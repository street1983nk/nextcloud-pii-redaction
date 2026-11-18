"""Container proof of SAFE-03 (plan 02-22): a DOCX or ODT with external references makes no network call.

Runs only inside the test stage of the image (sandbox.yml, -m container). A
canary HTTP server listens on 127.0.0.1 inside the container and counts every
connection it accepts, in setup(), so a connection without a valid request
counts as well. The attack corpus of plan 02-07 is mounted at PII_CORPUS; its
external references point to the discard port (http://127.0.0.1:9/), and
retarget() writes each candidate anew with the port of the canary, member by
member, nothing else changed.

The layers of RESEARCH "Netzwerkbeweis in CI", each a run of its own:

    a  the full chain: the sanitize child in its jail, then soffice.convert
       (jail profile soffice: Landlock, seccomp, the hardened profile)
    b  the hardened LibreOffice profile alone: the raw document, soffice
       started directly by the test with child_env and its own job profile,
       no jail, no seccomp (A3: the keys are read and work)
    c  seccomp alone: the raw document, the jail of soffice, the profile
       template without the hardening (A8: LibreOffice needs no AF_INET)
    d  the positive control: the raw document, the template without the
       hardening, no jail. Its count is a measurement, never a gate: when it
       stays 0 for every candidate, run b cannot be told apart from "nothing
       would have loaded anyway", and measurements.json says
       positive_control not_triggered for the owner (plan 02-24).

a, b and c must count 0 connections and give a PDF (a run that renders
nothing would count 0 for the wrong reason). A macro ODT (OnLoad Basic that
would write <outdir>/macro-ran) must leave no file after a and b. After every
run no zombie of uid 10001 is left. test_bridge_full_chain repeats a for
ext_image.docx; sandbox.yml runs it with -k bridge in the bridge container
under the docker0 capture (D-02-06), which must stay empty.

Lines in the job log:

    LO-NET layer=<a|b|c|d> file=<name> connections=<n> pdf=<ja|nein> outcome=<word> macro=<ran|absent|-> asked=<paths>
    LO-NET-ZOMBIES layer=<layer> n=<n>                                        (a gate: 0)
    LO-NET-CONTROL connections=<n> positive_control=<triggered|not_triggered> (a measurement)
"""

import asyncio
import contextlib
import shutil
import socket
import threading
import time
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final, Literal

import pytest

from pii_redaction_backend import config
from pii_redaction_backend.intake.verdict import OK
from pii_redaction_backend.runner import runner
from pii_redaction_backend.sandbox.reaper import become_subreaper, reap_group
from pii_redaction_backend.workers import child, soffice
from tests.conftest import record_measurement

pytestmark = [pytest.mark.container, pytest.mark.linux]

Format = Literal["docx", "odt"]
Corpus = tuple[Path, dict[str, dict[str, object]]]
# The type of pytest's record_property fixture.
RecordProperty = Callable[[str, object], None]

# The canary address of the corpus (ci/make_corpus.py canary_address(0)): the discard port.
CORPUS_ADDRESS: Final = b"http://127.0.0.1:9/"
# The corpus files with an external reference, all retargeted to the canary.
CANDIDATES: Final = (
    "ext_image.docx",
    "ext_template.docx",
    "ext_includepicture.docx",
    "ext_altchunk.docx",
    "odt_ext_image.odt",
)
# The corpus files with a macro; they carry no address and are copied as they are.
MACRO_FILES: Final = ("macro_vba.docx", "odt_basic.odt")
# The ODT of this test whose OnLoad Basic would write a marker file.
MACRO_MARKER_ODT: Final = "macro_marker.odt"
MARKER: Final = "macro-ran"
BRIDGE_FILE: Final = "ext_image.docx"
# Job ids of this test; far above anything the queue hands out in the container.
JOB_BASE: Final = 990_600
# A connection made just before the end of a run is accepted a moment later.
SETTLE_S: Final = 0.5
UNJAILED_TIMEOUT_S: Final = soffice.DEFAULT_TIMEOUT_S

ODT_MIMETYPE: Final = "application/vnd.oasis.opendocument.text"
ODT_NS: Final = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:script="urn:oasis:names:tc:opendocument:xmlns:script:1.0"'
)
LIBRARY_NS: Final = "http://openoffice.org/2000/library"
SCRIPT_NS: Final = "http://openoffice.org/2000/script"


