"""DOCX to PDF through the real LibreOffice in the jail of the "soffice" profile (plan 02-08, 02-16).

Runs only inside the test stage of the image (sandbox.yml, -m container): the
development machine has neither LibreOffice nor Docker. The DOCX is written
here with the standard library, so the test needs no file outside the image.

History: HaRP run 44015648619 showed the regression (soffice ended after 249
ms in the jail of 02-08). Sandbox runs of 7e3c909, 11fb9f9 and 4ee9c31
narrowed it to /tmp; sandbox run 44054386548 (a80b90b, amd64 and arm64) named
the cause. With a fresh profile soffice restarts once (two dconf process ids
in stderr), and the second process cannot get past the OSL_PIPE socket of the
first, which it may not remove. With a profile made beforehand the conversion
works in the unchanged product jail without any right on /tmp
("warm-template-unjailed" and "warm-init-jailed/2": pdf=ja on both
architectures). REMOVE_FILE on /tmp would also convert, but the child could
then remove /tmp/exapp.sock (UNLINK-RISK socket-copy grant=ok: uid 10001, mode
0666, the sticky bit does not help). Owner decision 17.11.: the image build
makes the profile template, every job gets a fresh copy, no init run at run
time. The layer and variant diagnosis is evaluated and gone; what stays are
the lasting checks:

    SOFFICE-LAYER product exit=<code|-> signal=<n|None> pdf=<ja|nein> ms=<ms> template=<ok|reason>
    SOFFICE-STARTS <product|control-fresh-unjailed> n=<soffice.bin starts, parent not soffice.bin> [exit= pdf=]
    TMP-REST product before_cleanup=<name:type,...|-> after_cleanup=<name:type,...|->
    PIPE-NAME predicted=<ja|nein> seen=<n>
    TEMPLATE-FACTS dirs=<n> files=<n> bytes=<n> owner=<uid:gid,...> writable=<n> other=<n> mentions_path=<ja|nein>
    TEMPLATE-RESTART buildid=<match|differs|missing|unknown> setup_completed=<ja|nein> bundled=<n|absent>
        shared=<n|absent> mentions=<files|->
    TMP-FACTS uid=<uid> tmp=<uid>:<gid>:<mode> sticky=<ja|nein> exapp=<uid>:<gid>:<mode>:<type> access_w=...
    UNLINK-RISK target=<socket-copy|file|file-in-subdir> jail=<none|product> result=<ok|EACCES|...> like_exapp=...
    SOCKET-CONNECT <test-process|profile>=<ok|refused <errno>|absent>
    SOCKET-CONNECT-DENY <profile>=<refused EACCES|...>
    PROFILE-DENY-CONNECT profile=<p> work=<w> ok=<ja|nein|-> product_ok=<ja|nein|-> result=<word>
        events=<...> tail=<...>
    PROFILE-PRODUCT profile=<p> work=<w> result=<word> tail=<...>   (only when the product run failed)

Risks of the template (owner 17.11., "allen Risiken nachgehen"): R1 does the
copy start without a restart (SOFFICE-STARTS product n=1, a gate; the fresh
profile control must show the restart the counter is meant to see), and does
the server remove the one socket the child leaves (TMP-REST, after_cleanup
empty, a gate). R2 would the other profiles still work without connect()
(PROFILE-DENY-CONNECT, a measurement; its control SOCKET-CONNECT-DENY is a
gate). Why a fresh profile restarts and a copy should not, from the LibreOffice
25.2.3.2 sources: desktop/source/app/app.cxx cleanExtensionCache() returns
true when user/extensions/buildid is missing or differs from the build id of
the installation, and check_ext_deps.cxx SynchronizeExtensionRepositories then
calls requestRestart; the build writes buildid in Desktop::Init, before
--terminate_after_init ends the start. The path of the profile is no input of
that decision; userinstall.cxx reads ooSetupInstCompleted, not the path.

The gates: the product converts with one start; the template is root-owned
and read only; a child in the product jail removes nothing in /tmp; soffice
reaches no socket. The real HaRP socket is only described, never named to a child.
"""

import asyncio
import contextlib
import hashlib
import os
import re
import shutil
import socket
import stat
import sys
import threading
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

import pymupdf
import pytest

from pii_redaction_backend.sandbox import jail as sandbox_jail
from pii_redaction_backend.sandbox.jail import jail_argv
from pii_redaction_backend.sandbox.profiles import PROFILES
from pii_redaction_backend.sandbox.reaper import reap_group
from pii_redaction_backend.workers import child, soffice
from tests.conftest import record_measurement

