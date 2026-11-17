"""DOCX to PDF through the real LibreOffice in the jail of the "soffice" profile (plan 02-08, 02-16).

Runs only inside the test stage of the image (sandbox.yml, -m container): the
development machine has neither LibreOffice nor Docker. The DOCX is written
here with the standard library, so the test needs no file outside the image.

HaRP run 44015648619 showed the regression: with the jail of 02-08 soffice
ended after 249 ms and every DOCX job failed with render_failed. Sandbox run
44021006501 showed exit 1 without a signal, after fontconfig ("No writable
cache directories") and dconf ("unable to create directory") warnings; the
cause is not proven. The diagnosis below runs the same soffice call layer by
layer and with and without HOME/XDG in the job profile, so that one CI run
names the layer that breaks it. Its result lines in the job log:

    SOFFICE-LAYER <layer>/<env> exit=<n> signal=<s> pdf=<ja|nein>
    SOFFICE-TAIL  <layer>/<env> stderr: ... || stdout: ...
    SOCKET-CONNECT soffice=<ok|refused ...|absent>

Layers: 1-env-only (no jail, emptied environment, own process group),
2-limits (rlimits, no_new_privs), 3-landlock (plus Landlock), 4-seccomp (plus
seccomp: the product). Env: plain (only TMPDIR in the job profile, the state
of ba141fa), home (TMPDIR, HOME, XDG_CACHE_HOME, XDG_CONFIG_HOME,
XDG_RUNTIME_DIR in the job profile: the product now). One hypothesis variant,
test only: 4-seccomp+proc-shm also reads /proc and /dev/shm. The LibreOffice
25.2 source does not prove that headless conversion needs them (oosplash only
stat()s /proc/version, which Landlock does not govern; sal reads
/proc/self/exe only before osl_setCommandArgs), so the product does not open them.
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
VARIANTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("4-seccomp", "home", ()),
    ("4-seccomp", "plain", ()),
    ("4-seccomp+proc-shm", "home", HYPOTHESIS_READ),
    ("3-landlock", "home", ()),
    ("3-landlock", "plain", ()),
    ("2-limits", "home", ()),
    ("2-limits", "plain", ()),
    ("1-env-only", "home", ()),
    ("1-env-only", "plain", ()),
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
    """The start of one variant: the product jail, the partial jail of jail_layers.py, or no jail."""
    if layer == "1-env-only":
        return command
    product = jail_argv("soffice", command, read=read, write=write)
    if layer.startswith("4-seccomp"):
        return product
    # product[4:] is what jail.main takes: profile, paths, --, command.
    partial = layer.split("-", 1)[1]
    return [sys.executable, "-I", str(DRIVER), "layers", partial, *product[4:]]


async def _run_variant(
    number: int, layer: str, env_name: str, extra_read: tuple[str, ...], source: Path, tmp_path: Path
) -> dict[str, object]:
    job_id = str(990100 + number)
    outdir = tmp_path / f"out-{job_id}"
    outdir.mkdir()
    profile, full_env = soffice.prepare_profile(job_id)
    extra = full_env if env_name == "home" else {"TMPDIR": full_env["TMPDIR"]}
    command = soffice.command(source, outdir, job_id)
    argv = _argv(layer, command, (str(source), *extra_read), (str(outdir), str(profile)))
    soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=outdir,
        env=child.child_env(extra, profile="soffice"),
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


async def test_diagnosis_soffice_layer_by_layer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _docx(tmp_path / "probe.docx")
    results: dict[str, dict[str, object]] = {}
    for number, (layer, env_name, extra_read) in enumerate(VARIANTS):
        name = f"{layer}/{env_name}"
        result = await _run_variant(number, layer, env_name, extra_read, source, tmp_path)
        results[name] = result
        # Outside the capture, so the lines stand in the job log of a passing run, too.
        with capsys.disabled():
            print(
                f"\nSOFFICE-LAYER {name} exit={result['exit']} signal={result['signal']} "
                f"pdf={'ja' if result['pdf'] else 'nein'} ms={result['ms']}"
            )
            print(f"SOFFICE-TAIL {name} stderr: {result['stderr']} || stdout: {result['stdout']}")
    record_measurement("soffice_layers", results)

    # Positive control: without any jail soffice converts the same file with
    # the job profile environment; otherwise the diagnosis says nothing.
    assert results["1-env-only/home"]["pdf"], results["1-env-only/home"]


async def test_measure_whether_a_soffice_child_reaches_the_harp_socket(capsys: pytest.CaptureFixture[str]) -> None:
    """A measurement for secure-phase, not a gate: SOCKET-CONNECT soffice=<ok|refused|absent>."""
    path = os.environ.get("HP_EXAPP_SOCK", "/tmp/exapp.sock")  # noqa: S108 - the HaRP socket path
    probe = [sys.executable, "-I", str(DRIVER), "connect", path]
    control = await _probe(probe)
    jailed = await _probe(jail_argv("soffice", probe))
    with capsys.disabled():
        print(f"\nSOCKET-CONNECT test-process={control}")
        print(f"SOCKET-CONNECT soffice={jailed}")
    record_measurement("socket_connect_soffice", jailed)
    # Positive control: the socket is there and answers an unjailed process;
    # and the jailed probe really ran (a jail failure would print nothing).
    assert control == "ok", control
    assert jailed == "ok" or jailed.startswith("refused"), jailed


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
