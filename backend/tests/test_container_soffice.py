"""DOCX to PDF through the real LibreOffice in the jail of the "soffice" profile (plan 02-08, 02-16).

Runs only inside the test stage of the image (sandbox.yml, -m container): the
development machine has neither LibreOffice nor Docker. The DOCX is written
here with the standard library, so the test needs no file outside the image.

HaRP run 44015648619 showed the regression: with the jail of 02-08 soffice
ended after 249 ms and every DOCX job failed with render_failed. Sandbox run
44021006501 showed exit 1 without a signal. Sandbox run of 7e3c909 showed:
layers 1 and 2 convert, from layer 3 (Landlock) on exit 1 after about 300 ms
on amd64 and arm64, with and without HOME/XDG in the job profile alike (so
HOME/XDG are closed again), with and without seccomp alike, and reading
/proc and /dev/shm does not help. Sandbox run of 11fb9f9 (Landlock ABI 8,
amd64 and arm64 alike): fs-all and write=/tmp convert, every other single
change does not; the stderr names dconf ("unable to create directory"). The
Landlock audit said nothing (audit_enabled=0), so that run is gone.

Round 2 (this file) names the one right and the one path. Every run starts
from a clean /tmp: what earlier runs left there (.cache, .config, dconf and
soffice remains, any own hidden entry new since the test began) is removed
first, so an unjailed run can no longer make a later jailed run look better
or worse. Its result lines in the job log:

    LANDLOCK-ABI abi=<n> kernel=<release>
    SOFFICE-LAYER <layer>/plain exit=<n> signal=<s> pdf=<ja|nein> ms=<n> clean=<removed|->
    SOFFICE-LAYER variant=<spec> exit=... pdf=... ms=... path=<ja|nein|-> clean=<removed|->
    SOFFICE-LAYER env=<name> exit=... pdf=... ms=... clean=<removed|->
    SOFFICE-TAIL  <name> stderr: ... || stdout: ...
    SOFFICE-TMPNEW <name> n=<count> <path> <path> ...
    SOCKET-CONNECT <who>=<ok|refused ...|absent>

clean= lists the names removed from /tmp before the run (- for none).
SOFFICE-TMPNEW lists the paths that were new in /tmp after the run, names
only, no content (below the job profile /tmp/lo-<id> at most three levels).

Layers: 1-env-only (no jail, emptied environment, own process group),
2-limits (rlimits, no_new_privs), 3-landlock (plus Landlock), 4-seccomp (plus
seccomp: the product). Env: only TMPDIR in the job profile (the product).

Variants (tests/jail_layers.py, VARIANT_SPECS): rlimits, no_new_privs and
the Landlock rules of the product with exactly one change: one more
readable path, one more writable path, one more right, or one handled class
less. They are measurements in the test run, never rules of the product.
path= tells whether the named path exists in the image (Landlock skips a
missing one, so path=nein means the run equals the product).

grant=/tmp:<rights> grants exactly these Landlock rights on /tmp on top of the
product rules (write=/tmp split up): each right alone, the pairs and chains a
cache folder needs, and write=/tmp minus one right each. env=<name> runs the
product jail (all layers, seccomp with connect() refused) with one change of
the environment: HOME and/or the XDG folders inside the job profile, or dconf
kept in memory (GSETTINGS_BACKEND=memory, DCONF_PROFILE=/dev/null). The
environment of these runs is set here and bypasses child.child_env on
purpose: a measurement, not a rule of the product.
"""

import asyncio
import contextlib
import os
import shutil
import stat
import sys
import time
import zipfile
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