pytestmark = [pytest.mark.container, pytest.mark.linux]

MARKER = "Containerprobe Umwandlung 4711"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
PACKAGE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)

DRIVER = Path(__file__).with_name("jail_layers.py")
WORK_DRIVER = Path(__file__).with_name("profile_work.py")
TMP = Path("/tmp")  # noqa: S108 - the folder the checks describe, test only
HARP_SOCKET = "/tmp/exapp.sock"  # noqa: S108 - the HaRP socket path, never removed by this test
JOB_ID = "990001"
CONTROL_JOB_ID = "990003"

# The start counter: /proc is read every POLL_S for processes of this uid whose
# name is soffice.bin (oosplash starts soffice.bin anew for a restart, so a
# restart is a second process id). A pid with its start time counts once.
# Only a soffice.bin whose parent is not soffice.bin is a start: soffice.bin
# itself forks helpers (fork, then exec), and between fork and exec the child
# still carries the name soffice.bin. Sandbox run of df2d2e5: n=6 (amd64) and
# n=7 (arm64) for the product and the fresh control alike, so the name alone
# counted these children. /proc/<pid>/exe does not separate them: before the
# exec the child still runs the image of soffice.bin. The parent does: a real
# start comes from oosplash (or the soffice script), a helper from soffice.bin.
PROC = Path("/proc")
SOFFICE_BIN = "soffice.bin"
POLL_S = 0.002
# /proc/<pid>/stat after the ")" of the name: field 3 (state) is index 0,
# field 4 (ppid) index 1, field 22 (starttime) index 19.
PPID_INDEX = 1
STARTTIME_INDEX = 19

# The installation LibreOffice compares the profile with (Debian layout).
LO_ROOT = Path("/usr/lib/libreoffice")
SETUP_COMPLETED = re.compile(rb'oor:name="ooSetupInstCompleted"[^>]*>\s*<value>true</value>')

# The stand-ins a child tries to remove, and the jails it runs in.
UNLINK_PREFIX = "pii-unlink-probe"
UNLINK_TARGETS = ("socket-copy", "file", "file-in-subdir")
UNLINK_JAILS = ("none", "product")
ACCESS_PATHS = ("/tmp", "/var/tmp")  # noqa: S108 - access(2) probe only, test only


def _docx(path: Path) -> Path:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}">'
        f"<w:body><w:p><w:r><w:t>{MARKER}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/document.xml", document)
    return path


def layer_line(result: Mapping[str, object]) -> str:
    """The SOFFICE-LAYER line of the product run."""
    return (
        f"SOFFICE-LAYER product exit={result['exit']} signal={result['signal']} "
        f"pdf={'ja' if result['pdf'] else 'nein'} ms={result['ms']} template={result['template']}"
    )


def _uid() -> int:
    """The uid of this process; -1 where there is none (the helpers also run on Windows)."""
    if sys.platform == "win32":
        return -1
    return os.getuid()


@dataclass(frozen=True, slots=True)
class ProcEntry:
    """What the counter reads of one process in /proc."""

    name: str
    ppid: int
    start: int
    owner: int


def read_proc(proc: Path = PROC) -> dict[int, ProcEntry]:
    """pid -> name, parent, start time and owner of every process /proc shows now; unreadable ones are left out."""
    found: dict[int, ProcEntry] = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="ascii", errors="replace")
            owner = entry.stat().st_uid
        except OSError:
            continue
        head, closing, tail = raw.rpartition(")")
        fields = tail.split()
        if not closing or len(fields) <= STARTTIME_INDEX:
            continue
        ppid, start = fields[PPID_INDEX], fields[STARTTIME_INDEX]
        if not (ppid.isdigit() and start.isdigit()):
            continue
        found[int(entry.name)] = ProcEntry(head.partition("(")[2], int(ppid), int(start), owner)
    return found


def soffice_processes(proc: Path = PROC, uid: int | None = None) -> set[tuple[int, int]]:
    """(pid, start time) of every soffice.bin start of uid (any uid when None) that /proc shows now.

    A soffice.bin whose parent is soffice.bin is a forked helper before its
    exec, not a start (see PROC). A parent /proc no longer shows is no
    soffice.bin as far as this scan knows, so that process counts.
    """
    table = read_proc(proc)
    found: set[tuple[int, int]] = set()
    for pid, entry in table.items():
        if entry.name != SOFFICE_BIN or (uid is not None and entry.owner != uid):
            continue
        parent = table.get(entry.ppid)
        if parent is not None and parent.name == SOFFICE_BIN:
            continue
        found.add((pid, entry.start))
    return found


