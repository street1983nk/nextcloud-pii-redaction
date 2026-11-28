"""Real public documents through the product path, LibreOffice measured per file (plan 02-24, "Nachtrag Task 3").

Owner rule 28.11.2026: the address space cap of soffice (D-02-13) is set from
real documents, never from made ones alone. sandbox.yml fetches the set with
fixed hashes (ci/fetch_corpus.py: seven DOCX of the Schleswig-Holstein
transparency portal, three PDFs of the Bundestag and of the BuFI report),
turns the three PDFs into a DOCX and an ODT each with LibreOffice outside the
sandbox (ci/convert_corpus.py, a foreign tool) and mounts both folders read
only (PII_REAL_CORPUS, PII_REAL_DERIVED). Nothing of it is in the repository,
the image or an artifact; measurements.json holds names and numbers only.

Every file goes through the product path (tests/product_path.py: the real
Runner with pre-check, cleaner, soffice and render in their jails, only the
Nextcloud side replaced). A refusal of the pre-check or the page cap is a
result with its reason, not a failure. While soffice runs, a sampler reads
VmPeak, VmHWM and the address space limit of every soffice.bin of this uid.
soffice_corpus in tests/out/measurements.json gets one entry per file;
ci/soffice_cap.py derives the cap from both architectures (step 4); the value
in sandbox/profiles.py is set only after that (address_space stays None).

Step 5, the negative test: a probe (tests/probes/as_cap.py) puts a cap of
256 MiB in front of soffice inside the product jail. The file must end as
failed with a reason of the closed list, without an exception out of the
runner, without a zombie and without a left job profile or pipe socket. Its
positive control runs the same file with the same probe and a cap of 4 GiB:
it converts, and the sampler sees exactly that limit on soffice.bin, so the
refusal comes from the cap and not from the probe.

Lines in the job log:

    SOFFICE-CORPUS-CONVERT source=<pdf> format=<docx|odt> result=<word> bytes=<n> images=<n> ms=<n>
    SOFFICE-CORPUS doc=<name> format= origin= bytes= result= reason= soffice=<pdf|timeout|exit=..|-> vmpeak_kb=
        vmhwm_kb= samples= as_limit=<unlimited|bytes|-> ms= pages= pages_from=   (a measurement)
    SOFFICE-CAP-PROBE run=<control|capped> cap=<bytes> result= reason= soffice= as_limit= zombies= leftovers=
        (a gate: control review with as_limit=cap, capped failed with a reason, no zombie, nothing left)
    JAIL-ZOMBIES after=corpus n=<n>                                                    (a gate: 0)
"""

import hashlib
import json
import os
import sys
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest

from pii_redaction_backend.sandbox.reaper import become_subreaper
from pii_redaction_backend.workers import child, soffice
from tests import product_path
from tests.conftest import record_measurement
from tests.test_jail_container import settled_zombies, vm_values

pytestmark = [pytest.mark.container, pytest.mark.linux]

REAL_CORPUS_ENV: Final = "PII_REAL_CORPUS"
REAL_DERIVED_ENV: Final = "PII_REAL_DERIVED"
MANIFEST: Final = "manifest.json"
PROC: Final = Path("/proc")
SOFFICE_BIN: Final = "soffice.bin"
SAMPLE_S: Final = 0.05
# Job ids of this test; far above what the queue hands out and apart from the other container tests.
JOB_BASE: Final = 990_300
CONTROL_JOB: Final = 990_390
CAPPED_JOB: Final = 990_391
MIB: Final = 1024 * 1024
# One step of the 256 MiB grid of D-02-13, below the 360 MiB VmPeak of the made files (run 46123496042).
TEST_CAP: Final = 256 * MIB
CONTROL_CAP: Final = 4096 * MIB
CAP_PROBE: Final = Path(__file__).with_name("probes") / "as_cap.py"
RESULTS: Final = frozenset({"review", "failed", "confirm"})
DASH: Final = "-"


# -- the mounted set ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RealCorpus:
    root: Path
    derived: Path
    originals: tuple[dict[str, Any], ...]
    conversions: tuple[dict[str, Any], ...]


def _manifest(folder: str, variable: str) -> list[dict[str, Any]]:
    path = Path(folder) / MANIFEST
    if not folder or not path.is_file():
        pytest.fail(f"{variable} names no folder with {MANIFEST} (sandbox.yml fetches and mounts it)")
    files = json.loads(path.read_text(encoding="utf-8")).get("files")
    if not isinstance(files, list) or not files:
        pytest.fail(f"{MANIFEST} of {variable} lists no file")
    return files


