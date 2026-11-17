"""DOCX to PDF through the real LibreOffice in the jail of the "soffice" profile (plan 02-08, 02-16).

Runs only inside the test stage of the image (sandbox.yml, -m container): the
development machine has neither LibreOffice nor Docker. The DOCX is written
here with the standard library, so the test needs no file outside the image.

HaRP run 44015648619 showed the regression: with the jail of 02-08 soffice
ended after 249 ms and every DOCX job failed with render_failed. Sandbox runs
of 7e3c909 and 11fb9f9 put the break on Landlock and on /tmp. Round 2 (sandbox
run of 4ee9c31, Landlock ABI 8, amd64 and arm64 alike) named the one right:
with grant=/tmp:REMOVE_FILE soffice converts, with write=/tmp minus REMOVE_FILE
it does not; HOME, XDG, dconf and gsettings change nothing. Every red run left
/tmp/OSL_PIPE_10001_SingleOfficeIPC_* behind. Round 2 is evaluated and gone.

Round 3 (this file, owner decision 17.11.: measure first, test only, nothing
opened in the product) asks two questions.

1. How dangerous is REMOVE_FILE on /tmp? A stand-in made by this test (a
   listening socket with owner and mode of the HaRP socket, a file, a file in
   a subfolder) is removed by a child in the soffice jail, with and without
   the right. The real HaRP socket is never named. Lines:

    TMP-FACTS uid=<test uid> tmp=<uid>:<gid>:<mode> sticky=<ja|nein> exapp=<uid>:<gid>:<mode>:<type> \
access_w=<path>:<answer in the product jail>,...
    UNLINK-RISK target=<socket-copy|file|file-in-subdir> jail=<none|product|grant> result=<ok|EACCES|EPERM|...> \
like_exapp=<ja|nein|->

2. Can the pipe leave /tmp, so no right on /tmp is needed at all? The
   LibreOffice sources (25.2.3.2) say: sal/osl/unx/pipe.cxx picks /tmp when
   access(/tmp, W_OK) says writable, else /var/tmp, else the bootstrap
   variable OSL_SOCKET_PATH; when the socket file exists and connect() fails,
   it unlinks it before bind(). A fresh profile makes soffice.bin restart once
   (oosplash loop, EXITHELPER_NORMAL_RESTART): the first process cannot unlink
   its socket on exit, the second finds it, cannot unlink it and ends with a
   pipe error. Each candidate runs in the full product jail without any extra
   right:

    SOFFICE-LAYER variant=<name>[/<step>] exit=... pdf=<ja|nein> ms=... path=<ja|nein|-> clean=...
    SOFFICE-LAYER env=<name> exit=... pdf=<ja|nein> ms=... clean=...

Other lines: LANDLOCK-ABI, SOFFICE-TAIL (cleaned stderr/stdout tail),
SOFFICE-TMPNEW (paths new in /tmp after the run, names only) and
SOCKET-CONNECT (connect() to the HaRP socket, a gate for soffice).

Layers of test_diagnosis_soffice_layer_by_layer: 1-env-only (no jail, emptied
environment, own process group), 2-limits (rlimits, no_new_privs), 3-landlock
(plus Landlock), 4-seccomp (plus seccomp: the product).

Every run starts on a clean /tmp: what earlier runs left there (.cache,
.config, dconf and soffice remains, any own hidden entry new since the test
began) is removed first. Variants and environment changes are measurements in
the test run, never rules of the product; they bypass child.child_env on
purpose.
"""

import asyncio
import contextlib
import os
import shutil
import socket
import stat
import sys
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pymupdf
import pytest