class StartCounter:
    """Counts the soffice.bin processes that appear while the block runs (a thread reads /proc)."""

    def __init__(self, proc: Path = PROC, uid: int | None = None, poll_s: float = POLL_S) -> None:
        self._proc, self._uid, self._poll_s = proc, uid, poll_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self.seen: set[tuple[int, int]] = set()
        self._before: set[tuple[int, int]] = set()

    def _scan(self) -> None:
        self.seen |= soffice_processes(self._proc, self._uid) - self._before

    def _watch(self) -> None:
        while not self._stop.is_set():
            self._scan()
            self._stop.wait(self._poll_s)

    def __enter__(self) -> "StartCounter":
        self._before = soffice_processes(self._proc, self._uid)
        self._thread.start()
        return self

    def __exit__(
        self, _type: type[BaseException] | None, _value: BaseException | None, _trace: TracebackType | None
    ) -> None:
        self._stop.set()
        self._thread.join()
        self._scan()

    @property
    def n(self) -> int:
        return len(self.seen)


def starts_line(who: str, n: int, extra: str = "") -> str:
    return f"SOFFICE-STARTS {who} n={n}{f' {extra}' if extra else ''}"


def tmp_entries(root: Path) -> dict[str, str]:
    """name -> type of every entry directly in root."""
    entries: dict[str, str] = {}
    for path in root.iterdir():
        try:
            entries[path.name] = _kind(path.lstat())
        except OSError:
            entries[path.name] = "gone"
    return entries


def new_entries(before: Mapping[str, str], now: Mapping[str, str]) -> list[str]:
    return sorted(f"{name}:{kind}" for name, kind in now.items() if name not in before)


def rest_line(before_cleanup: list[str], after_cleanup: list[str]) -> str:
    return (
        f"TMP-REST product before_cleanup={','.join(before_cleanup) or '-'} "
        f"after_cleanup={','.join(after_cleanup) or '-'}"
    )


def lo_hex(digest: bytes) -> str:
    """Bytes in hex the way LibreOffice writes the pipe hash: lower case, no leading zero per byte."""
    return "".join(format(byte, "x") for byte in digest)


def predicted_pipe_name(argv: list[str], uid: int) -> str:
    """The pipe socket name of a soffice command line (officeipcthread.cxx: MD5 of the UTF-16 URL)."""
    prefix = "-env:UserInstallation="
    url = next(arg[len(prefix) :] for arg in argv if arg.startswith(prefix))
    digest = hashlib.md5(url.encode("utf-16-le"), usedforsecurity=False).digest()
    return f"OSL_PIPE_{uid}_SingleOfficeIPC_{lo_hex(digest)}"


async def test_a_docx_becomes_a_pdf_in_the_soffice_jail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _docx(tmp_path / "probe.docx")
    outdir = tmp_path / "pdf"
    # What the child leaves in /tmp, seen by the server just before and just after its cleanup.
    snapshot = tmp_entries(TMP)
    cleanups: list[tuple[list[str], list[str]]] = []
    remove = soffice._remove_ipc_sockets

    def watched_remove(root: Path) -> None:
        before = new_entries(snapshot, tmp_entries(TMP))
        remove(root)
        cleanups.append((before, new_entries(snapshot, tmp_entries(TMP))))

    monkeypatch.setattr(soffice, "_remove_ipc_sockets", watched_remove)
    started = time.monotonic()
    result: dict[str, object] = {"exit": "-", "signal": None, "pdf": False, "template": "ok"}
    failure = ""
    pdf: Path | None = None
    with StartCounter(uid=_uid()) as counter:
        try:
            pdf = await soffice.convert(source, outdir, JOB_ID)
            result["exit"] = 0
        except soffice.ProfileTemplateMissing as missing:
            result["template"] = missing.reason
            failure = f"profile template unusable: {missing.reason}"
        except child.ChildFailed as failed:
            result["exit"], result["signal"] = failed.exit_code, failed.signal
            failure = f"soffice failed: exit {failed.exit_code}, signal {failed.signal}, stderr {failed.stderr_tail!r}"
    result["ms"] = int((time.monotonic() - started) * 1000)
    result["pdf"] = pdf is not None
    before_cleanup, after_cleanup = cleanups[-1] if cleanups else (["no-cleanup"], ["no-cleanup"])
    expected_pipe = predicted_pipe_name(soffice.command(source, outdir, JOB_ID), _uid())
    pipes = [entry for entry in before_cleanup if entry.startswith("OSL_PIPE_")]
    lines = [
        layer_line(result),
        starts_line("product", counter.n),
        rest_line(before_cleanup, after_cleanup),
        f"PIPE-NAME predicted={'ja' if f'{expected_pipe}:sock' in pipes else 'nein'} seen={len(pipes)}",
    ]
    # Outside the capture, so the lines stand in the job log of a passing run, too.
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    record_measurement("soffice_product", result)
    record_measurement(
        "soffice_starts", {"product": counter.n, "before_cleanup": before_cleanup, "after_cleanup": after_cleanup}
    )
    if pdf is None:
        pytest.fail(failure)
    record_measurement("soffice_docx_ms", result["ms"])

    with pymupdf.open(pdf) as document:
        assert document.page_count == 1
        assert MARKER in document[0].get_text()
    # R1: the copy of the template starts once, no restart.
    assert counter.n == 1, lines
    # The server cleaned up: nothing new in /tmp, the profile with its copy is gone, no socket is left.
    assert after_cleanup == [], lines
    assert _leftovers(JOB_ID) == []