def load_real_corpus(env: Mapping[str, str]) -> RealCorpus:
    """Both mounted folders with their manifests; fails loudly (never skips) when one is missing."""
    root, derived = env.get(REAL_CORPUS_ENV, ""), env.get(REAL_DERIVED_ENV, "")
    originals = _manifest(root, REAL_CORPUS_ENV)
    conversions = _manifest(derived, REAL_DERIVED_ENV)
    return RealCorpus(Path(root), Path(derived), tuple(originals), tuple(conversions))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


@pytest.fixture(scope="session")
def real_corpus() -> RealCorpus:
    corpus = load_real_corpus(os.environ)
    # The mount holds the files of the table, byte for byte (the hash is checked on the runner, too).
    for entry in corpus.originals:
        if sha256_of(corpus.root / entry["name"]) != entry["sha256"]:
            pytest.fail(f"{entry['name']} in {REAL_CORPUS_ENV} does not match its sha256")
    return corpus


# -- sampling soffice.bin ----------------------------------------------------------------


def address_space_limit(limits_text: str) -> str:
    """The soft "Max address space" of /proc/<pid>/limits: unlimited, a byte count, or - when absent."""
    for line in limits_text.splitlines():
        if line.startswith("Max address space"):
            fields = line.removeprefix("Max address space").split()
            if fields and (fields[0] == "unlimited" or fields[0].isdigit()):
                return fields[0]
    return DASH


def _own_pids() -> Iterator[int]:
    uid = os.getuid() if sys.platform != "win32" else -1
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
        except OSError:
            continue
        yield int(entry.name)


@dataclass(slots=True)
class Sampler:
    """VmPeak, VmHWM and the address space limit of every soffice.bin of this uid, every SAMPLE_S."""

    vmpeak_kb: int = 0
    vmhwm_kb: int = 0
    samples: int = 0
    as_limits: set[str] = field(default_factory=set)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def __enter__(self) -> "Sampler":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample()
            self._stop.wait(SAMPLE_S)

    def sample(self) -> None:
        for pid in _own_pids():
            folder = PROC / str(pid)
            try:
                if (folder / "comm").read_text(encoding="ascii").strip() != SOFFICE_BIN:
                    continue
                status = (folder / "status").read_text(encoding="ascii", errors="replace")
                limits = (folder / "limits").read_text(encoding="ascii", errors="replace")
            except OSError:
                continue
            values = vm_values(status)
            if values:
                self.samples += 1
                self.vmpeak_kb = max(self.vmpeak_kb, values.get("VmPeak", 0))
                self.vmhwm_kb = max(self.vmhwm_kb, values.get("VmHWM", 0))
                self.as_limits.add(address_space_limit(limits))


# -- what soffice did --------------------------------------------------------------------


def soffice_end(exc: BaseException | None) -> str:
    """How the soffice step ended, as a word: pdf, timeout, exit=<n> signal=<n>, template <reason> or a type."""
    if exc is None:
        return "pdf"
    if isinstance(exc, child.ChildTimeout):
        return "timeout"
    if isinstance(exc, child.ChildFailed):
        return f"exit={exc.exit_code} signal={exc.signal}"
    if isinstance(exc, soffice.ProfileTemplateMissing):
        return f"template {exc.reason}"
    if isinstance(exc, soffice.ConversionFailed):
        return "no_pdf"
    return type(exc).__name__


@dataclass(slots=True)
class WatchedConvert:
    """soffice.convert as the runner calls it, noting how it ended and the pages of its PDF."""

    end: str | None = None
    pages: int | None = None
    tail: str = ""

    async def __call__(self, src: Path, outdir: Path, job_id: str, *args: Any) -> Path:
        try:
            pdf = await soffice.convert(src, outdir, job_id, *args)
        except BaseException as exc:
            self.end = soffice_end(exc)
            self.tail = exc.stderr_tail if isinstance(exc, child.ChildFailed) else ""
            raise
        self.end = soffice_end(None)
        with pymupdf.open(pdf) as document:
            self.pages = document.page_count
        return pdf


def source_pages(path: Path) -> int | None:
    """The page count of a source PDF, for the record only (the product reports it only on review)."""
    try:
        with pymupdf.open(path) as document:
            return document.page_count
    except Exception:  # a PDF MuPDF cannot open has no count; the product decides the result
        return None


def pages_of(run: product_path.ProductRun, watched: WatchedConvert, path: Path) -> tuple[int | None, str]:
    """The page count and where it comes from: the product, the PDF of soffice, or the source PDF."""
    if run.pages is not None:
        return run.pages, "product"
    if watched.pages is not None:
        return watched.pages, "soffice_pdf"
    if product_path.format_of(path.name) == "pdf":
        pages = source_pages(path)
        return pages, DASH if pages is None else "source"
    return None, DASH