# -- the canary ----------------------------------------------------------------------------------


class Canary:
    """A counting HTTP server on 127.0.0.1: every accepted connection, and the paths that were asked for."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections = 0
        self._asked: list[str] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), canary_handler(self))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> "Canary":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def connected(self) -> None:
        with self._lock:
            self._connections += 1

    def asked(self, method: str, path: str) -> None:
        with self._lock:
            self._asked.append(f"{method}:{path}")

    def snapshot(self) -> tuple[int, int]:
        """The number of connections and of asked paths so far, to measure one run as a difference."""
        with self._lock:
            return self._connections, len(self._asked)

    def since(self, mark: tuple[int, int]) -> tuple[int, list[str]]:
        """Connections and asked paths since mark."""
        with self._lock:
            return self._connections - mark[0], list(self._asked[mark[1] :])


def canary_handler(canary: Canary) -> type[BaseHTTPRequestHandler]:
    """The request handler of the canary: counts in setup(), before any request is parsed."""

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            canary.connected()
            super().setup()

        def do_GET(self) -> None:
            canary.asked(self.command, self.path)
            self.send_error(404)

        do_HEAD = do_POST = do_PUT = do_OPTIONS = do_PROPFIND = do_GET

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the name of the base method
            return

    return Handler


@contextlib.contextmanager
def running_canary() -> Iterator[Canary]:
    canary = Canary().start()
    try:
        yield canary
    finally:
        canary.stop()


# -- the documents ------------------------------------------------------------------------------


def retarget(source: Path, target: Path, port: int) -> int:
    """Write source anew as target with every corpus address pointing to the canary port; returns the members changed.

    Names, order, dates and compression of the members stay as they were (the
    mimetype of an ODT stays first and stored).
    """
    new = f"http://127.0.0.1:{port}/".encode("ascii")
    changed = 0
    with zipfile.ZipFile(source) as reader, zipfile.ZipFile(target, "w") as writer:
        for info in reader.infolist():
            data = reader.read(info)
            if CORPUS_ADDRESS in data:
                data = data.replace(CORPUS_ADDRESS, new)
                changed += 1
            fresh = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            fresh.compress_type = info.compress_type
            writer.writestr(fresh, data)
    return changed


def macro_marker_odt(target: Path, marker: Path) -> Path:
    """An ODT whose document Basic runs on load (dom:load) and would write marker.

    A complete Basic library (script-lc.xml, script-lb.xml, Module1.xml, all in
    the manifest), no DOCTYPE anywhere, so the sanitizer takes it as a document
    and not as a broken file.
    """
    code = "\n".join(
        (
            "Sub Main",
            "Dim n As Integer",
            "n = FreeFile()",
            f'Open "{marker}" For Output As #n',
            'Print #n, "ran"',
            "Close #n",
            "End Sub",
        )
    )
    content = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {ODT_NS} office:version="1.3">'
        "<office:scripts><office:event-listeners>"
        '<script:event-listener script:language="ooo:script" script:event-name="dom:load" '
        'xlink:href="vnd.sun.star.script:Standard.Module1.Main?language=Basic&amp;location=document" '
        'xlink:type="simple"/>'
        "</office:event-listeners></office:scripts>"
        "<office:body><office:text><text:p>Makroprobe</text:p></office:text></office:body>"
        "</office:document-content>"
    )
    libraries = (
        f'<?xml version="1.0" encoding="UTF-8"?><library:libraries xmlns:library="{LIBRARY_NS}" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<library:library library:name="Standard" library:link="false"/></library:libraries>'
    )
    library = (
        f'<?xml version="1.0" encoding="UTF-8"?><library:library xmlns:library="{LIBRARY_NS}" '
        'library:name="Standard" library:readonly="false" library:passwordprotected="false">'
        '<library:element library:name="Module1"/></library:library>'
    )
    module = (
        f'<?xml version="1.0" encoding="UTF-8"?><script:module xmlns:script="{SCRIPT_NS}" '
        f'script:name="Module1" script:language="StarBasic">{xml_text(code)}</script:module>'
    )
    entries = [
        ("/", ODT_MIMETYPE),
        ("content.xml", "text/xml"),
        ("Basic/", ""),
        ("Basic/script-lc.xml", "text/xml"),
        ("Basic/Standard/", ""),
        ("Basic/Standard/script-lb.xml", "text/xml"),
        ("Basic/Standard/Module1.xml", "text/xml"),
    ]
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
        'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
        + "".join(
            f'<manifest:file-entry manifest:full-path="{path}" manifest:media-type="{kind}"/>' for path, kind in entries
        )
        + "</manifest:manifest>"
    )
    members = [
        ("mimetype", ODT_MIMETYPE),
        ("content.xml", content),
        ("Basic/script-lc.xml", libraries),
        ("Basic/Standard/script-lb.xml", library),
        ("Basic/Standard/Module1.xml", module),
        ("META-INF/manifest.xml", manifest),
    ]
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            archive.writestr(info, data.encode("utf-8"))
    return target


def xml_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def doc_format(name: str) -> Format:
    return "odt" if name.endswith(".odt") else "docx"


# -- the layers -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Layer:
    """One run of the network proof: which protections are on."""

    name: str
    sanitize: bool
    harden: bool
    jail: bool


LAYERS: Final[Mapping[str, Layer]] = {
    "a": Layer("a", sanitize=True, harden=True, jail=True),
    "b": Layer("b", sanitize=False, harden=True, jail=False),
    "c": Layer("c", sanitize=False, harden=False, jail=True),
    "d": Layer("d", sanitize=False, harden=False, jail=False),
}


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one run did: connections to the canary, the paths it asked for, a PDF or why not, the macro marker."""

    connections: int
    asked: list[str]
    pdf: bool
    word: str
    macro: str


