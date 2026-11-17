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
    TEMPLATE-FACTS dirs=<n> files=<n> bytes=<n> owner=<uid:gid,...> writable=<n> other=<n> mentions_path=<ja|nein>
    TMP-FACTS uid=<uid> tmp=<uid>:<gid>:<mode> sticky=<ja|nein> exapp=<uid>:<gid>:<mode>:<type> access_w=...
    UNLINK-RISK target=<socket-copy|file|file-in-subdir> jail=<none|product> result=<ok|EACCES|...> like_exapp=...
    SOCKET-CONNECT <test-process|soffice|render>=<ok|refused <errno>|absent>

The gates: the product converts; the template is root-owned and read only;
a child in the product jail removes nothing in /tmp; soffice reaches no
socket. The real HaRP socket is only described, never named to a child.
"""

import asyncio
import contextlib
import os
import socket
import stat
import sys
import time
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.sandbox.jail import jail_argv
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
TMP = Path("/tmp")  # noqa: S108 - the folder the checks describe, test only
HARP_SOCKET = "/tmp/exapp.sock"  # noqa: S108 - the HaRP socket path, never removed by this test
JOB_ID = "990001"

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


async def test_a_docx_becomes_a_pdf_in_the_soffice_jail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _docx(tmp_path / "probe.docx")
    outdir = tmp_path / "pdf"
    started = time.monotonic()
    result: dict[str, object] = {"exit": "-", "signal": None, "pdf": False, "template": "ok"}
    failure = ""
    pdf: Path | None = None
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
    # Outside the capture, so the line stands in the job log of a passing run, too.
    with capsys.disabled():
        print(f"\n{layer_line(result)}")
    record_measurement("soffice_product", result)
    if pdf is None:
        pytest.fail(failure)
    record_measurement("soffice_docx_ms", result["ms"])

    with pymupdf.open(pdf) as document:
        assert document.page_count == 1
        assert MARKER in document[0].get_text()
    # The profile with its copy of the template is gone, and no socket is left in /tmp.
    assert _leftovers(JOB_ID) == []


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
        uid = str(os.getuid())
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


async def test_soffice_reaches_no_socket(capsys: pytest.CaptureFixture[str]) -> None:
    """SOCKET-CONNECT <who>=<ok|refused|absent>; for soffice a gate since the owner decision of 17.11.

    soffice: the product jail, whose seccomp filter refuses connect() for
    every family: must answer "refused EACCES". render: a profile with
    connect() open, a measurement (sandbox runs showed ok) for a later
    decision.
    """
    path = os.environ.get("HP_EXAPP_SOCK", HARP_SOCKET)
    probe = [sys.executable, "-I", str(DRIVER), "connect", path]
    runs = {
        "test-process": probe,
        "soffice": jail_argv("soffice", probe),
        "render": jail_argv("render", probe),
    }
    answers = {who: await _probe(argv) for who, argv in runs.items()}
    with capsys.disabled():
        print()
        for who, answer in answers.items():
            print(f"SOCKET-CONNECT {who}={answer}")
    record_measurement("socket_connect", answers)
    # Positive control: the socket is there and answers an unjailed process;
    # and every jailed probe really ran (a jail failure would print nothing).
    assert answers["test-process"] == "ok", answers
    for who, answer in answers.items():
        assert answer == "ok" or answer.startswith("refused"), (who, answer)
    assert answers["soffice"] == "refused EACCES", answers


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