from pii_redaction_backend.sandbox.jail import jail_argv
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
LAYER_TIMEOUT_S = 90.0
HYPOTHESIS_READ = ("/proc", "/dev/shm")  # noqa: S108 - read only, test only, a hypothesis
# The jailed layers first: an unjailed run may leave files in /tmp (it may
# write there), and none of them must be there for a jailed run.
LAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("4-seccomp", ()),
    ("4-seccomp+proc-shm", HYPOTHESIS_READ),
    ("3-landlock", ()),
    ("2-limits", ()),
    ("1-env-only", ()),
)
TMP = Path("/tmp")  # noqa: S108 - the folder the diagnosis cleans and lists, test only
# What soffice, dconf and fontconfig may leave in /tmp with HOME=/tmp; removed
# before every run (entries of this uid only).
CLEAN_NAMES = frozenset({".cache", ".config", ".local", ".dbus", ".fontconfig", ".fonts", ".pki"})
CLEAN_GLOBS = ("dconf*", "OSL_PIPE_*", "lo-*", "*.tmp")
# Paths below a job profile are listed in SOFFICE-TMPNEW at most this deep.
PROFILE_DEPTH = 3
TMPNEW_MAX = 40

# soffice.command: everything up to and including -env:UserInstallation comes
# before this index; the extra options of a step go here, the document after.
PROFILE_ARG_END = 7
INIT_ONLY = "--terminate_after_init"
HARP_SOCKET = "/tmp/exapp.sock"  # noqa: S108 - the HaRP socket path, never removed by this test


@dataclass(frozen=True, slots=True)
class Step:
    """One soffice start of a round 3 candidate.

    layer: "4-seccomp" (the product jail), "variant:<spec>" or "1-env-only".
    args: extra soffice options before --convert-to; "@name" in a value is a
    fresh 0700 folder inside the job profile. env: extra environment, "@name"
    likewise. init_only: --terminate_after_init without a document (warms the
    profile, converts nothing). read: more readable paths (the hypothesis
    layer of the layer diagnosis).
    """

    layer: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    init_only: bool = False
    read: tuple[str, ...] = ()


PRODUCT = "4-seccomp"
GRANT_REMOVE = "seccomp,grant=/tmp:REMOVE_FILE"
VAR_TMP = "seccomp,read=/tmp,write=/var/tmp"

# Round 3, part 2: one candidate per entry, each on a clean /tmp and with its
# own job profile. Controls first and last. A candidate with two steps keeps
# its job profile between them; the server removes the pipe socket after every
# step, as the product does (soffice._remove_ipc_sockets).
CANDIDATES: tuple[tuple[str, tuple[Step, ...]], ...] = (
    # Control: the product, red in round 2.
    ("variant=seccomp", (Step("variant:seccomp"),)),
    # Control: the product plus REMOVE_FILE on /tmp, green in round 2.
    (f"variant={GRANT_REMOVE}", (Step(f"variant:{GRANT_REMOVE}"),)),
    # /var/tmp writable, /tmp read only: pipe.cxx asks access(/tmp, W_OK) first.
    (f"variant={VAR_TMP}", (Step(f"variant:{VAR_TMP}"),)),
    # OSL_SOCKET_PATH: the bootstrap fallback of pipe.cxx, as -env: option.
    ("variant=osl-socket-path", (Step(PRODUCT, args=("-env:OSL_SOCKET_PATH=@ipc",)),)),
    # LIBO_FLATPAK: oosplash skips the pipe, soffice.bin takes D-Bus (if built with it).
    ("env=libo-flatpak", (Step(PRODUCT, env={"LIBO_FLATPAK": "1"}),)),
    # The same conversion twice on one job profile: the second start has a profile.
    ("variant=warm-jailed-twice", (Step(PRODUCT), Step(PRODUCT))),
    # The profile warmed in the product jail without a document, then the conversion.
    ("variant=warm-init-jailed", (Step(PRODUCT, init_only=True), Step(PRODUCT))),
)
# Warmed outside any jail without a document, copied into the job profile,
# then converted in the product jail (test only: where a template could come from).
TEMPLATE_LABEL = "variant=warm-template-unjailed"
CONTROL_LABEL = "env=control-1-env-only"

