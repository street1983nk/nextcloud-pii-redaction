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
/proc and /dev/shm does not help. The diagnosis below narrows it down inside
Landlock, one change per run. Its result lines in the job log:

    LANDLOCK-ABI abi=<n> kernel=<release>
    LANDLOCK-AUDIT <ran|unavailable abi=<n> needs 7>
    SOFFICE-LAYER <layer>/plain exit=<n> signal=<s> pdf=<ja|nein> ms=<n>
    SOFFICE-LAYER variant=<spec> exit=<n> signal=<s> pdf=<ja|nein> ms=<n> path=<ja|nein|->
    SOFFICE-TAIL  <name> stderr: ... || stdout: ...
    SOCKET-CONNECT <who>=<ok|refused ...|absent>

Layers: 1-env-only (no jail, emptied environment, own process group),
2-limits (rlimits, no_new_privs), 3-landlock (plus Landlock), 4-seccomp (plus
seccomp: the product). Env: only TMPDIR in the job profile (the product).

Variants (tests/jail_layers.py, VARIANT_SPECS): rlimits, no_new_privs and
the Landlock rules of the product with exactly one change: one more
readable path, one more writable path, one more right, or one handled class
less. They are measurements in the test run, never rules of the product.
path= tells whether the named path exists in the image (Landlock skips a
missing one, so path=nein means the run equals the product). The read
candidates below /usr and /etc are readable in the product already
(profiles.SOFFICE_READ); they are controls and must equal the product run.
"""

import asyncio
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.sandbox.jail import jail_argv
from pii_redaction_backend.sandbox.reaper import reap_group
from pii_redaction_backend.workers import child, soffice
from tests.conftest import record_measurement
from tests.jail_layers import AUDIT_ABI

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
# The folder of the source file, filled in per run.
SOURCE_DIR = "{source-dir}"
# One change against the Landlock rules of the product per variant; the order
# runs the bisection first, the variants that may write /tmp last.
LANDLOCK_VARIANTS: tuple[str, ...] = (
    # Positive control of the driver: no Landlock = layer 2, must convert.
    "no-landlock",
    # Bisection: Landlock on, but every file right on /, no TCP, no scope.
    "fs-all,net-off,scope-off",
    "fs-all",
    "net-off",
    "scope-off",
    # One more right on the product paths.
    "refer",
    "ioctl",
    "nosock",
    # One more writable path.
    "write=/dev/null",
    "write=/dev",
    "write=/dev/shm",
    "write=/var/tmp",
    # One more readable path, not in the product.
    "read=/",
    "read=/proc",
    "read=/dev",
    "read=/sys",
    "read=/var",
    "read=/var/cache/fontconfig",
    "read=/run",
    "read=/opt",
    "read=/home",
    "read=/tmp",
    f"read={SOURCE_DIR}",
    # Controls: readable in the product already (profiles.SOFFICE_READ).
    "read=/usr/lib/libreoffice/program",
    "read=/usr/lib",
    "read=/usr/share/fonts",
    "read=/usr/share/fontconfig",
    "read=/etc/fonts",
    "read=/etc/passwd",
    # For the SOCKET-CONNECT proposal: does soffice convert when connect() fails?
    "no-landlock,deny-connect",
    "no-landlock,seccomp,deny-connect",
    # Last: may create files below /tmp.
    "write=/tmp",
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


async def _run(number: int, layer: str, extra_read: tuple[str, ...], source: Path, tmp_path: Path) -> dict[str, object]:
    job_id = str(990100 + number)
    outdir = tmp_path / f"out-{job_id}"
    outdir.mkdir()
    profile, env = soffice.prepare_profile(job_id)
    command = soffice.command(source, outdir, job_id)
    argv = _argv(layer, command, (str(source), *extra_read), (str(outdir), str(profile)))
    soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=outdir,
        env=child.child_env(env, profile="soffice"),
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
        shutil.rmtree(profile, ignore_errors=True)
        soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    return {
        "exit": "timeout" if code is None else code,
        "signal": -code if code is not None and code < 0 else None,
        "pdf": any(outdir.glob("*.pdf")),
        "ms": int((time.monotonic() - started) * 1000),
        "stderr": child.diagnostic_tail(err, child.SOFFICE_TAIL_LINES),
        "stdout": child.diagnostic_tail(out, child.SOFFICE_TAIL_LINES),
    }


def _print_run(label: str, result: dict[str, object], suffix: str = "") -> None:
    print(
        f"\nSOFFICE-LAYER {label} exit={result['exit']} signal={result['signal']} "
        f"pdf={'ja' if result['pdf'] else 'nein'} ms={result['ms']}{suffix}"
    )
    print(f"SOFFICE-TAIL {label} stderr: {result['stderr']} || stdout: {result['stdout']}")


async def test_diagnosis_soffice_layer_by_layer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _docx(tmp_path / "probe.docx")
    results: dict[str, dict[str, object]] = {}
    for number, (layer, extra_read) in enumerate(LAYERS):
        name = f"{layer}/plain"
        results[name] = await _run(number, layer, extra_read, source, tmp_path)
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
    paths = [part.split("=", 1)[1] for part in spec.split(",") if "=" in part]
    if not paths:
        return "-"
    return "ja" if all(Path(path).exists() for path in paths) else "nein"


async def test_diagnosis_soffice_landlock_one_change_at_a_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _docx(tmp_path / "probe.docx")
    abi_line = await _driver("abi")
    abi = int(abi_line.split()[0].removeprefix("abi=")) if abi_line.startswith("abi=") else 0
    specs = [spec.replace(SOURCE_DIR, str(source.parent)) for spec in LANDLOCK_VARIANTS]
    if abi >= AUDIT_ABI:
        specs.insert(1, "audit")
    with capsys.disabled():
        print(f"\nLANDLOCK-ABI {abi_line or 'no-answer'}")
        print("LANDLOCK-AUDIT " + ("ran" if abi >= AUDIT_ABI else f"unavailable abi={abi} needs {AUDIT_ABI}"))
    results: dict[str, dict[str, object]] = {}
    for number, spec in enumerate(specs, start=len(LAYERS)):
        results[spec] = await _run(number, f"variant:{spec}", (), source, tmp_path)
        with capsys.disabled():
            _print_run(f"variant={spec}", results[spec], f" path={_path_state(spec)}")
    record_measurement("soffice_landlock_variants", {"abi": abi_line, "runs": results})

    # Positive control of the driver: without Landlock it is layer 2, which converts.
    assert results["no-landlock"]["pdf"], results["no-landlock"]


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
