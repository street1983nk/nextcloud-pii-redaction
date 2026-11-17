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
    SOFFICE-STARTS <product|control-fresh-unjailed> n=<soffice.bin starts: parent not soffice.bin, alive,
        cmdline and exe of the program> [exit= pdf=]
    SOFFICE-START-DETAIL kind=<product|control-fresh-unjailed> counted=<ja|nein reason=<why>> pid= ppid=
        parent_comm= comm= exe_basename=
        cmdline_head= first_seen_ms= counted_ms= pgrp= first_ppid= first_parent_comm= earlier_fork=<ja|nein>
        ppids=<a>b..> names=<..> states=<..>   (one per counted start and per refused candidate)
    TMP-REST product before_cleanup=<name:type,...|-> after_cleanup=<name:type,...|->
    PIPE-NAME predicted=<ja|nein> seen=<n>
    TEMPLATE-FACTS dirs=<n> files=<n> bytes=<n> owner=<uid:gid,...> writable=<n> other=<n> mentions_path=<ja|nein>
    TEMPLATE-RESTART buildid=<match|differs|missing|unknown> setup_completed=<ja|nein> bundled=<n|absent>
        shared=<n|absent> mentions=<files|->
    TMP-FACTS uid=<uid> tmp=<uid>:<gid>:<mode> sticky=<ja|nein> exapp=<uid>:<gid>:<mode>:<type> access_w=...
    UNLINK-RISK target=<socket-copy|file|file-in-subdir> jail=<none|product> result=<ok|EACCES|...> like_exapp=...
    SOCKET-CONNECT <test-process|profile>=<ok|refused <errno>|absent>
    SOCKET-CONNECT-DENY <profile>=<refused EACCES|...>
    PROFILE-WORK profile=<p> work=<w> product_ok=<ja|nein> result=<word> events=<...> tail=<...>
    PROFILE-DENY-CONNECT profile=<p> work=<w> ok=<ja|nein|-> product_ok=<ja|nein|-> result=<word>
        events=<...> tail=<...>
    PROFILE-PRODUCT profile=<p> work=<w> result=<word> tail=<...>   (only when the product run failed)
    PROFILE-TRACE profile=detect work=detect build=<product|deny> marks=<MARK lines> dumps=<n> last_dump=<stacks>
        (on a timeout tail= holds state, threads, cpu_s, wchan, top_threads, stderr= and trace= of the child)
    ZOMBIES after_job=<zombies of the job group after convert()> pgrp=<groups> other_uid_zombies=<n>
        subreaper=<ja|nein>   (a gate: after_job=0)
    DETECT-STACK name=<variant> dump=<i>/<n> at=<0:00:30|0:01:00|0:01:30|harness> threads=<n>
        stacks=<thread < module:line func < ... || ...>   (one per stack dump of a variant run)
    TORCH-FACTS env=<unjailed|jailed-product> arch= ok= result= torch= aten_threads= aten_interop=
        omp_max_threads= mkl_max_threads= hw_concurrency= backend= openmp= mkldnn_version= num_threads= interop=
        mkldnn= acl= config_acl= mkl= omp_avail= cpu_cap= omp_thread_limit= omp_num_threads=
        matmul512_x20_ms= score_queries_x20_ms= score_queries_first_ms= score_queries_ftz_x20_ms=
        score_queries_ftz_first_ms= ftz= tail=   (a measurement; ms=timeout for a step past BENCH_STEP_S)
    DETECT-VARIANT name=<unjailed|jailed-sys-cpu-read|jailed-threads-cpu|jailed-product|unjailed-no-omp-limit|
        jailed-product-no-omp-limit> ok=<ja|nein>
        ms_extract=<ms|-> threads=<torch threads> cpu_cap=<...> interop= cpu_count= affinity= present= possible=
        online= cpuinfo= omp_num_threads= omp_thread_limit= result=<word> tail=<...>   (a measurement)

Risks of the template (owner 17.11., "allen Risiken nachgehen"): R1 does the
copy start without a restart (SOFFICE-STARTS product n=1, a gate; the fresh
profile control must show the restart the counter is meant to see), and does
the server remove the one socket the child leaves (TMP-REST, after_cleanup
empty, a gate). R2 would the other profiles still work without connect()?
Sandbox run of df2d2e5 measured render, precheck and sanitize: ok on amd64 and
arm64, so the owner switched them (17.11.); their product jail refuses
connect() now (SOCKET-CONNECT refused EACCES, a gate) and their work must run
in it (PROFILE-WORK, a gate). detect and ocr stay a measurement
(PROFILE-DENY-CONNECT; its control SOCKET-CONNECT-DENY is a gate).

Why a fresh profile restarts and a copy should not, from the LibreOffice
25.2.3.2 sources: desktop/source/app/app.cxx cleanExtensionCache() returns
true when user/extensions/buildid is missing or differs from the build id of
the installation, and check_ext_deps.cxx SynchronizeExtensionRepositories then
calls requestRestart; the build writes buildid in Desktop::Init, before
--terminate_after_init ends the start. The path of the profile is no input of
that decision; userinstall.cxx reads ooSetupInstCompleted, not the path.