def corpus_entry(
    path: Path, origin: str, run: product_path.ProductRun, watched: WatchedConvert, sampler: Sampler
) -> dict[str, Any]:
    """One file of soffice_corpus in measurements.json: names and numbers only."""
    ran = watched.end is not None
    pages, pages_from = pages_of(run, watched, path)
    return {
        "format": product_path.format_of(path.name),
        "herkunft": origin,
        "bytes": path.stat().st_size,
        "ergebnis": run.result,
        "grund": run.reason,
        "soffice_ende": watched.end,
        "soffice_vmpeak_kb": sampler.vmpeak_kb if ran else None,
        "soffice_vmhwm_kb": sampler.vmhwm_kb if ran else None,
        "samples": sampler.samples,
        "as_limit": ",".join(sorted(sampler.as_limits)) or DASH,
        "ms": run.ms,
        "seiten": pages,
        "seiten_herkunft": pages_from,
        "stufen": list(run.stages),
    }


def _v(value: object) -> str:
    return DASH if value is None else str(value).replace(" ", "_")


def corpus_line(name: str, entry: Mapping[str, Any]) -> str:
    return (
        f"SOFFICE-CORPUS doc={name} format={entry['format']} origin={entry['herkunft']} bytes={entry['bytes']} "
        f"result={entry['ergebnis']} reason={_v(entry['grund'])} soffice={_v(entry['soffice_ende'])} "
        f"vmpeak_kb={_v(entry['soffice_vmpeak_kb'])} vmhwm_kb={_v(entry['soffice_vmhwm_kb'])} "
        f"samples={entry['samples']} as_limit={entry['as_limit']} ms={entry['ms']} pages={_v(entry['seiten'])} "
        f"pages_from={entry['seiten_herkunft']}"
    )


def convert_line(entry: Mapping[str, Any]) -> str:
    return (
        f"SOFFICE-CORPUS-CONVERT source={entry['source']} format={entry['format']} "
        f"result={_v(entry['result'])} bytes={entry['bytes']} images={entry['images']} ms={entry['ms']}"
    )


def leftovers(job_id: int) -> list[str]:
    """A job profile or a single-instance socket of this uid that is still in /tmp."""
    root = Path(soffice.PROFILE_ROOT)
    uid = os.getuid() if sys.platform != "win32" else -1
    found = []
    for entry in root.glob(soffice.IPC_SOCKET_GLOB):
        try:
            if soffice.is_own_ipc_socket(entry.name, entry.lstat(), uid):
                found.append(entry.name)
        except OSError:
            continue
    if soffice.job_profile(str(job_id)).exists():
        found.append(f"lo-{job_id}")
    return found


def _say(capsys: pytest.CaptureFixture[str], lines: list[str]) -> None:
    """Outside the capture, so the lines stand in the job log of a passing run, too."""
    with capsys.disabled():
        print()
        for line in lines:
            print(line)


# -- step 3: the measurement -------------------------------------------------------------