async def test_control_a_fresh_profile_restarts_unjailed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Positive control of the start counter: an empty profile, no jail, must show the restart (n >= 2).

    Without the jail the second process can take the pipe over, so this run
    may convert; it only shows that the counter sees a restart when there is one.
    """
    source = _docx(tmp_path / "control.docx")
    outdir = tmp_path / "pdf"
    outdir.mkdir()
    profile, env = soffice.prepare_profile(CONTROL_JOB_ID)
    code: int | None = None
    try:
        with StartCounter(uid=_uid()) as counter:
            process = await asyncio.create_subprocess_exec(
                *soffice.command(source, outdir, CONTROL_JOB_ID),
                cwd=outdir,
                env=child.child_env(env, profile="soffice"),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                code = await asyncio.wait_for(process.wait(), timeout=soffice.DEFAULT_TIMEOUT_S)
            except TimeoutError:
                child._kill_group(process.pid)
                await process.wait()
            finally:
                reap_group(process.pid)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        soffice._remove_ipc_sockets(TMP)
    pdf = any(outdir.glob("*.pdf"))
    line = starts_line("control-fresh-unjailed", counter.n, f"exit={code} pdf={'ja' if pdf else 'nein'}")
    with capsys.disabled():
        print(f"\n{line}")
    record_measurement("soffice_starts_control", {"n": counter.n, "exit": code, "pdf": pdf})
    assert counter.n >= 2, line


def _leftovers(job_id: str) -> list[str]:
    root = Path(soffice.PROFILE_ROOT)
    found = [path.name for path in root.glob(soffice.IPC_SOCKET_GLOB)]
    return found + ([f"lo-{job_id}"] if (root / f"lo-{job_id}").exists() else [])


# -- the profile template of the image ------------------------------------------------------


def template_facts(root: Path) -> dict[str, object]:
    """Folders, files, bytes, owners, entries with a write bit or writable for this process, other types.

    mentions_path: does any file name the template folder itself (a copy
    would then point back to the read-only template)? A measurement only.
    """
    counts = {"dirs": 0, "files": 0, "bytes": 0, "writable": 0, "other": 0}
    owners: set[str] = set()
    mentions = False
    needle = str(root).encode()
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        owners.add(f"{info.st_uid}:{info.st_gid}")
        if info.st_mode & 0o222 or os.access(path, os.W_OK, follow_symlinks=False):
            counts["writable"] += 1
        if stat.S_ISDIR(info.st_mode):
            counts["dirs"] += 1
        elif stat.S_ISREG(info.st_mode):
            counts["files"] += 1
            counts["bytes"] += info.st_size
            mentions = mentions or needle in path.read_bytes()
        else:
            counts["other"] += 1
    return {**counts, "owner": ",".join(sorted(owners)), "mentions_path": "ja" if mentions else "nein"}


def template_line(facts: Mapping[str, object]) -> str:
    return (
        f"TEMPLATE-FACTS dirs={facts['dirs']} files={facts['files']} bytes={facts['bytes']} "
        f"owner={facts['owner']} writable={facts['writable']} other={facts['other']} "
        f"mentions_path={facts['mentions_path']}"
    )


def test_the_profile_template_is_in_the_image_root_owned_and_read_only(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(soffice.PROFILE_TEMPLATE)
    assert root.is_dir(), "the image carries no soffice profile template"
    assert (root / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER).is_file()
    facts = template_facts(root)
    with capsys.disabled():
        print(f"\n{template_line(facts)}")
    record_measurement("soffice_template", facts)
    assert facts["owner"] == "0:0", facts
    assert facts["writable"] == 0, facts
    assert facts["other"] == 0, facts
    # Positive control: this process (uid 10001) does write where it may.
    assert os.access(Path(soffice.PROFILE_ROOT), os.W_OK)


def _count(folder: Path) -> str:
    return str(len(list(folder.iterdir()))) if folder.is_dir() else "absent"


def _installed_buildid(lo_root: Path) -> str | None:
    """buildid= of program/versionrc, the value desktop/source/app/app.cxx expands for cleanExtensionCache."""
    try:
        text = (lo_root / "program" / "versionrc").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        key, has_value, value = line.partition("=")
        if has_value and key.strip() == "buildid":
            return value.strip()
    return None


def restart_facts(template: Path, lo_root: Path) -> dict[str, str]:
    """What LibreOffice 25.2 compares at start, read from the template and the installation.

    buildid: user/extensions/buildid against the installation (a difference
    or a missing file means cleanExtensionCache and a restart). setup_completed:
    ooSetupInstCompleted in registrymodifications.xcu (missing means
    userinstall::create and Migration). bundled/shared: entries in the
    extension folders of the installation (SynchronizeExtensionRepositories
    restarts when it registers something new). mentions: files of the
    template that name the template folder, relative.
    """
    user = template / soffice.PROFILE_USER
    installed = _installed_buildid(lo_root)
    try:
        stored = (user / "extensions" / "buildid").read_bytes().decode("latin-1").strip()
    except OSError:
        stored = None
    if stored is None:
        buildid = "missing"
    elif installed is None:
        buildid = "unknown"
    else:
        buildid = "match" if stored == installed else "differs"
    try:
        completed = SETUP_COMPLETED.search((user / soffice.TEMPLATE_MARKER).read_bytes()) is not None
    except OSError:
        completed = False
    needle = str(template).encode()
    mentions = sorted(
        path.relative_to(template).as_posix()
        for path in template.rglob("*")
        if path.is_file() and not path.is_symlink() and needle in path.read_bytes()
    )
    return {
        "buildid": buildid,
        "setup_completed": "ja" if completed else "nein",
        "bundled": _count(lo_root / "share" / "extensions"),
        "shared": _count(lo_root / "share" / "uno_packages"),
        "mentions": ",".join(mentions) or "-",
    }


def restart_line(facts: Mapping[str, str]) -> str:
    return (
        f"TEMPLATE-RESTART buildid={facts['buildid']} setup_completed={facts['setup_completed']} "
        f"bundled={facts['bundled']} shared={facts['shared']} mentions={facts['mentions']}"
    )


def test_the_template_carries_what_lets_a_copy_start_without_restart(capsys: pytest.CaptureFixture[str]) -> None:
    """A measurement for R1; the gate is SOFFICE-STARTS product n=1 of the product test."""
    facts = restart_facts(Path(soffice.PROFILE_TEMPLATE), LO_ROOT)
    with capsys.disabled():
        print(f"\n{restart_line(facts)}")
    record_measurement("soffice_template_restart", facts)
    # The build made the template with --terminate_after_init, which writes buildid in Desktop::Init.
    assert facts["buildid"] != "missing", facts


# -- how far would REMOVE_FILE on /tmp reach? (the reason it was refused) -------------------


def _mode(info: os.stat_result) -> str:
    return f"{stat.S_IMODE(info.st_mode):04o}"


def _kind(info: os.stat_result) -> str:
    if stat.S_ISSOCK(info.st_mode):
        return "sock"
    if stat.S_ISREG(info.st_mode):
        return "file"
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    return "other"


def describe(path: Path) -> str:
    """uid:gid:mode:type of a path without following a symlink, or absent."""
    try:
        info = path.lstat()
    except OSError:
        return "absent"
    return f"{info.st_uid}:{info.st_gid}:{_mode(info)}:{_kind(info)}"


def _remove(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def unlink_target(kind: str, root: Path, like: Path) -> tuple[Path, socket.socket | None]:
    """A stand-in below root that a child tries to remove; never the HaRP socket.

    socket-copy listens like the HaRP socket and gets its mode (owner is this
    process, the line says whether it matches); file and file-in-subdir are
    plain files of this uid, 0600.
    """
    if kind not in UNLINK_TARGETS:
        msg = f"unknown unlink target {kind!r}"
        raise ValueError(msg)
    if kind == "file-in-subdir":
        folder = root / f"{UNLINK_PREFIX}.d"
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / "file"
    else:
        path = root / f"{UNLINK_PREFIX}.{'sock' if kind == 'socket-copy' else 'file'}"
    if path.as_posix() == HARP_SOCKET or path.name == Path(HARP_SOCKET).name:
        msg = "the HaRP socket is never a target"
        raise ValueError(msg)
    _remove(path)
    listener: socket.socket | None = None
    if kind == "socket-copy":
        family = getattr(socket, "AF_UNIX", None)
        if family is None:
            msg = "a socket stand-in needs AF_UNIX"
            raise OSError(msg)
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(1)
        with contextlib.suppress(OSError):
            path.chmod(stat.S_IMODE(like.lstat().st_mode))
    else:
        path.write_bytes(b"stand-in\n")
        path.chmod(0o600)
    return path, listener


def like_exapp(path: Path, like: Path) -> str:
    """ja when owner, group and mode equal those of the HaRP socket, nein when not, - when it is absent."""
    mine, theirs = describe(path), describe(like)
    if theirs == "absent" or mine == "absent":
        return "-"
    return "ja" if mine.split(":")[:3] == theirs.split(":")[:3] else "nein"


def tmp_facts(harp: Path, access: Mapping[str, str], root: Path = TMP) -> str:
    """The TMP-FACTS line: this uid, owner/mode/sticky of root, the HaRP socket, access(W_OK) in the product jail."""
    info = root.lstat()
    sticky = "ja" if info.st_mode & stat.S_ISVTX else "nein"
    answers = ",".join(f"{path}:{answer}" for path, answer in access.items())
    uid = "-"
    if sys.platform != "win32":
        uid = str(_uid())
    return (
        f"TMP-FACTS uid={uid} tmp={info.st_uid}:{info.st_gid}:{_mode(info)} sticky={sticky} "
        f"exapp={describe(harp)} access_w={answers}"
    )


def unlink_argv(jail: str, path: Path) -> list[str]:
    probe = [sys.executable, "-I", str(DRIVER), "unlink", str(path)]
    if jail == "none":
        return probe
    if jail == "product":
        return jail_argv("soffice", probe)
    msg = f"unknown jail {jail!r}"
    raise ValueError(msg)


async def test_negative_a_child_in_the_soffice_jail_removes_nothing_in_tmp(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """TMP-FACTS and UNLINK-RISK; the real HaRP socket is only described, never named to a child."""
    harp = Path(os.environ.get("HP_EXAPP_SOCK", HARP_SOCKET))
    access: dict[str, str] = {}
    for path in ACCESS_PATHS:
        access[path] = await _probe(jail_argv("soffice", [sys.executable, "-I", str(DRIVER), "access", path]))
    facts = tmp_facts(harp, access)
    lines = [facts]
    answers: dict[str, str] = {}
    for kind in UNLINK_TARGETS:
        for jail in UNLINK_JAILS:
            path, listener = unlink_target(kind, TMP, harp)
            try:
                like = like_exapp(path, harp) if kind == "socket-copy" else "-"
                answer = await _probe(unlink_argv(jail, path))
            finally:
                if listener is not None:
                    listener.close()
                _remove(path)
                if kind == "file-in-subdir":
                    with contextlib.suppress(OSError):
                        path.parent.rmdir()
            answers[f"{kind}/{jail}"] = answer
            lines.append(f"UNLINK-RISK target={kind} jail={jail} result={answer} like_exapp={like}")
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    record_measurement("unlink_risk", {"facts": facts, "answers": answers})
    # The HaRP socket is untouched.
    assert describe(harp) != "absent" or "HP_EXAPP_SOCK" not in os.environ
    for kind in UNLINK_TARGETS:
        # Positive control: an unjailed process of this uid removes the stand-in.
        assert answers[f"{kind}/none"] == "ok", answers
        # The product jail grants no removal in /tmp.
        assert answers[f"{kind}/product"] != "ok", answers


def deny_connect_argv(
    profile: str, args: list[str], *, read: tuple[str, ...] = (), write: tuple[str, ...] = ()
) -> list[str]:
    """The product jail of profile with deny_connect on (jail_layers.py deny-connect), test only."""
    product = jail_argv(profile, args, read=read, write=write)
    return [sys.executable, "-I", str(DRIVER), "deny-connect", *product[4:]]


async def test_soffice_reaches_no_socket(capsys: pytest.CaptureFixture[str]) -> None:
    """SOCKET-CONNECT <who>=<ok|refused|absent> for every profile as it stands, and SOCKET-CONNECT-DENY.

    soffice: the product jail, whose seccomp filter refuses connect() for
    every family: must answer "refused EACCES" (owner decision 17.11.). The
    other profiles keep connect() for now: their answers describe the state
    (R2). SOCKET-CONNECT-DENY is the same probe in each profile with
    deny_connect on: every one must answer "refused EACCES", or the
    PROFILE-DENY-CONNECT measurement would not mean what it says.
    """
    path = os.environ.get("HP_EXAPP_SOCK", HARP_SOCKET)
    probe = [sys.executable, "-I", str(DRIVER), "connect", path]
    answers = {"test-process": await _probe(probe)}
    for name in PROFILES:
        answers[name] = await _probe(jail_argv(name, probe))
    denied = {name: await _probe(deny_connect_argv(name, probe)) for name in PROFILES}
    with capsys.disabled():
        print()
        for who, answer in answers.items():
            print(f"SOCKET-CONNECT {who}={answer}")
        for who, answer in denied.items():
            print(f"SOCKET-CONNECT-DENY {who}={answer}")
    record_measurement("socket_connect", answers)
    record_measurement("socket_connect_deny", denied)
    # Positive control: the socket is there and answers an unjailed process;
    # and every jailed probe really ran (a jail failure would print nothing).
    assert answers["test-process"] == "ok", answers
    for who, answer in answers.items():
        assert answer == "ok" or answer.startswith("refused"), (who, answer)
    assert answers["soffice"] == "refused EACCES", answers
    assert set(denied.values()) == {"refused EACCES"}, denied


# -- R2: does the work of each profile run without connect()? -------------------------------

# Stands for the fresh output folder of one run in the arguments of a work.
OUT = "{out}"
JAILS = ("product", "deny")


@dataclass(frozen=True, slots=True)
class Work:
    """One piece of real work of a profile; OUT in args and write becomes the folder of the run."""

    profile: str
    name: str
    args: tuple[str, ...]
    read: tuple[str, ...]
    timeout_s: float = 120.0
    python: bool = True

    def argv(self, out: Path) -> list[str]:
        args = [arg.replace(OUT, str(out)) for arg in self.args]
        return work_argv(*args) if self.python else args


def work_argv(*args: str) -> list[str]:
    return [sys.executable, "-I", str(WORK_DRIVER), *args]


def _ja(flag: object) -> str:
    return "-" if flag is None else ("ja" if flag else "nein")


def work_line(work: Work, product: Mapping[str, object], denied: Mapping[str, object]) -> str:
    """The PROFILE-DENY-CONNECT line: the deny-connect run, and whether the product run worked."""
    result, _, events = str(denied["result"]).partition(" events=")
    return (
        f"PROFILE-DENY-CONNECT profile={work.profile} work={work.name} ok={_ja(denied['ok'])} "
        f"product_ok={_ja(product['ok'])} result={result.removeprefix('result=')} events={events or '-'} "
        f"tail={denied['tail'] or '-'}"
    )


def absent_line(profile: str, name: str, reason: str) -> str:
    return f"PROFILE-DENY-CONNECT profile={profile} work={name} ok=- product_ok=- result={reason} events=- tail=-"


def really_ran(run: Mapping[str, object]) -> bool:
    """A result line came back and the jail did not fail (exit 71 or a usage error)."""
    failed_jail = (sandbox_jail.EXIT_LAYER_FAILED, sandbox_jail.EXIT_USAGE)
    return str(run["result"]).startswith("result=") and run["exit"] not in failed_jail


async def _run_work(argv: list[str], profile: str, timeout_s: float) -> dict[str, object]:
    """exit, the result line of profile_work.py (or no-answer), the cleaned stderr tail, ok."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=child.child_env(profile=profile),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError:
        child._kill_group(process.pid)
        await process.wait()
        return {"exit": None, "result": "result=fail:timeout events=-", "tail": "", "ok": False}
    finally:
        reap_group(process.pid)
    lines = [line for line in out.decode("ascii", errors="replace").splitlines() if line.startswith("result=")]
    result = lines[-1] if lines else f"no-answer exit={process.returncode}"
    return {
        "exit": process.returncode,
        "result": result,
        "tail": child.diagnostic_tail(err, child.TAIL_LINES),
        "ok": result.startswith("result=ok "),
    }