The gates: the product converts with one start; the template is root-owned
and read only; a child in the product jail removes nothing in /tmp; soffice,
render, precheck and sanitize reach no socket and still do their work. The
real HaRP socket is only described, never named to a child.
"""

import asyncio
import contextlib
import hashlib
import os
import platform
import re
import shutil
import signal
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
from pii_redaction_backend.sandbox.reaper import become_subreaper, reap_group
from pii_redaction_backend.workers import child, soffice
from tests.conftest import record_measurement
from tests.profile_work import BENCH_FILE, BENCH_STEP_S, BENCH_STEPS, TRACE_FILE

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
# field 4 (ppid) index 1, field 5 (pgrp) index 2, field 22 (starttime) index 19.
STATE_INDEX = 0
PPID_INDEX = 1
PGRP_INDEX = 2
STARTTIME_INDEX = 19
# Sandbox run of cfb428a: the product counted n=4 (amd64 and arm64) with one
# pipe and a PDF, the fresh control n=2. Sandbox run of 335a80f named them: one
# real soffice.bin (exe soffice.bin, cmdline the program path, parent
# oosplash) and three zombies in the oosplash group whose parent was gone
# (first_ppid=1, no exe, no cmdline, state Z or R>Z): forks of soffice.bin
# that ended before an exec. So a start also needs a program identity
# (identity_reason): alive, cmdline starting with the program path, exe
# soffice.bin. Everything the parent rule lets through but the identity does
# not gets a SOFFICE-START-DETAIL line with counted=nein and its reason.
CMDLINE_ARGS = 3
CMDLINE_CHARS = 120
SOFFICE_BIN_PATH = "/usr/lib/libreoffice/program/soffice.bin"
DEAD_STATES = frozenset({"Z", "X", "x"})

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
    state: str = "?"
    pgrp: int = 0


def read_proc(proc: Path = PROC) -> dict[int, ProcEntry]:
    """pid -> name, parent, start time, owner, state and group of every process /proc shows now.

    Unreadable ones are left out.
    """
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
        ppid, start, pgrp = fields[PPID_INDEX], fields[STARTTIME_INDEX], fields[PGRP_INDEX]
        if not (ppid.isdigit() and start.isdigit()):
            continue
        found[int(entry.name)] = ProcEntry(
            head.partition("(")[2],
            int(ppid),
            int(start),
            owner,
            fields[STATE_INDEX],
            int(pgrp) if pgrp.isdigit() else -1,
        )
    return found


def soffice_entries(table: Mapping[int, ProcEntry], uid: int | None = None) -> dict[tuple[int, int], bool]:
    """(pid, start time) -> is a start, for every soffice.bin of uid (any uid when None) in table.

    A soffice.bin whose parent is soffice.bin is a forked helper before its
    exec, not a start (see PROC). A parent /proc no longer shows is no
    soffice.bin as far as this scan knows, so that process counts.
    """
    found: dict[tuple[int, int], bool] = {}
    for pid, entry in table.items():
        if entry.name != SOFFICE_BIN or (uid is not None and entry.owner != uid):
            continue
        parent = table.get(entry.ppid)
        found[(pid, entry.start)] = parent is None or parent.name != SOFFICE_BIN
    return found


def soffice_processes(proc: Path = PROC, uid: int | None = None) -> set[tuple[int, int]]:
    """(pid, start time) of every soffice.bin start of uid (any uid when None) that /proc shows now."""
    return {key for key, start in soffice_entries(read_proc(proc), uid).items() if start}


def _token(text: str) -> str:
    """One blank-free word for a key=value line; - when empty."""
    return re.sub(r"\s+", "_", text.strip()) or "-"


def exe_basename(proc: Path, pid: int) -> str:
    """The file name of /proc/<pid>/exe, or - when it cannot be read (gone, a zombie, another uid)."""
    try:
        return _token(Path(os.readlink(proc / str(pid) / "exe")).name)
    except OSError:
        return "-"


def cmdline_head(proc: Path, pid: int) -> str:
    """The first CMDLINE_ARGS arguments of /proc/<pid>/cmdline, comma joined and cut; - when empty or unreadable."""
    try:
        raw = (proc / str(pid) / "cmdline").read_bytes()
    except OSError:
        return "-"
    args = [arg.decode("utf-8", errors="replace") for arg in raw.split(b"\0") if arg][:CMDLINE_ARGS]
    return _token(",".join(args))[:CMDLINE_CHARS]


def cmdline_program(proc: Path, pid: int) -> str | None:
    """The first argument of /proc/<pid>/cmdline; None when unreadable or empty (a zombie has none)."""
    try:
        raw = (proc / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    first = raw.split(b"\0", 1)[0]
    return first.decode("utf-8", errors="replace") if first else None


def identity_reason(proc: Path, pid: int, entry: ProcEntry) -> str | None:
    """None for a soffice.bin with a program identity, else the reason it has none.

    Reasons: zombie, no_cmdline, other_cmdline, no_exe, other_exe.

    A zombie and a process in its exit have neither cmdline nor exe; a fork
    before its exec has both, but the parent rule (soffice_entries) catches it.
    """
    if entry.state in DEAD_STATES:
        return "zombie"
    program = cmdline_program(proc, pid)
    if program is None:
        return "no_cmdline"
    if program != SOFFICE_BIN_PATH:
        return "other_cmdline"
    exe = exe_basename(proc, pid)
    if exe == "-":
        return "no_exe"
    if exe != SOFFICE_BIN:
        return "other_exe"
    return None


def _chain(values: list[str]) -> str:
    return ">".join(values) or "-"


@dataclass(slots=True)
class StartTrack:
    """What the counter saw of one soffice.bin (pid, start time) over the block, counted or not."""

    first_ms: int
    first_ppid: int
    first_parent: str
    first_fork: bool
    exe: str
    cmdline: str
    pgrp: int
    ppids: list[str]
    names: list[str]
    states: list[str]
    counted_ms: int | None = None
    counted_ppid: int = 0
    counted_parent: str = "-"
    # Why a candidate (parent not soffice.bin) was not counted, each change in order.
    reasons: list[str] | None = None

    def refuse(self, reason: str) -> None:
        """Note why this candidate does not count at this scan (identity_reason)."""
        if self.reasons is None:
            self.reasons = []
        if not self.reasons or self.reasons[-1] != reason:
            self.reasons.append(reason)

    def note(self, entry: ProcEntry) -> None:
        """Append ppid, name and state when they differ from the last value seen."""
        for values, value in ((self.ppids, str(entry.ppid)), (self.names, entry.name), (self.states, entry.state)):
            if not values or values[-1] != value:
                values.append(value)


def detail_line(kind: str, pid: int, track: StartTrack) -> str:
    """The SOFFICE-START-DETAIL line of one candidate: counted=ja, or counted=nein with its reasons.

    ppid and parent_comm are those at the scan that counted it (first_ppid
    for one not counted); earlier_fork says whether an earlier scan saw the
    same process as a child of soffice.bin (then the parent went away before
    this scan, and the process was handed to another parent). ppids, names
    and states list each change seen until the block ended.
    """
    counted = track.counted_ms is not None
    ppid = track.counted_ppid if counted else track.first_ppid
    parent = track.counted_parent if counted else track.first_parent
    verdict = "counted=ja" if counted else f"counted=nein reason={_chain(track.reasons or [])}"
    return (
        f"SOFFICE-START-DETAIL kind={kind} {verdict} pid={pid} ppid={ppid} "
        f"parent_comm={_token(parent)} comm={_token(track.names[0])} exe_basename={track.exe} "
        f"cmdline_head={track.cmdline} first_seen_ms={track.first_ms} counted_ms={track.counted_ms} "
        f"pgrp={track.pgrp} first_ppid={track.first_ppid} first_parent_comm={_token(track.first_parent)} "
        f"earlier_fork={'ja' if track.first_fork else 'nein'} ppids={_chain(track.ppids)} "
        f"names={_token(_chain(track.names))} states={_chain(track.states)}"
    )


class StartCounter:
    """Counts the soffice.bin processes that appear while the block runs (a thread reads /proc).

    Besides the count it keeps a StartTrack of every soffice.bin it saw, so
    detail_lines can say what each counted start was and why a candidate did
    not count (sandbox run of 335a80f: three zombies, see identity_reason).
    """

    def __init__(self, proc: Path = PROC, uid: int | None = None, poll_s: float = POLL_S) -> None:
        self._proc, self._uid, self._poll_s = proc, uid, poll_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self.seen: set[tuple[int, int]] = set()
        self.tracks: dict[tuple[int, int], StartTrack] = {}
        self._before: set[tuple[int, int]] = set()
        self._started = time.monotonic()

    def _ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def _parent_name(self, table: Mapping[int, ProcEntry], ppid: int) -> str:
        parent = table.get(ppid)
        return "gone" if parent is None else parent.name

    def _scan(self) -> None:
        table = read_proc(self._proc)
        for key, start in soffice_entries(table, self._uid).items():
            if key in self._before:
                continue
            pid, entry = key[0], table[key[0]]
            track = self.tracks.get(key)
            if track is None:
                track = StartTrack(
                    first_ms=self._ms(),
                    first_ppid=entry.ppid,
                    first_parent=self._parent_name(table, entry.ppid),
                    first_fork=not start,
                    exe=exe_basename(self._proc, pid),
                    cmdline=cmdline_head(self._proc, pid),
                    pgrp=entry.pgrp,
                    ppids=[],
                    names=[],
                    states=[],
                )
                self.tracks[key] = track
            track.note(entry)
            if start and key not in self.seen:
                reason = identity_reason(self._proc, pid, entry)
                if reason is not None:
                    track.refuse(reason)
                    continue
                self.seen.add(key)
                track.counted_ms = self._ms()
                track.counted_ppid = entry.ppid
                track.counted_parent = self._parent_name(table, entry.ppid)
        # What became of a tracked process that no longer carries the name (an exec): its new name.
        for (pid, begun), track in self.tracks.items():
            entry = table.get(pid)
            if entry is not None and entry.start == begun and entry.name != SOFFICE_BIN:
                track.note(entry)

    def detail_lines(self, kind: str) -> list[str]:
        """One SOFFICE-START-DETAIL line per counted start and per refused candidate, in the order first seen.

        A fork that never left its soffice.bin parent is neither and gets no line.
        """
        shown = sorted(
            (track.first_ms, key[0], key)
            for key, track in self.tracks.items()
            if key in self.seen or track.reasons is not None
        )
        return [detail_line(kind, pid, self.tracks[key]) for _, pid, key in shown]

    def pgrps(self) -> set[int]:
        """The process groups of the counted starts (the oosplash group of a conversion)."""
        return {self.tracks[key].pgrp for key in self.seen}

    def _watch(self) -> None:
        while not self._stop.is_set():
            self._scan()
            self._stop.wait(self._poll_s)

    def __enter__(self) -> "StartCounter":
        self._started = time.monotonic()
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


def zombie_counts(table: Mapping[int, ProcEntry], pgrps: set[int], uid: int | None = None) -> tuple[int, int]:
    """Zombies of uid (any uid when None) inside the groups pgrps, and zombies of uid outside them."""
    inside = outside = 0
    for entry in table.values():
        if entry.state != "Z" or (uid is not None and entry.owner != uid):
            continue
        if entry.pgrp in pgrps:
            inside += 1
        else:
            outside += 1
    return inside, outside


def zombies_line(after_job: int, other: int, pgrps: set[int], subreaper: bool) -> str:
    """The ZOMBIES line: zombies of the job's group after convert() returned (a gate: 0), and all others of the uid."""
    groups = ",".join(str(group) for group in sorted(pgrps)) or "-"
    return (
        f"ZOMBIES after_job={after_job} pgrp={groups} other_uid_zombies={other} "
        f"subreaper={'ja' if subreaper else 'nein'}"
    )


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
    # As the server does at its start (main.harden_process): it is PID 1 of the
    # product container and a subreaper, so every orphan of a job comes back to
    # it and reap_group collects it. Here the server is PID 1 and pytest a
    # docker exec beside it; without this the orphans went to the server, which
    # never waits for a group it did not start (sandbox run of 335a80f).
    subreaper = become_subreaper()
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
    pgrps = counter.pgrps() | {track.pgrp for track in counter.tracks.values()}
    after_job, other_zombies = zombie_counts(read_proc(), pgrps, _uid())
    before_cleanup, after_cleanup = cleanups[-1] if cleanups else (["no-cleanup"], ["no-cleanup"])
    expected_pipe = predicted_pipe_name(soffice.command(source, outdir, JOB_ID), _uid())
    pipes = [entry for entry in before_cleanup if entry.startswith("OSL_PIPE_")]
    lines = [
        layer_line(result),
        starts_line("product", counter.n),
        *counter.detail_lines("product"),
        rest_line(before_cleanup, after_cleanup),
        zombies_line(after_job, other_zombies, pgrps, subreaper),
        f"PIPE-NAME predicted={'ja' if f'{expected_pipe}:sock' in pipes else 'nein'} seen={len(pipes)}",
    ]
    # A string message: pytest cuts the repr of a list in the middle, a string it keeps whole.
    report = "\n".join(lines)
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
    assert counter.n == 1, report
    # No zombie of the job is left once convert() returned (reap_group with the server as subreaper).
    assert after_job == 0, report
    # The server cleaned up: nothing new in /tmp, the profile with its copy is gone, no socket is left.
    assert after_cleanup == [], report
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
    lines = [
        starts_line("control-fresh-unjailed", counter.n, f"exit={code} pdf={'ja' if pdf else 'nein'}"),
        *counter.detail_lines("control-fresh-unjailed"),
    ]
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    record_measurement("soffice_starts_control", {"n": counter.n, "exit": code, "pdf": pdf})
    assert counter.n >= 2, "\n".join(lines)


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