# Round 3, part 1: the stand-ins a child tries to remove, and the jails it runs in.
UNLINK_PREFIX = "pii-unlink-probe"
UNLINK_TARGETS = ("socket-copy", "file", "file-in-subdir")
UNLINK_JAILS = ("none", "product", "grant")
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


async def test_a_docx_becomes_a_pdf_in_the_soffice_jail(tmp_path: Path) -> None:
    source = _docx(tmp_path / "probe.docx")
    outdir = tmp_path / "pdf"
    started = time.monotonic()

    try:
        pdf = await soffice.convert(source, outdir, "990001")
    except child.ChildFailed as failure:
        pytest.fail(
            f"soffice failed: exit {failure.exit_code}, signal {failure.signal}, stderr {failure.stderr_tail!r}"
        )
    record_measurement("soffice_docx_ms", int((time.monotonic() - started) * 1000))

    with pymupdf.open(pdf) as document:
        assert document.page_count == 1
        assert MARKER in document[0].get_text()
    # The profile with its temporary folder is gone, and no socket is left in /tmp.
    assert _leftovers("990001") == []


def _leftovers(job_id: str) -> list[str]:
    root = Path(soffice.PROFILE_ROOT)
    found = [path.name for path in root.glob(soffice.IPC_SOCKET_GLOB)]
    return found + ([f"lo-{job_id}"] if (root / f"lo-{job_id}").exists() else [])


# -- the layer diagnosis (plan 02-16) -------------------------------------------------------


def _argv(layer: str, command: list[str], read: tuple[str, ...], write: tuple[str, ...]) -> list[str]:
    """The start of one run: the product jail, a partial or variant jail of jail_layers.py, or no jail."""
    if layer == "1-env-only":
        return command
    product = jail_argv("soffice", command, read=read, write=write)
    if layer.startswith("4-seccomp"):
        return product
    # product[4:] is what jail.main takes: profile, paths, --, command.
    if layer.startswith("variant:"):
        return [sys.executable, "-I", str(DRIVER), "variant", layer.removeprefix("variant:"), *product[4:]]
    partial = layer.split("-", 1)[1]
    return [sys.executable, "-I", str(DRIVER), "layers", partial, *product[4:]]


def _own(path: Path) -> bool:
    if sys.platform == "win32":
        return False
    with contextlib.suppress(OSError):
        return path.lstat().st_uid == os.getuid()
    return False


def _remove(path: Path) -> None:
    with contextlib.suppress(OSError):
        if stat.S_ISDIR(path.lstat().st_mode):
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()


def cleanable(name: str, baseline: frozenset[str] | None) -> bool:
    """An entry of /tmp a run may have left: a known name, or (with a baseline) a hidden one new since the test began.

    Only hidden new entries (what a program with HOME=/tmp makes), so nothing
    the server process of the same uid keeps in /tmp is touched.
    """
    if name.startswith("pytest-of-"):
        return False
    if name in CLEAN_NAMES or any(PurePosixPath(name).match(pattern) for pattern in CLEAN_GLOBS):
        return True
    return baseline is not None and name.startswith(".") and name not in baseline


def clean_tmp(baseline: frozenset[str] | None = None) -> list[str]:
    """Remove what earlier runs left in /tmp (own entries only) and return the removed names."""
    removed: list[str] = []
    if not TMP.is_dir():
        return removed
    for entry in sorted(TMP.iterdir()):
        if _own(entry) and cleanable(entry.name, baseline):
            _remove(entry)
            removed.append(entry.name)
    return removed


def _baseline() -> frozenset[str]:
    """Clean the known names once, then remember what /tmp holds: that stays (HaRP socket, pytest)."""
    clean_tmp()
    return frozenset(entry.name for entry in TMP.iterdir()) if TMP.is_dir() else frozenset()