def positive_control_word(counts: Mapping[str, int]) -> str:
    """triggered when the control run made at least one connection for any candidate."""
    return "triggered" if any(count > 0 for count in counts.values()) else "not_triggered"


def line(layer: str, name: str, outcome: Outcome) -> str:
    return (
        f"LO-NET layer={layer} file={name} connections={outcome.connections} pdf={'ja' if outcome.pdf else 'nein'} "
        f"outcome={outcome.word} macro={outcome.macro} asked={','.join(outcome.asked) or '-'}"
    )


def _fresh(folder: Path) -> Path:
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


async def run_unjailed(args: list[str], *, cwd: Path, env: dict[str, str], timeout_s: float) -> int:
    """A command without any jail, in its own session; the group is killed and collected on every way out."""
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout_s)
    except TimeoutError:
        reap_group(process.pid)
        await process.wait()
        raise
    finally:
        reap_group(process.pid)


async def unjailed_convert(src: Path, outdir: Path, job_id: str, *, harden: bool) -> str:
    """soffice started by the test itself: the product command line and job profile, no jail; the outcome word."""
    profile, env = soffice.prepare_profile(job_id)
    soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    try:
        soffice.seed_profile(profile)
        if harden:
            soffice.harden_profile(profile)
        code = await run_unjailed(
            soffice.command(src, outdir, job_id),
            cwd=outdir,
            env=child.child_env(env, profile="soffice"),
            timeout_s=UNJAILED_TIMEOUT_S,
        )
    except TimeoutError:
        return "timeout"
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        soffice._remove_ipc_sockets(Path(soffice.PROFILE_ROOT))
    return "ok" if code == 0 else f"exit{code}"


async def jailed_convert(src: Path, outdir: Path, job_id: str, *, harden: bool) -> str:
    """soffice.convert of the product (jail profile soffice); without harden the template copy stays as it is."""
    with pytest.MonkeyPatch.context() as patch:
        if not harden:
            patch.setattr(soffice, "harden_profile", lambda _profile: None)
        try:
            await soffice.convert(src, outdir, job_id)
        except child.ChildTimeout:
            return "timeout"
        except child.ChildFailed as failed:
            return f"exit{failed.exit_code}"
        except soffice.ConversionFailed:
            return "no-pdf"
    return "ok"


async def sanitized(source: Path, fmt: Format, job: int) -> tuple[str, Path | None]:
    """The sanitize child on source as the runner starts it; its word and the cleaned copy (None unless ok)."""
    from tests.test_corpus import run_sanitize

    folder = _fresh(config.work_dir(job))
    shutil.copyfile(source, folder / runner.SOURCE_STEM)
    word, _, clean = await run_sanitize(folder / runner.SOURCE_STEM, fmt, folder)
    return word, (clean if word == OK else None)