async def _run_tesseract(work: Work, out: Path, build: str) -> dict[str, object]:
    """Tesseract has no result line: ok is exit 0 and a text file."""
    argv = work.argv(out)
    command = (jail_argv if build == "product" else deny_connect_argv)(
        work.profile, argv, read=work.read, write=(str(out),)
    )
    run = await _run_work(command, work.profile, work.timeout_s)
    ok = run["exit"] == 0 and (out / "text.txt").is_file()
    return {**run, "ok": ok, "result": f"result={'ok' if ok else 'fail:exit' + str(run['exit'])} events=-"}


def _pdf(path: Path) -> Path:
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), MARKER)
        document.save(path)
    return path


def _png(path: Path) -> Path:
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=120)
        page.insert_text((20, 60), "Containerprobe 4711", fontsize=24)
        page.get_pixmap(dpi=150).save(path)
    return path


def profile_works(pdf: Path, docx: Path, png: Path, models: Path, tesseract: str | None) -> list[Work | str]:
    """The work of every profile but soffice (a gate of its own); a string where the work cannot run here."""
    works: list[Work | str] = [
        Work("render", "render", ("module", "render", str(pdf), f"{OUT}/page.png", "72"), (str(pdf),)),
        Work("render", "placeholder", ("module", "placeholder", f"{OUT}/ph.pdf", "990002"), ()),
        Work("precheck", "precheck", ("precheck", str(pdf), str(docx)), (str(pdf), str(docx))),
        Work("sanitize", "sanitize", ("sanitize", str(docx), f"{OUT}/clean.docx"), (str(docx),)),
    ]
    if (models / "gliner2").is_dir():
        works.append(Work("detect", "detect", ("detect", str(models)), (str(models),), timeout_s=900.0))
    else:
        works.append(absent_line("detect", "detect", "no-models"))
    if tesseract is None:
        works.append(absent_line("ocr", "tesseract", "absent"))
    else:
        works.append(Work("ocr", "tesseract", (tesseract, str(png), f"{OUT}/text"), (str(png),), python=False))
    return works