def tmp_snapshot(root: Path = TMP) -> frozenset[str]:
    """Every path below root (names only, no symlink followed), the pytest folders left out."""
    found: set[str] = set()
    for folder, dirs, files in os.walk(root, onerror=lambda _error: None):
        if folder == str(root):
            dirs[:] = [name for name in dirs if not name.startswith("pytest-of-")]
        found.update(f"{folder}/{name}" for name in (*dirs, *files))
    return frozenset(found)


def tmp_new(before: frozenset[str], after: frozenset[str], root: Path = TMP) -> list[str]:
    """The new paths, below a job profile (lo-<id>) cut to PROFILE_DEPTH levels."""
    shown: set[str] = set()
    for path in after - before:
        parts = PurePosixPath(path).relative_to(PurePosixPath(root.as_posix())).parts
        if parts and parts[0].startswith("lo-"):
            parts = parts[:PROFILE_DEPTH]
        shown.add("/".join((root.as_posix(), *parts)))
    return sorted(shown)


def fill(profile: Path, value: str) -> str:
    """A value of a step; "@name" (whole value or after "=") becomes a fresh 0700 folder inside the job profile."""
    head, sep, tail = value.rpartition("=")
    name = tail if sep else value
    if not name.startswith("@"):
        return value
    folder = profile / name[1:]
    folder.mkdir(mode=0o700, exist_ok=True)
    return f"{head}{sep}{folder}"


def env_for(profile: Path, changes: Mapping[str, str]) -> dict[str, str]:
    """The values of one env change; "@name" becomes a fresh 0700 folder inside the job profile."""
    return {key: fill(profile, value) for key, value in changes.items()}


def step_command(step: Step, source: Path, outdir: Path, job_id: str, profile: Path) -> list[str]:
    """The soffice command of one step: the product command with the step's options before the document part."""
    base = soffice.command(source, outdir, job_id)
    head, tail = base[:PROFILE_ARG_END], base[PROFILE_ARG_END:]
    extra = [fill(profile, value) for value in step.args]
    if step.init_only:
        return [*head, *extra, INIT_ONLY]
    return [*head, *extra, *tail]


def has_pdf(outdir: Path) -> bool:
    return any(outdir.glob("*.pdf"))


def _drop_pdfs(outdir: Path) -> None:
    for old in outdir.glob("*.pdf"):
        old.unlink()


async def _start(step: Step, source: Path, outdir: Path, job_id: str, profile: Path, env: dict[str, str]) -> dict:
    """One soffice start of a step; the PDFs of earlier steps are removed first."""
    _drop_pdfs(outdir)
    command = step_command(step, source, outdir, job_id, profile)
    argv = _argv(step.layer, command, (str(source), *step.read), (str(outdir), str(profile)))
    full_env = child.child_env(env, profile="soffice")
    # Test only: an env change bypasses the allowlist of child_env on purpose.
    full_env.update(env_for(profile, step.env))
    before = tmp_snapshot()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=outdir,
        env=full_env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    started = time.monotonic()
    out, err, code = b"", b"", None
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=LAYER_TIMEOUT_S)
        code = process.returncode
    except TimeoutError:
        child._kill_group(process.pid)
        await process.wait()
    finally:
        reap_group(process.pid)
    return {
        "exit": "timeout" if code is None else code,
        "signal": -code if code is not None and code < 0 else None,
        "pdf": has_pdf(outdir),
        "ms": int((time.monotonic() - started) * 1000),
        "stderr": child.diagnostic_tail(err, child.SOFFICE_TAIL_LINES),
        "stdout": child.diagnostic_tail(out, child.SOFFICE_TAIL_LINES),
        "clean": [],
        "tmp_new": tmp_new(before, tmp_snapshot()),
    }


def _fresh_job(
    job_id: str, tmp_path: Path, baseline: frozenset[str], seed: Path | None
) -> tuple[Path, list[str], Path, dict[str, str]]:
    """Output folder, a clean /tmp (the removed names), the job profile (seeded) and its environment."""
    outdir = tmp_path / f"out-{job_id}"
    outdir.mkdir()
    removed = clean_tmp(baseline)
    soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    profile, env = soffice.prepare_profile(job_id)
    if seed is not None:
        shutil.copytree(seed, profile, symlinks=True, dirs_exist_ok=True)
    return outdir, removed, profile, env