GRANT = "grant=/tmp:"
# write=/tmp, split into its rights (jail_layers.GRANT_RIGHTS).
WRITE_RIGHTS = (
    "READ_FILE",
    "READ_DIR",
    "EXECUTE",
    "WRITE_FILE",
    "TRUNCATE",
    "MAKE_DIR",
    "MAKE_REG",
    "MAKE_SOCK",
    "MAKE_FIFO",
    "MAKE_SYM",
    "REMOVE_FILE",
    "REMOVE_DIR",
)
SINGLE_RIGHTS = (
    "READ",
    "MAKE_DIR",
    "MAKE_REG",
    "WRITE_FILE",
    "TRUNCATE",
    "REMOVE_FILE",
    "REMOVE_DIR",
    "MAKE_SOCK",
    "MAKE_SYM",
    "MAKE_FIFO",
)
RIGHT_SETS = (
    "MAKE_DIR+MAKE_REG",
    "MAKE_DIR+MAKE_REG+WRITE_FILE",
    "READ+MAKE_DIR",
    "READ+MAKE_DIR+MAKE_REG",
    "READ+MAKE_DIR+MAKE_REG+WRITE_FILE",
    "READ+MAKE_DIR+MAKE_REG+WRITE_FILE+TRUNCATE",
    "READ+MAKE_DIR+MAKE_REG+WRITE_FILE+TRUNCATE+REMOVE_FILE",
    "READ+MAKE_DIR+MAKE_REG+WRITE_FILE+TRUNCATE+REMOVE_FILE+REMOVE_DIR",
)


def _minus(right: str) -> str:
    return "+".join(name for name in WRITE_RIGHTS if name != right)


# One run per entry, each on a clean /tmp; controls first, write=/tmp last.
LANDLOCK_VARIANTS: tuple[str, ...] = (
    # Positive control of the driver: no Landlock = layer 2, must convert.
    "no-landlock",
    # The product (Landlock, seccomp with connect() refused) as a variant: control.
    "seccomp",
    # Each right of write=/tmp alone on /tmp.
    *(f"{GRANT}{right}" for right in SINGLE_RIGHTS),
    # The pairs and chains a cache folder needs.
    *(f"{GRANT}{rights}" for rights in RIGHT_SETS),
    # write=/tmp minus one right each: which right cannot be missed.
    *(f"{GRANT}{_minus(right)}" for right in WRITE_RIGHTS),
    # Controls of round 1: converted there.
    "fs-all",
    "write=/tmp",
)

# One change of the environment per run, in the product jail. "@name" is a
# folder inside the job profile, made 0700 before the run (Landlock grants
# the job profile already, so no rule changes).
HOME_JOB = {"HOME": "@home"}
XDG_JOB = {"XDG_CACHE_HOME": "@cache", "XDG_CONFIG_HOME": "@config", "XDG_RUNTIME_DIR": "@run"}
GSETTINGS_MEMORY = {"GSETTINGS_BACKEND": "memory"}
DCONF_NULL = {"DCONF_PROFILE": "/dev/null"}
ENV_VARIANTS: tuple[tuple[str, dict[str, str]], ...] = (
    ("product", {}),
    ("home-job", HOME_JOB),
    ("home-job+xdg-job", {**HOME_JOB, **XDG_JOB}),
    ("xdg-job", XDG_JOB),
    ("gsettings-memory", GSETTINGS_MEMORY),
    ("dconf-profile-null", DCONF_NULL),
    ("gsettings-memory+dconf-profile-null", {**GSETTINGS_MEMORY, **DCONF_NULL}),
    ("home-job+gsettings-memory", {**HOME_JOB, **GSETTINGS_MEMORY}),
    ("xdg-job+gsettings-memory", {**XDG_JOB, **GSETTINGS_MEMORY}),
)


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


def env_for(profile: Path, changes: dict[str, str]) -> dict[str, str]:
    """The values of one env variant; "@name" becomes a fresh 0700 folder inside the job profile."""
    values: dict[str, str] = {}
    for key, value in changes.items():
        if value.startswith("@"):
            folder = profile / value[1:]
            folder.mkdir(mode=0o700, exist_ok=True)
            values[key] = str(folder)
        else:
            values[key] = value
    return values