async def test_each_profile_does_its_work_with_connect_denied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PROFILE-DENY-CONNECT per profile: a measurement for R2, nothing in the product changes.

    Each work runs twice in fresh folders: in the product jail of its profile
    and in the same jail with deny_connect. A switch is only safe where
    product_ok=ja and ok=ja. The gate here is only that every run really ran
    (a result line, no jail failure), so a broken jail or driver cannot pass
    as a measurement.
    """
    models = Path(os.environ.get("PII_MODELS", "/models"))
    works = profile_works(
        _pdf(tmp_path / "probe.pdf"),
        _docx(tmp_path / "probe.docx"),
        _png(tmp_path / "probe.png"),
        models,
        shutil.which("tesseract"),
    )
    lines: list[str] = []
    measured: dict[str, object] = {}
    not_run: list[str] = []
    for work in works:
        if isinstance(work, str):
            lines.append(work)
            continue
        runs: dict[str, dict[str, object]] = {}
        for build in JAILS:
            out = tmp_path / f"{work.profile}-{work.name}-{build}"
            out.mkdir()
            if not work.python:
                runs[build] = await _run_tesseract(work, out, build)
                continue
            make = jail_argv if build == "product" else deny_connect_argv
            command = make(work.profile, work.argv(out), read=work.read, write=(str(out),))
            runs[build] = await _run_work(command, work.profile, work.timeout_s)
        lines.append(work_line(work, runs["product"], runs["deny"]))
        if not runs["product"]["ok"]:
            product = runs["product"]
            lines.append(
                f"PROFILE-PRODUCT profile={work.profile} work={work.name} "
                f"result={product['result']} tail={product['tail'] or '-'}"
            )
        measured[f"{work.profile}/{work.name}"] = runs
        not_run += [f"{work.name}/{build}" for build, run in runs.items() if not really_ran(run)]
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    record_measurement("profile_deny_connect", measured)
    assert not_run == [], lines


async def _probe(argv: list[str]) -> str:
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=child.child_env(profile="soffice"),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    out, _ = await asyncio.wait_for(process.communicate(), timeout=30)
    text = out.decode("ascii", errors="replace").strip()
    return text or f"no-answer exit={process.returncode}"