async def _run_steps(
    number: int,
    steps: tuple[Step, ...],
    source: Path,
    tmp_path: Path,
    *,
    baseline: frozenset[str],
    seed: Path | None = None,
    export_to: Path | None = None,
) -> list[dict]:
    """The steps on one job profile and a clean /tmp; the server removes the pipe socket after every step.

    seed is copied into the fresh job profile first; export_to receives a
    copy of the job profile after the last step (a template, test only).
    """
    job_id = str(990100 + number)
    outdir, removed, profile, env = _fresh_job(job_id, tmp_path, baseline, seed)
    root = Path(soffice.PROFILE_ROOT)
    results: list[dict] = []
    try:
        for step in steps:
            results.append(await _start(step, source, outdir, job_id, profile, env))
            soffice._remove_ipc_sockets(root)
        if export_to is not None:
            shutil.copytree(profile, export_to, symlinks=True)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        soffice._remove_ipc_sockets(root)
    results[0]["clean"] = removed
    return results


def tmpnew_line(label: str, new: list[str]) -> str:
    shown = " ".join(new[:TMPNEW_MAX])
    more = f" +{len(new) - TMPNEW_MAX} more" if len(new) > TMPNEW_MAX else ""
    return f"SOFFICE-TMPNEW {label} n={len(new)} {shown}{more}".rstrip()


def _print_run(label: str, result: dict, suffix: str = "") -> None:
    removed = result["clean"]
    new = result["tmp_new"]
    assert isinstance(removed, list)
    assert isinstance(new, list)
    print(
        f"\nSOFFICE-LAYER {label} exit={result['exit']} signal={result['signal']} "
        f"pdf={'ja' if result['pdf'] else 'nein'} ms={result['ms']}{suffix} clean={','.join(removed) or '-'}"
    )
    print(f"SOFFICE-TAIL {label} stderr: {result['stderr']} || stdout: {result['stdout']}")
    print(tmpnew_line(label, new))


async def test_diagnosis_soffice_layer_by_layer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _docx(tmp_path / "probe.docx")
    baseline = _baseline()
    results: dict[str, dict] = {}
    for number, (layer, extra_read) in enumerate(LAYERS):
        name = f"{layer}/plain"
        steps = (Step(layer, read=extra_read),)
        results[name] = (await _run_steps(number, steps, source, tmp_path, baseline=baseline))[0]
        # Outside the capture, so the lines stand in the job log of a passing run, too.
        with capsys.disabled():
            _print_run(name, results[name])
    record_measurement("soffice_layers", results)

    # Positive control: without any jail soffice converts the same file with
    # the job profile environment; otherwise the diagnosis says nothing.
    assert results["1-env-only/plain"]["pdf"], results["1-env-only/plain"]