async def _run(
    number: int,
    layer: str,
    extra_read: tuple[str, ...],
    source: Path,
    tmp_path: Path,
    *,
    baseline: frozenset[str],
    env_changes: dict[str, str] | None = None,
) -> dict[str, object]:
    job_id = str(990100 + number)
    outdir = tmp_path / f"out-{job_id}"
    outdir.mkdir()
    removed = clean_tmp(baseline)
    soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    profile, env = soffice.prepare_profile(job_id)
    command = soffice.command(source, outdir, job_id)
    argv = _argv(layer, command, (str(source), *extra_read), (str(outdir), str(profile)))
    full_env = child.child_env(env, profile="soffice")
    # Test only: an env variant bypasses the allowlist of child_env on purpose.
    full_env.update(env_for(profile, env_changes or {}))
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
        new = tmp_new(before, tmp_snapshot())
        shutil.rmtree(profile, ignore_errors=True)
        soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    return {
        "exit": "timeout" if code is None else code,
        "signal": -code if code is not None and code < 0 else None,
        "pdf": any(outdir.glob("*.pdf")),
        "ms": int((time.monotonic() - started) * 1000),
        "stderr": child.diagnostic_tail(err, child.SOFFICE_TAIL_LINES),
        "stdout": child.diagnostic_tail(out, child.SOFFICE_TAIL_LINES),
        "clean": removed,
        "tmp_new": new,
    }


def tmpnew_line(label: str, new: list[str]) -> str:
    shown = " ".join(new[:TMPNEW_MAX])
    more = f" +{len(new) - TMPNEW_MAX} more" if len(new) > TMPNEW_MAX else ""
    return f"SOFFICE-TMPNEW {label} n={len(new)} {shown}{more}".rstrip()


def _print_run(label: str, result: dict[str, object], suffix: str = "") -> None:
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
    results: dict[str, dict[str, object]] = {}
    for number, (layer, extra_read) in enumerate(LAYERS):
        name = f"{layer}/plain"
        results[name] = await _run(number, layer, extra_read, source, tmp_path, baseline=baseline)
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


def _path_state(spec: str) -> str:
    """ja or nein for a spec that names a path, - for a flag spec."""
    paths = [part.split("=", 1)[1].split(":", 1)[0] for part in spec.split(",") if "=" in part]
    if not paths:
        return "-"
    return "ja" if all(Path(path).exists() for path in paths) else "nein"


async def test_diagnosis_soffice_landlock_one_change_at_a_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _docx(tmp_path / "probe.docx")
    abi_line = await _driver("abi")
    baseline = _baseline()
    with capsys.disabled():
        print(f"\nLANDLOCK-ABI {abi_line or 'no-answer'}")
    results: dict[str, dict[str, object]] = {}
    for number, spec in enumerate(LANDLOCK_VARIANTS, start=len(LAYERS)):
        results[spec] = await _run(number, f"variant:{spec}", (), source, tmp_path, baseline=baseline)
        with capsys.disabled():
            _print_run(f"variant={spec}", results[spec], f" path={_path_state(spec)}")
    record_measurement("soffice_landlock_variants", {"abi": abi_line, "runs": results})

    # Positive control of the driver: without Landlock it is layer 2, which converts.
    assert results["no-landlock"]["pdf"], results["no-landlock"]


async def test_diagnosis_soffice_environment_in_the_product_jail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The product jail with one change of the environment per run; no rule of the product changes."""
    source = _docx(tmp_path / "probe.docx")
    baseline = _baseline()
    start = len(LAYERS) + len(LANDLOCK_VARIANTS)
    results: dict[str, dict[str, object]] = {}
    for number, (name, changes) in enumerate(ENV_VARIANTS, start=start):
        results[name] = await _run(number, "4-seccomp", (), source, tmp_path, baseline=baseline, env_changes=changes)
        with capsys.disabled():
            _print_run(f"env={name}", results[name])
    # Positive control on the same clean /tmp: without a jail soffice converts.
    control = await _run(start + len(ENV_VARIANTS), "1-env-only", (), source, tmp_path, baseline=baseline)
    with capsys.disabled():
        _print_run("env=control-1-env-only", control)
    record_measurement("soffice_env_variants", {**results, "control-1-env-only": control})
    assert control["pdf"], control


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
    path = os.environ.get("HP_EXAPP_SOCK", "/tmp/exapp.sock")  # noqa: S108 - the HaRP socket path
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