async def run_layer(layer: Layer, source: Path, job: int, work: Path, canary: Canary) -> Outcome:
    """One document through one layer, measured at the canary."""
    outdir = _fresh(work / f"pdf-{layer.name}-{job}")
    marker = outdir / MARKER
    if source.name == MACRO_MARKER_ODT:
        source = macro_marker_odt(work / f"{layer.name}-{job}-{MACRO_MARKER_ODT}", marker)
    mark = canary.snapshot()
    document = source
    word = ""
    try:
        if layer.sanitize:
            cleaned, copy = await sanitized(source, doc_format(source.name), job)
            if copy is None:
                word = f"sanitize-{cleaned}"
            else:
                document = Path(shutil.copyfile(copy, work / f"clean-{job}.{doc_format(source.name)}"))
        if not word:
            convert = jailed_convert if layer.jail else unjailed_convert
            word = await convert(document, outdir, str(job), harden=layer.harden)
    finally:
        if layer.sanitize:
            shutil.rmtree(config.work_dir(job), ignore_errors=True)
    await asyncio.sleep(SETTLE_S)
    connections, asked = canary.since(mark)
    pdf = len(list(outdir.glob("*.pdf"))) == 1
    macro = ("ran" if marker.exists() else "absent") if source.name.endswith(MACRO_MARKER_ODT) else "-"
    return Outcome(connections=connections, asked=asked, pdf=pdf, word=word, macro=macro)


async def run_files(
    layer: Layer, names: tuple[str, ...], sources: Mapping[str, Path], work: Path, canary: Canary
) -> tuple[dict[str, Outcome], int]:
    """Every named document through layer; the outcomes and the zombies of uid 10001 left afterwards."""
    from tests.test_jail_container import settled_zombies

    # As the server (main.harden_process): orphans of soffice come back here and reap_group collects them.
    assert become_subreaper()
    outcomes: dict[str, Outcome] = {}
    for index, name in enumerate(names):
        job = JOB_BASE + 20 * sorted(LAYERS).index(layer.name) + index
        outcomes[name] = await run_layer(layer, sources[name], job, work, canary)
    found = await asyncio.to_thread(settled_zombies)
    return outcomes, len(found)


# -- fixtures --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def canary() -> Iterator[Canary]:
    """The running canary, after it counted one plain connect of this process (else every 0 would mean nothing)."""
    with running_canary() as server:
        assert canary_sees_a_connect(server), "the canary does not count a plain connect"
        yield server


def touch_canary(port: int) -> None:
    """One plain TCP connect to the canary, no request."""
    with socket.create_connection(("127.0.0.1", port), timeout=5):
        pass


def canary_sees_a_connect(canary: Canary) -> bool:
    """Whether the canary counts exactly one connection for one plain connect."""
    mark = canary.snapshot()
    touch_canary(canary.port)
    deadline = time.monotonic() + 5
    while canary.since(mark)[0] == 0 and time.monotonic() < deadline:
        time.sleep(0.05)
    return canary.since(mark)[0] == 1