async def _driver(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(DRIVER),
        *args,
        env=child.child_env(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await asyncio.wait_for(process.communicate(), timeout=30)
    return out.decode("ascii", errors="replace").strip()


def path_state(label: str) -> str:
    """ja or nein when the variant names paths (do they exist in the image?), - otherwise."""
    if not label.startswith("variant="):
        return "-"
    spec = label.removeprefix("variant=")
    paths = [part.split("=", 1)[1].split(":", 1)[0] for part in spec.split(",") if "=" in part]
    if not paths:
        return "-"
    return "ja" if all(Path(path).exists() for path in paths) else "nein"


def step_labels(label: str, count: int) -> list[str]:
    """The label of each step: the label itself for one step, label/1, label/2, ... for more."""
    return [label] if count == 1 else [f"{label}/{index}" for index in range(1, count + 1)]


async def test_diagnosis_round_3_the_pipe_without_a_right_on_tmp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each candidate of CANDIDATES in the product jail without an extra right; controls first and last."""
    source = _docx(tmp_path / "probe.docx")
    abi_line = await _driver("abi")
    baseline = _baseline()
    with capsys.disabled():
        print(f"\nLANDLOCK-ABI {abi_line or 'no-answer'}")
    start = len(LAYERS)
    results: dict[str, dict] = {}

    def show(label: str, runs: list[dict]) -> None:
        for name, result in zip(step_labels(label, len(runs)), runs, strict=True):
            results[name] = result
            with capsys.disabled():
                _print_run(name, result, f" path={path_state(label)}" if label.startswith("variant=") else "")

    for number, (label, steps) in enumerate(CANDIDATES, start=start):
        show(label, await _run_steps(number, steps, source, tmp_path, baseline=baseline))

    # The template: warmed without a jail and without a document, then copied.
    number = start + len(CANDIDATES)
    template = tmp_path / "template"
    warm = (Step("1-env-only", init_only=True),)
    made = await _run_steps(number, warm, source, tmp_path, baseline=baseline, export_to=template)
    show(f"{TEMPLATE_LABEL}/make", made)
    converted = await _run_steps(number + 1, (Step(PRODUCT),), source, tmp_path, baseline=baseline, seed=template)
    show(TEMPLATE_LABEL, converted)

    # Positive control on the same clean /tmp: without a jail soffice converts.
    control = await _run_steps(number + 2, (Step("1-env-only"),), source, tmp_path, baseline=baseline)
    show(CONTROL_LABEL, control)
    record_measurement("soffice_round_3", {"abi": abi_line, "runs": results})
    assert results[CONTROL_LABEL]["pdf"], results[CONTROL_LABEL]
    # The red control of round 2 must stay red, or the round measures something else.
    assert not results["variant=seccomp"]["pdf"], results["variant=seccomp"]


# -- round 3, part 1: how far does REMOVE_FILE on /tmp reach? --------------------------------


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
    if jail == "grant":
        return [sys.executable, "-I", str(DRIVER), "variant", GRANT_REMOVE, "soffice", "--", *probe]
    msg = f"unknown jail {jail!r}"
    raise ValueError(msg)


async def test_measure_whether_remove_file_on_tmp_reaches_files_of_the_server(
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
                    _remove(path.parent)
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


async def test_measure_whether_a_jailed_child_reaches_the_harp_socket(capsys: pytest.CaptureFixture[str]) -> None:
    """SOCKET-CONNECT <who>=<ok|refused|absent>; for soffice a gate since the owner decision of 17.11.

    soffice: the product jail of the soffice profile, whose seccomp filter
    refuses connect() for every family: must answer "refused EACCES" (fix of
    the secure-phase finding SOCKET-CONNECT). The others stay measurements.
    render: the product jail of a profile without any socket rule and with
    connect() open (unchanged); round 1 showed it reaches the socket, so
    Landlock does not govern connect() of a Unix socket on this kernel.
    variant nosock: the soffice rules without the /tmp socket rule, i.e. a
    soffice whose own sockets would live in its job folder. variant
    seccomp,deny-connect: the product seccomp filter plus connect() refused.
    """
    path = os.environ.get("HP_EXAPP_SOCK", HARP_SOCKET)
    probe = [sys.executable, "-I", str(DRIVER), "connect", path]
    runs = {
        "test-process": probe,
        "soffice": jail_argv("soffice", probe),
        "render": jail_argv("render", probe),
        "variant=nosock": [sys.executable, "-I", str(DRIVER), "variant", "nosock", "soffice", "--", *probe],
        "variant=seccomp,deny-connect": [
            sys.executable,
            "-I",
            str(DRIVER),
            "variant",
            "seccomp,deny-connect",
            "soffice",
            "--",
            *probe,
        ],
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
    # The fix: soffice reaches no socket, the HaRP socket of the server included.
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