async def test_the_real_corpus_goes_through_the_product_path_and_soffice_is_measured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], real_corpus: RealCorpus
) -> None:
    assert become_subreaper()
    lines = [convert_line(entry) for entry in real_corpus.conversions]
    files = [(real_corpus.root / entry["name"], "original") for entry in real_corpus.originals]
    files += [
        (real_corpus.derived / entry["name"], entry["source"])
        for entry in real_corpus.conversions
        if entry["result"] == "ok"
    ]
    entries: dict[str, dict[str, Any]] = {}
    left: dict[str, list[str]] = {}
    jail_marks = 0
    for index, (path, origin) in enumerate(files):
        job_id = JOB_BASE + index
        watched = WatchedConvert()
        with Sampler() as sampler:
            run = await product_path.run_product(path, job_id, tmp_path / f"job-{index}", watched)
        entries[path.name] = corpus_entry(path, origin, run, watched, sampler)
        lines.append(corpus_line(path.name, entries[path.name]))
        if watched.tail:
            lines.append(f"SOFFICE-CORPUS-TAIL doc={path.name} tail={watched.tail.replace(chr(10), ' | ')[:600]}")
        jail_marks += run.jail_marks
        if found := leftovers(job_id):
            left[path.name] = found
    zombies = settled_zombies()
    lines.append(f"JAIL-ZOMBIES after=corpus n={len(zombies)}")
    _say(capsys, lines)
    record_measurement("soffice_corpus", entries)
    record_measurement("soffice_corpus_convert", list(real_corpus.conversions))
    report = "\n".join(lines)

    # The set is whole: every PDF became a DOCX and an ODT, every file was measured.
    pdfs = sorted(entry["name"] for entry in real_corpus.originals if entry["format"] == "pdf")
    assert pdfs, report
    sources = sorted(entry["source"] for entry in real_corpus.conversions)
    assert sources == sorted(pdfs * 2), report
    failed = [entry["name"] for entry in real_corpus.conversions if entry["result"] != "ok"]
    assert failed == [], f"the foreign tool did not convert: {failed}\n{report}"
    assert len(entries) == len(real_corpus.originals) + len(real_corpus.conversions), report
    # The product answered every file with a word of its own: review, confirm or failed with a reason.
    for name, entry in entries.items():
        assert entry["ergebnis"] in RESULTS, (name, report)
        assert (entry["grund"] is not None) == (entry["ergebnis"] == "failed"), (name, report)
        if entry["format"] == "pdf":
            assert entry["soffice_ende"] is None, (name, report)
    # Positive control of the sampler: where soffice ran, it was seen, with no cap (address_space None).
    for name, entry in entries.items():
        if entry["soffice_ende"] is not None:
            assert entry["samples"] > 0, (name, report)
            assert entry["soffice_vmpeak_kb"] > 0, (name, report)
            assert entry["as_limit"] == "unlimited", (name, report)
    assert any(entry["soffice_ende"] is not None for entry in entries.values()), report
    assert jail_marks == 0, report
    assert left == {}, report
    assert zombies == [], report


# -- step 5: over the cap ----------------------------------------------------------------


def capped_command(cap: int) -> Any:
    """soffice.command with the probe in front: the same soffice, under RLIMIT_AS cap."""
    original = soffice.command

    def command(src: Path, outdir: Path, job_id: str) -> list[str]:
        return [sys.executable, "-I", str(CAP_PROBE), str(cap), *original(src, outdir, job_id)]

    return command


def probe_line(label: str, cap: int, entry: Mapping[str, Any]) -> str:
    return (
        f"SOFFICE-CAP-PROBE run={label} cap={cap} result={entry['result']} reason={_v(entry['reason'])} "
        f"soffice={_v(entry['soffice'])} as_limit={entry['as_limit']} vmpeak_kb={entry['vmpeak_kb']} "
        f"zombies={entry['zombies']} leftovers={','.join(entry['leftovers']) or DASH}"
    )


async def test_negative_soffice_over_a_small_cap_ends_with_a_reason_and_leaves_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, real_corpus: RealCorpus
) -> None:
    assert become_subreaper()
    docx = sorted(entry["name"] for entry in real_corpus.originals if entry["format"] == "docx")
    assert docx, "the real corpus holds no DOCX"
    source = real_corpus.root / docx[0]
    measured: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    # The control first: it proves the probe works and the limit reaches soffice.bin.
    for label, cap, job_id in (("control", CONTROL_CAP, CONTROL_JOB), ("capped", TEST_CAP, CAPPED_JOB)):
        monkeypatch.setattr(soffice, "command", capped_command(cap))
        watched = WatchedConvert()
        with Sampler() as sampler:
            run = await product_path.run_product(source, job_id, tmp_path / label, watched)
        zombies = settled_zombies()
        measured[label] = {
            "cap": cap,
            "result": run.result,
            "reason": run.reason,
            "soffice": watched.end,
            "as_limit": ",".join(sorted(sampler.as_limits)) or DASH,
            "vmpeak_kb": sampler.vmpeak_kb,
            "zombies": len(zombies),
            "leftovers": leftovers(job_id),
            "jail_marks": run.jail_marks,
        }
        lines.append(probe_line(label, cap, measured[label]))
        if watched.tail:
            lines.append(f"SOFFICE-CAP-PROBE-TAIL run={label} tail={watched.tail.replace(chr(10), ' | ')[:600]}")
    _say(capsys, lines)
    record_measurement("soffice_cap_probe", {"doc": source.name, **measured})
    report = "\n".join(lines)

    control, capped = measured["control"], measured["capped"]
    assert control["result"] == "review", report
    assert control["soffice"] == "pdf", report
    assert control["as_limit"] == str(CONTROL_CAP), report
    # Over the cap: a refusal with a reason of the closed list, no crash out of the runner.
    assert capped["result"] == "failed", report
    assert capped["reason"] == "render_failed", report
    assert capped["soffice"] not in {None, "pdf"}, report
    for entry in (control, capped):
        assert entry["zombies"] == 0, report
        assert entry["leftovers"] == [], report
        assert entry["jail_marks"] == 0, report