# The profiles whose product jail refuses connect() (owner 17.11.): a gate in
# the container. detect and ocr keep connect() and are only described.
CONNECT_REFUSED = ("soffice", "render", "precheck", "sanitize")


async def test_soffice_reaches_no_socket(capsys: pytest.CaptureFixture[str]) -> None:
    """SOCKET-CONNECT <who>=<ok|refused|absent> for every profile as it stands, and SOCKET-CONNECT-DENY.

    soffice, render, precheck and sanitize: the product jail, whose seccomp
    filter refuses connect() for every family: each must answer "refused
    EACCES" (owner decisions 17.11.). detect and ocr keep connect() for now:
    their answers describe the state (R2). SOCKET-CONNECT-DENY is the same
    probe in each profile with deny_connect on: every one must answer
    "refused EACCES", or the PROFILE-DENY-CONNECT measurement would not mean
    what it says.
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
    assert set(CONNECT_REFUSED) <= set(PROFILES), CONNECT_REFUSED
    for name in CONNECT_REFUSED:
        assert answers[name] == "refused EACCES", (name, answers)
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
    traced: bool = False

    def argv(self, out: Path) -> list[str]:
        args = [arg.replace(OUT, str(out)) for arg in self.args]
        return work_argv(*args) if self.python else args

    def trace(self, out: Path) -> Path | None:
        """The trace file profile_work.py writes into the folder of the run, for a traced work."""
        return out / TRACE_FILE if self.traced else None


def trace_line(work: Work, build: str, run: Mapping[str, object]) -> str:
    """The PROFILE-TRACE line: the MARK lines and the last stacks of one traced run."""
    return f"PROFILE-TRACE profile={work.profile} work={work.name} build={build} {run.get('trace') or '-'}"


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


def product_work_line(work: Work, product: Mapping[str, object]) -> str:
    """The PROFILE-WORK line: the work of a profile whose product jail already refuses connect()."""
    result, _, events = str(product["result"]).partition(" events=")
    return (
        f"PROFILE-WORK profile={work.profile} work={work.name} product_ok={_ja(product['ok'])} "
        f"result={result.removeprefix('result=')} events={events or '-'} tail={product['tail'] or '-'}"
    )


def absent_line(profile: str, name: str, reason: str) -> str:
    return f"PROFILE-DENY-CONNECT profile={profile} work={name} ok=- product_ok=- result={reason} events=- tail=-"


def really_ran(run: Mapping[str, object]) -> bool:
    """A result line came back and the jail did not fail (exit 71 or a usage error)."""
    failed_jail = (sandbox_jail.EXIT_LAYER_FAILED, sandbox_jail.EXIT_USAGE)
    return str(run["result"]).startswith("result=") and run["exit"] not in failed_jail


# -- why a run hangs: what the test sees of the child when its time is up --------------------

# Sandbox run of cfb428a: detect ran into 900 s on arm64 twice (product and
# deny-connect), with no line on stdout and nothing on stderr, while amd64
# needed seconds. The test now reads /proc of the child and the trace file of
# profile_work.py (MARK lines, faulthandler stacks) before it kills the group.
# 300 s: amd64 needs about 20 s per detect run (both runs and everything else
# in 44 s), so 300 s is 15 times that; arm64 failed at 900 s anyway, and with a
# stack every DETECT_DUMP_EVERY_S the dumps show whether it moves. Both runs
# together then take at most 10 instead of 30 minutes.
DETECT_TIMEOUT_S = 300.0
DETECT_DUMP_EVERY_S = 60.0
DUMP_SETTLE_S = 2.0
HARNESS_MARK = "HARNESS dump on timeout"
TRACE_FRAMES = 12
TRACE_CHARS = 4000
TOP_THREADS = 8
CLOCK_TICKS = 100  # sysconf(_SC_CLK_TCK) on Linux; only for the seconds in the line
# /proc/<pid>/stat after the ")": field 14 (utime) index 11, field 15 (stime) index 12.
UTIME_INDEX = 11
STIME_INDEX = 12
STATUS_KEYS = ("State", "Threads", "VmRSS", "VmHWM")
_FRAME = re.compile(r'^\s*File "(?P<path>[^"]*)", line (?P<line>\d+) in (?P<func>.*)$')
_NOT_PRINTABLE = re.compile(r"[^\x20-\x7e]")
COMMUNICATE_AFTER_KILL_S = 10.0


def _cpu_s(stat_text: str) -> float:
    fields = stat_text.rpartition(")")[2].split()
    try:
        return (int(fields[UTIME_INDEX]) + int(fields[STIME_INDEX])) / CLOCK_TICKS
    except (IndexError, ValueError):
        return -1.0


def proc_snapshot(pid: int, proc: Path = PROC) -> str:
    """State, threads, memory, CPU seconds and wchan of pid, and its busiest threads; - per field it cannot read.

    CPU seconds that grow from dump to dump mean work (slow), a flat value and
    a wchan like futex_wait mean a wait (a lock, a pool that never answers).
    """
    base = proc / str(pid)
    parts: list[str] = []
    try:
        status = (base / "status").read_text(encoding="ascii", errors="replace")
    except OSError:
        return "proc=gone"
    for line in status.splitlines():
        key, _, value = line.partition(":")
        if key in STATUS_KEYS:
            parts.append(f"{key.lower()}={_token(value)}")
    cpu = wchan = "-"
    with contextlib.suppress(OSError):
        cpu = f"{_cpu_s((base / 'stat').read_text(encoding='ascii')):.1f}"
    with contextlib.suppress(OSError):
        wchan = _token((base / "wchan").read_text(encoding="ascii"))
    parts += [f"cpu_s={cpu}", f"wchan={wchan}"]
    threads: list[tuple[float, str]] = []
    with contextlib.suppress(OSError):
        for task in (base / "task").iterdir():
            with contextlib.suppress(OSError):
                text = (task / "stat").read_text(encoding="ascii", errors="replace")
                name = text.partition("(")[2].rpartition(")")[0]
                state = text.rpartition(")")[2].split()[:1] or ["?"]
                wchan = "-"
                with contextlib.suppress(OSError):
                    wchan = (task / "wchan").read_text(encoding="ascii") or "-"
                threads.append((_cpu_s(text), f"{_token(name)}:{state[0]}:{_cpu_s(text):.1f}s:{_token(wchan)}"))
    threads.sort(reverse=True)
    parts.append(f"top_threads={','.join(entry for _, entry in threads[:TOP_THREADS]) or '-'}")
    return " ".join(parts)


def _short_path(path: str) -> str:
    """The part of a source path after site-packages (or its last two parts): enough to name the module."""
    head, marker, rest = path.partition("site-packages/")
    if marker:
        return rest
    return "/".join(Path(head).parts[-2:])


def condense_trace(text: str) -> str:
    """The MARK lines and the last stack dump of a trace file, as one line.

    The last dump starts after the last HARNESS_MARK or "Timeout (" header;
    each thread keeps its TRACE_FRAMES most recent frames as module:line func.
    """
    lines = text.splitlines()
    marks = [line.removeprefix("MARK ").strip() for line in lines if line.startswith("MARK ")]
    starts = _dump_starts(lines)
    threads = _dump_threads(lines[starts[-1] + 1 :] if starts else [], TRACE_FRAMES)
    text_out = f"marks={' ; '.join(marks) or '-'} dumps={len(starts)} last_dump={' || '.join(threads) or '-'}"
    return _NOT_PRINTABLE.sub("?", text_out)[:TRACE_CHARS]


def _dump_starts(lines: list[str]) -> list[int]:
    """The index of each dump header: a faulthandler timer dump or the harness mark before SIGUSR1."""
    return [index for index, line in enumerate(lines) if line.startswith((HARNESS_MARK, "Timeout ("))]


def _dump_threads(dump: list[str], frames_kept: int) -> list[str]:
    """Each thread of one dump as "<thread> < module:line func < ...", innermost first.

    frames_kept counts the thread name as one entry.

    A dump ends at the next MARK, FACTS or dump header line; faulthandler
    lists the most recent call first.
    """
    threads: list[str] = []
    frames: list[str] = []
    for line in dump:
        if line.startswith((HARNESS_MARK, "Timeout (", "MARK ", "FACTS ", "EXTRACT ")):
            break
        if line.startswith(("Thread ", "Current thread ")):
            if frames:
                threads.append(" < ".join(frames[:frames_kept]))
            frames = [line.split(" (")[0].replace("Current thread", "current")]
            continue
        match = _FRAME.match(line)
        if match is not None:
            frames.append(f"{_short_path(match['path'])}:{match['line']} {match['func'].strip()}")
    if frames:
        threads.append(" < ".join(frames[:frames_kept]))
    return threads


def read_trace(path: Path | None) -> str:
    """condense_trace of the file, or - when there is none."""
    if path is None:
        return "-"
    try:
        return condense_trace(path.read_text(encoding="ascii", errors="replace"))
    except OSError:
        return "-"


def _ask_for_a_dump(pid: int, trace: Path | None) -> None:
    """Mark the trace file and send SIGUSR1: profile_work.py's faulthandler writes the stacks once more."""
    if trace is not None:
        with contextlib.suppress(OSError), trace.open("a", encoding="ascii") as handle:
            handle.write(f"{HARNESS_MARK}\n")
    sigusr1 = getattr(signal, "SIGUSR1", None)
    if sigusr1 is not None:
        with contextlib.suppress(OSError):
            os.kill(pid, sigusr1)