@pytest.fixture(scope="module")
def canary_sources(canary: Canary, mounted_corpus: Corpus, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The candidates retargeted to the canary port, the macro files as they are, the marker ODT made per run."""
    corpus, _ = mounted_corpus
    folder = tmp_path_factory.mktemp("lo-network")
    sources: dict[str, Path] = {}
    for name in CANDIDATES:
        changed = retarget(corpus / name, folder / name, canary.port)
        # The positive control of retarget: without a changed member the canary could never be asked.
        assert changed >= 1, name
        sources[name] = folder / name
    for name in MACRO_FILES:
        sources[name] = Path(shutil.copyfile(corpus / name, folder / name))
    # Made per run by run_layer, because the marker path lies in the output folder of that run.
    sources[MACRO_MARKER_ODT] = folder / MACRO_MARKER_ODT
    return sources


def _report(capsys: pytest.CaptureFixture[str], layer: str, outcomes: Mapping[str, Outcome], zombies: int) -> str:
    """The LO-NET lines of one layer, printed outside the capture and returned for the assert texts."""
    lines = [line(layer, name, outcome) for name, outcome in outcomes.items()]
    lines.append(f"LO-NET-ZOMBIES layer={layer} n={zombies}")
    with capsys.disabled():
        print()
        for text in lines:
            print(text)
    return "\n".join(lines)


def _measure(layer: str, outcomes: Mapping[str, Outcome], zombies: int) -> None:
    runs: dict[str, object] = {
        name: {"connections": o.connections, "pdf": o.pdf, "outcome": o.word, "macro": o.macro}
        for name, o in outcomes.items()
    }
    record_measurement(f"lo_network_{layer}", {**runs, "zombies": zombies})


def closed_problems(outcomes: Mapping[str, Outcome], zombies: int) -> list[str]:
    """Why a protecting layer failed: a connection, no PDF (0 would then mean nothing), a macro that ran, a zombie."""
    found: list[str] = []
    for name, outcome in outcomes.items():
        if outcome.connections:
            found.append(f"{name}: {outcome.connections} connections")
        if not outcome.pdf:
            found.append(f"{name}: no PDF ({outcome.word})")
        if outcome.macro == "ran":
            found.append(f"{name}: the macro ran")
    if zombies:
        found.append(f"{zombies} zombies")
    return found


# -- the runs ---------------------------------------------------------------------------------------


async def test_layer_a_full_chain_makes_no_connection(
    canary: Canary, canary_sources: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    names = (*CANDIDATES, *MACRO_FILES, MACRO_MARKER_ODT)
    outcomes, zombies = await run_files(LAYERS["a"], names, canary_sources, tmp_path, canary)
    report = _report(capsys, "a", outcomes, zombies)
    _measure("a", outcomes, zombies)
    assert closed_problems(outcomes, zombies) == [], report
    assert outcomes[MACRO_MARKER_ODT].macro == "absent", report


async def test_layer_b_hardened_profile_alone_makes_no_connection(
    canary: Canary, canary_sources: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A3: the keys of the hardened profile are read and keep LibreOffice from loading, without sanitizer and jail."""
    names = (*CANDIDATES, MACRO_MARKER_ODT)
    outcomes, zombies = await run_files(LAYERS["b"], names, canary_sources, tmp_path, canary)
    report = _report(capsys, "b", outcomes, zombies)
    _measure("b", outcomes, zombies)
    assert closed_problems(outcomes, zombies) == [], report
    assert outcomes[MACRO_MARKER_ODT].macro == "absent", report


async def test_layer_c_seccomp_alone_makes_no_connection(
    canary: Canary, canary_sources: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A8: in the jail of soffice with the plain template profile nothing reaches the canary, the PDF still comes."""
    outcomes, zombies = await run_files(LAYERS["c"], CANDIDATES, canary_sources, tmp_path, canary)
    report = _report(capsys, "c", outcomes, zombies)
    _measure("c", outcomes, zombies)
    assert closed_problems(outcomes, zombies) == [], report


async def test_layer_d_positive_control_is_measured(
    canary: Canary,
    canary_sources: dict[str, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record_property: RecordProperty,
) -> None:
    """No layer at all: can LibreOffice reach the canary? A measurement, not a gate (plan 02-24 shows it the owner).

    That the canary itself counts a plain connect is checked by its fixture
    before any run; here only the cleanup after the runs is a gate.
    """
    names = (*CANDIDATES, MACRO_MARKER_ODT)
    outcomes, zombies = await run_files(LAYERS["d"], names, canary_sources, tmp_path, canary)
    report = _report(capsys, "d", outcomes, zombies)
    counts = {name: outcome.connections for name, outcome in outcomes.items() if name in CANDIDATES}
    word = positive_control_word(counts)
    total = sum(counts.values())
    with capsys.disabled():
        print(f"LO-NET-CONTROL connections={total} positive_control={word}")
    _measure("d", outcomes, zombies)
    record_measurement("positive_control", word)
    record_measurement("positive_control_connections", counts)
    record_measurement("positive_control_macro", outcomes[MACRO_MARKER_ODT].macro)
    record_property("positive_control", word)
    record_property("positive_control_connections", total)
    assert zombies == 0, report


async def test_bridge_full_chain(
    canary: Canary, canary_sources: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run a for ext_image.docx; in the bridge container the docker0 capture of sandbox.yml must stay empty."""
    started = time.monotonic()
    outcomes, zombies = await run_files(LAYERS["a"], (BRIDGE_FILE,), canary_sources, tmp_path, canary)
    report = _report(capsys, "a-bridge", outcomes, zombies)
    record_measurement("lo_network_bridge_s", round(time.monotonic() - started, 1))
    assert closed_problems(outcomes, zombies) == [], report