async def _run_work(
    argv: list[str],
    profile: str,
    timeout_s: float,
    trace: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """exit, the result line of profile_work.py (or no-answer), the cleaned stderr tail, ok.

    On a timeout the tail is what /proc shows of the child and the condensed
    trace file (MARK lines, the last stacks), read before the group is killed.
    "trace" holds the condensed trace of every run that has one. env replaces
    the child environment of the profile (a measurement variant only).
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=dict(env) if env is not None else child.child_env(profile=profile),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    communicate = asyncio.ensure_future(process.communicate())
    try:
        out, err = await asyncio.wait_for(asyncio.shield(communicate), timeout=timeout_s)
    except TimeoutError:
        snapshot = proc_snapshot(process.pid)
        _ask_for_a_dump(process.pid, trace)
        await asyncio.sleep(DUMP_SETTLE_S)
        child._kill_group(process.pid)
        err = b""
        with contextlib.suppress(TimeoutError):
            _, err = await asyncio.wait_for(communicate, timeout=COMMUNICATE_AFTER_KILL_S)
        stderr = child.diagnostic_tail(err, child.TAIL_LINES) or "-"
        condensed = read_trace(trace)
        tail = f"{snapshot} stderr={stderr} trace={condensed}"
        return {
            "exit": None,
            "result": "result=fail:timeout events=-",
            "tail": tail,
            "ok": False,
            "trace": condensed,
        }
    finally:
        reap_group(process.pid)
    lines = [line for line in out.decode("ascii", errors="replace").splitlines() if line.startswith("result=")]
    result = lines[-1] if lines else f"no-answer exit={process.returncode}"
    return {
        "exit": process.returncode,
        "result": result,
        "tail": child.diagnostic_tail(err, child.TAIL_LINES),
        "ok": result.startswith("result=ok "),
        "trace": read_trace(trace),
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
        works.append(
            Work(
                "detect",
                "detect",
                ("detect", str(models), OUT, str(DETECT_DUMP_EVERY_S)),
                (str(models),),
                timeout_s=DETECT_TIMEOUT_S,
                traced=True,
            )
        )
    else:
        works.append(absent_line("detect", "detect", "no-models"))
    if tesseract is None:
        works.append(absent_line("ocr", "tesseract", "absent"))
    else:
        works.append(Work("ocr", "tesseract", (tesseract, str(png), f"{OUT}/text"), (str(png),), python=False))
    return works


def jails_for(profile: str) -> tuple[str, ...]:
    """Only the product jail where it already refuses connect(); else the product and the deny variant."""
    return ("product",) if PROFILES[profile].deny_connect else JAILS


async def test_each_profile_does_its_work_with_connect_denied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PROFILE-WORK for the profiles that refuse connect(), PROFILE-DENY-CONNECT for detect and ocr.

    render, precheck and sanitize refuse connect() in the product since
    17.11.: their work runs once, in the product jail, and must work (a gate).
    detect and ocr run twice in fresh folders: in the product jail of their
    profile and in the same jail with deny_connect, a measurement for R2; a
    switch is only safe where product_ok=ja and ok=ja. For every run the gate
    is that it really ran (a result line, no jail failure), so a broken jail
    or driver cannot pass as a measurement.
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
    failed: list[str] = []
    for work in works:
        if isinstance(work, str):
            lines.append(work)
            continue
        runs: dict[str, dict[str, object]] = {}
        for build in jails_for(work.profile):
            out = tmp_path / f"{work.profile}-{work.name}-{build}"
            out.mkdir()
            if not work.python:
                runs[build] = await _run_tesseract(work, out, build)
                continue
            make = jail_argv if build == "product" else deny_connect_argv
            command = make(work.profile, work.argv(out), read=work.read, write=(str(out),))
            runs[build] = await _run_work(command, work.profile, work.timeout_s, work.trace(out))
        if work.traced:
            lines += [trace_line(work, build, run) for build, run in runs.items()]
        if "deny" not in runs:
            lines.append(product_work_line(work, runs["product"]))
            if not runs["product"]["ok"]:
                failed.append(f"{work.profile}/{work.name}")
        else:
            lines.append(work_line(work, runs["product"], runs["deny"]))
        if "deny" in runs and not runs["product"]["ok"]:
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
    report = "\n".join(lines)
    assert not_run == [], report
    # The profiles that refuse connect() in the product still do their work.
    assert failed == [], report


# -- detect on arm64: measurement variants (sandbox run of 335a80f) ----------------------------

# arm64 stopped after gliner_loaded for 300 s, every stack in gliner2
# score_queries, one thread busy, stderr "Error in cpuinfo: failed to parse
# the list of present processors"; amd64 extracted in 0.4 s. Four runs of the
# same detect work, on both architectures, each a DETECT-VARIANT line and no
# gate beyond "it really ran": (a) without any jail, (b) the product jail
# plus a Landlock read right on /sys/devices/system/cpu (a diagnosis variant
# through jail_layers.py, never a product rule), (c) the product jail with
# OMP_NUM_THREADS and torch.set_num_threads fixed to os.cpu_count(), (d) the
# product jail unchanged. 120 s each, so a hang costs at most eight minutes.
#
# Sandbox run of c2ac178 (CI 44126012119): amd64 extracted in about 230 ms in
# all four; arm64 hung 120 s in all four, the unjailed one too (cpuinfo=ok,
# /sys readable), one thread at 100 % CPU, cpu_cap=SVE128. Jail and /sys are
# out. Common to all: OMP_THREAD_LIMIT=1 from SAFE_ENV. Two more variants
# without it, (e) unjailed and (f) the product jail; their environment is
# SAFE_ENV minus OMP_THREAD_LIMIT, nothing else. A hang there costs two more
# times 120 s. Every variant dumps the stacks of all threads every
# VARIANT_DUMP_EVERY_S (30, 60, 90 s, and once more from the harness at
# 120 s), each dump a DETECT-STACK line.
VARIANT_TIMEOUT_S = 120.0
VARIANT_DUMP_EVERY_S = 30.0
STACK_FRAMES = 7
STACK_CHARS = 2500
SYS_CPU = "/sys/devices/system/cpu"
VARIANT_TAIL_CHARS = 1500
FACT_KEYS = (
    "interop",
    "cpu_count",
    "affinity",
    "present",
    "possible",
    "online",
    "cpuinfo",
    "omp_num_threads",
    "omp_thread_limit",
)


@dataclass(frozen=True, slots=True)
class DetectVariant:
    """One way to run the detect work: its jail, its thread setting (profile_work.py detect <threads>), its env."""

    name: str
    jail: str
    threads: str = "-"
    omp_limit: bool = True


DETECT_VARIANTS = (
    DetectVariant("unjailed", "none"),
    DetectVariant("jailed-sys-cpu-read", "sys-cpu"),
    DetectVariant("jailed-threads-cpu", "product", "cpu"),
    DetectVariant("jailed-product", "product"),
    DetectVariant("unjailed-no-omp-limit", "none", omp_limit=False),
    DetectVariant("jailed-product-no-omp-limit", "product", omp_limit=False),
)


def variant_env(variant: DetectVariant) -> dict[str, str]:
    """The child environment of detect; without OMP_THREAD_LIMIT for a variant with omp_limit=False."""
    env = child.child_env(profile="detect")
    if not variant.omp_limit:
        env.pop("OMP_THREAD_LIMIT", None)
    return env


def stack_lines(name: str, text: str) -> list[str]:
    """One DETECT-STACK line per stack dump in a trace: when (at=), how many threads, the innermost frames of each."""
    lines = text.splitlines()
    starts = _dump_starts(lines)
    out: list[str] = []
    for number, index in enumerate(starts, start=1):
        header = lines[index]
        at = "harness" if header.startswith(HARNESS_MARK) else header.partition("(")[2].partition(")")[0] or "-"
        threads = _dump_threads(lines[index + 1 :], STACK_FRAMES)
        line = (
            f"DETECT-STACK name={name} dump={number}/{len(starts)} at={at} threads={len(threads)} "
            f"stacks={' || '.join(threads) or '-'}"
        )
        out.append(_NOT_PRINTABLE.sub("?", line)[:STACK_CHARS])
    return out


def variant_argv(variant: DetectVariant, models: Path, out: Path) -> list[str]:
    """The command of one variant; sys-cpu is the product jail of detect plus read=SYS_CPU through the driver."""
    argv = work_argv("detect", str(models), str(out), str(VARIANT_DUMP_EVERY_S), variant.threads)
    if variant.jail == "none":
        return argv
    product = jail_argv("detect", argv, read=(str(models),), write=(str(out),))
    if variant.jail == "product":
        return product
    if variant.jail == "sys-cpu":
        return [sys.executable, "-I", str(DRIVER), "variant", f"read={SYS_CPU},seccomp", *product[4:]]
    msg = f"unknown jail {variant.jail!r}"
    raise ValueError(msg)


def trace_facts(text: str) -> dict[str, str]:
    """The last FACTS line of a trace as a dict, plus ms_extract from the EXTRACT line ("-" when missing)."""
    facts: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("FACTS "):
            pairs = (part.partition("=") for part in line.split()[1:] if "=" in part)
            facts = {key: value for key, _, value in pairs}
    extract = [line.split("ms=", 1)[1].strip() for line in text.splitlines() if line.startswith("EXTRACT ms=")]
    facts["ms_extract"] = extract[-1] if extract else "-"
    return facts


def variant_line(variant: DetectVariant, run: Mapping[str, object], trace_text: str) -> str:
    """The DETECT-VARIANT line of one run."""
    facts = trace_facts(trace_text)
    result = str(run["result"]).partition(" events=")[0].removeprefix("result=")
    tail = "-" if run["ok"] else _NOT_PRINTABLE.sub("?", str(run["tail"] or "-"))[:VARIANT_TAIL_CHARS]
    extra = " ".join(f"{key}={facts.get(key, '-')}" for key in FACT_KEYS)
    return (
        f"DETECT-VARIANT name={variant.name} ok={_ja(run['ok'])} ms_extract={facts['ms_extract']} "
        f"threads={facts.get('torch_threads', '-')} cpu_cap={facts.get('cpu_cap', '-')} {extra} "
        f"result={result} tail={tail}"
    )


async def test_detect_variants_measure_the_arm64_hang(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """DETECT-VARIANT and DETECT-STACK lines for (a) to (f); a measurement, the only gate is that each really ran.

    Not a gate on purpose: arm64 detect hangs (deferred-items, 02-16); a real
    gate for arm64 detect is due before the release.
    """
    models = Path(os.environ.get("PII_MODELS", "/models"))
    if not (models / "gliner2").is_dir():
        pytest.skip("no models for detect")
    lines: list[str] = []
    stacks: list[str] = []
    measured: dict[str, object] = {}
    not_run: list[str] = []
    for variant in DETECT_VARIANTS:
        out = tmp_path / f"detect-{variant.name}"
        out.mkdir()
        trace = out / TRACE_FILE
        argv = variant_argv(variant, models, out)
        run = await _run_work(argv, "detect", VARIANT_TIMEOUT_S, trace, variant_env(variant))
        text = ""
        with contextlib.suppress(OSError):
            text = trace.read_text(encoding="ascii", errors="replace")
        lines.append(variant_line(variant, run, text))
        stacks += stack_lines(variant.name, text)
        measured[variant.name] = {**run, "facts": trace_facts(text)}
        if not really_ran(run):
            not_run.append(variant.name)
    with capsys.disabled():
        print()
        for line in [*lines, *stacks]:
            print(line)
    record_measurement("detect_variants", measured)
    assert not_run == [], "\n".join(lines)


# -- torch on each architecture: facts and a micro benchmark in the detect child env ----------

# What the hang is made of, without the models: the TORCH-FACTS line of
# profile_work.py torchbench, once unjailed and once in the product jail of
# detect, both with SAFE_ENV (OMP_THREAD_LIMIT=1). Each step has
# BENCH_STEP_S in the child (a hung step writes ms=timeout, the next one
# still runs); BENCH_TIMEOUT_S covers the torch import and all steps. Normal
# cost: a few seconds per run; two hung score_queries steps add 20 s per run.
# The steps run in their own threads: torch.set_flush_denormal and the
# OpenMP pool are per thread, which is what OMP_THREAD_LIMIT=1 leaves anyway.
BENCH_ENVS = ("unjailed", "jailed-product")
BENCH_TIMEOUT_S = 60.0 + len(BENCH_STEPS) * BENCH_STEP_S
TORCH_FACT_KEYS = (
    "torch",
    "aten_threads",
    "aten_interop",
    "omp_max_threads",
    "mkl_max_threads",
    "hw_concurrency",
    "backend",
    "openmp",
    "mkldnn_version",
    "num_threads",
    "interop",
    "mkldnn",
    "acl",
    "config_acl",
    "mkl",
    "omp_avail",
    "cpu_cap",
    "omp_thread_limit",
    "omp_num_threads",
)
# Step of torchbench and the key of its timing in the TORCH-FACTS line.
TORCH_TIMINGS = (
    ("matmul", "matmul512_x20_ms"),
    ("score_queries", "score_queries_x20_ms"),
    ("score_queries_ftz", "score_queries_ftz_x20_ms"),
)


def bench_argv(env: str, out: Path) -> list[str]:
    """profile_work.py torchbench unjailed, or in the product jail of detect with out as its only write path."""
    argv = work_argv("torchbench", str(out))
    if env == "unjailed":
        return argv
    if env == "jailed-product":
        return jail_argv("detect", argv, write=(str(out),))
    msg = f"unknown bench env {env!r}"
    raise ValueError(msg)


def bench_values(text: str) -> dict[str, str]:
    """The BENCH lines of torch-bench.txt as one dict: the facts keys, <step>=<ms>, first ms and ftz of the steps."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("BENCH "):
            continue
        pairs: dict[str, str] = {}
        for part in line.split()[1:]:
            key, sep, value = part.partition("=")
            if sep:
                pairs[key] = value
        step = pairs.pop("step", "-")
        if step == "facts":
            values.update(pairs)
        elif step in BENCH_STEPS:
            values[step] = pairs.get("ms", "-")
            if "first_ms" in pairs:
                values[f"{step}_first_ms"] = pairs["first_ms"]
            if "ftz" in pairs:
                values["ftz"] = pairs["ftz"]
    return values


def torch_facts_line(env: str, arch: str, run: Mapping[str, object], text: str) -> str:
    """The TORCH-FACTS line of one bench run; - for every value the run did not write."""
    values = bench_values(text)
    result = str(run["result"]).partition(" events=")[0].removeprefix("result=")
    facts = " ".join(f"{key}={values.get(key, '-')}" for key in TORCH_FACT_KEYS)
    timings = " ".join(
        f"{key}={values.get(step, '-')} {step}_first_ms={values.get(f'{step}_first_ms', '-')}"
        if step != "matmul"
        else f"{key}={values.get(step, '-')}"
        for step, key in TORCH_TIMINGS
    )
    tail = "-" if run["ok"] else _NOT_PRINTABLE.sub("?", str(run["tail"] or "-"))[:VARIANT_TAIL_CHARS]
    return (
        f"TORCH-FACTS env={env} arch={arch} ok={_ja(run['ok'])} result={result} {facts} {timings} "
        f"ftz={values.get('ftz', '-')} tail={tail}"
    )


async def test_torch_facts_and_a_micro_benchmark_per_architecture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TORCH-FACTS unjailed and in the product jail of detect; a measurement, the gate is only that it really ran."""
    lines: list[str] = []
    measured: dict[str, object] = {}
    not_run: list[str] = []
    for env in BENCH_ENVS:
        out = tmp_path / f"torchbench-{env}"
        out.mkdir()
        run = await _run_work(bench_argv(env, out), "detect", BENCH_TIMEOUT_S)
        text = ""
        with contextlib.suppress(OSError):
            text = (out / BENCH_FILE).read_text(encoding="ascii", errors="replace")
        lines.append(torch_facts_line(env, platform.machine(), run, text))
        measured[env] = {**run, "bench": bench_values(text)}
        if not really_ran(run):
            not_run.append(env)
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    record_measurement("torch_facts", measured)
    assert not_run == [], "\n".join(lines)


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
