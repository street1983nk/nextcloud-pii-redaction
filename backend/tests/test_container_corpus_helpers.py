"""The parts of the corpus measurement of plan 02-24 that run without the container.

The harness (tests/product_path.py) has to report the product's answer and
nothing else; here it drives the real Runner with the real pre-check, cleaner
and render code run in process, and a double of LibreOffice. The sampler
parsers, the entry of measurements.json, the cap probe and the loud failure
for a missing mount are checked on every machine, so a broken helper cannot
make the container measurement look complete.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from pii_redaction_backend import nc
from pii_redaction_backend.model import AckResult, Reason, Task
from pii_redaction_backend.runner import runner
from pii_redaction_backend.workers import child, soffice
from tests import product_path
from tests.test_container_corpus import (
    CAP_PROBE,
    REAL_CORPUS_ENV,
    REAL_DERIVED_ENV,
    Sampler,
    WatchedConvert,
    address_space_limit,
    capped_command,
    corpus_entry,
    corpus_line,
    load_real_corpus,
    pages_of,
    soffice_end,
)
from tests.test_jail_container import docx_with_pages

CLAIM = nc.Claim(
    job_id=990_399, task=Task.ANALYZE, token="c" * 64, file_id=1, user_id="corpus", etag="e", lease_seconds=60
)

LIMITS = (
    "Limit                     Soft Limit           Hard Limit           Units     \n"
    "Max cpu time              125                  125                  seconds   \n"
    "Max address space         {soft}           {hard}           bytes     \n"
    "Max core file size        0                    0                    bytes     \n"
)


# -- the sampler and the words ------------------------------------------------------------


@pytest.mark.parametrize(
    ("soft", "expected"),
    [("unlimited", "unlimited"), ("268435456", "268435456"), ("4294967296", "4294967296")],
)
def test_the_address_space_limit_is_read_from_proc_limits(soft: str, expected: str) -> None:
    assert address_space_limit(LIMITS.format(soft=soft, hard="unlimited")) == expected


@pytest.mark.parametrize(
    "text", ["", "Max cpu time 1 1 seconds\n", "Max address space\n", "Max address space   lots  lots  bytes\n"]
)
def test_negative_no_address_space_line_is_a_dash(text: str) -> None:
    assert address_space_limit(text) == "-"


def test_a_sampler_that_saw_nothing_stays_empty() -> None:
    sampler = Sampler()
    assert (sampler.vmpeak_kb, sampler.vmhwm_kb, sampler.samples, sampler.as_limits) == (0, 0, 0, set())


@pytest.mark.parametrize(
    ("exc", "word"),
    [
        (None, "pdf"),
        (child.ChildTimeout(), "timeout"),
        (child.ChildFailed(-9), "exit=-9 signal=9"),
        (child.ChildFailed(1), "exit=1 signal=None"),
        (soffice.ProfileTemplateMissing("missing"), "template missing"),
        (soffice.ConversionFailed(), "no_pdf"),
        (OSError("x"), "OSError"),
    ],
)
def test_how_soffice_ended_is_one_word(exc: BaseException | None, word: str) -> None:
    assert soffice_end(exc) == word


# -- the mounted set ---------------------------------------------------------------------


def _folder(root: Path, files: object) -> Path:
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    return root


def test_positive_control_both_mounts_are_read(tmp_path: Path) -> None:
    root = _folder(tmp_path / "corpus", [{"name": "a.pdf", "format": "pdf", "sha256": "0"}])
    derived = _folder(tmp_path / "derived", [{"name": "a_pdf.docx", "source": "a.pdf", "result": "ok"}])
    corpus = load_real_corpus({REAL_CORPUS_ENV: str(root), REAL_DERIVED_ENV: str(derived)})
    assert corpus.root == root
    assert corpus.derived == derived
    assert corpus.originals[0]["name"] == "a.pdf"
    assert corpus.conversions[0]["name"] == "a_pdf.docx"


def test_negative_a_missing_mount_fails_loudly_and_never_skips(tmp_path: Path) -> None:
    root = _folder(tmp_path / "corpus", [{"name": "a.pdf"}])
    empty = _folder(tmp_path / "empty", [])
    for env in (
        {},
        {REAL_CORPUS_ENV: str(root)},
        {REAL_DERIVED_ENV: str(root)},
        {REAL_CORPUS_ENV: str(root), REAL_DERIVED_ENV: str(tmp_path / "nowhere")},
        {REAL_CORPUS_ENV: str(root), REAL_DERIVED_ENV: str(empty)},
    ):
        with pytest.raises(pytest.fail.Exception):
            load_real_corpus(env)


# -- the cap probe -----------------------------------------------------------------------


def _probe() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("as_cap_probe", CAP_PROBE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_probe_parses_the_cap_and_the_command() -> None:
    assert _probe().parse(["268435456", "/usr/bin/soffice", "--headless"]) == (
        268435456,
        ["/usr/bin/soffice", "--headless"],
    )


@pytest.mark.parametrize(
    "argv",
    [[], ["268435456"], ["0", "/bin/true"], ["-1", "/bin/true"], ["256M", "/bin/true"], ["1", "soffice"], ["²", "/x"]],
)
def test_negative_the_probe_refuses_anything_else(argv: list[str]) -> None:
    assert _probe().parse(argv) is None
    assert _probe().main(argv) == 2


def test_the_capped_command_is_the_product_command_behind_the_probe(tmp_path: Path) -> None:
    product = soffice.command(tmp_path / "a.docx", tmp_path / "out", "990391")
    capped = capped_command(256 * 1024 * 1024)(tmp_path / "a.docx", tmp_path / "out", "990391")
    assert capped[1:4] == ["-I", str(CAP_PROBE), str(256 * 1024 * 1024)]
    assert capped[0].startswith("/") or capped[0][1:3] == ":\\"
    assert capped[4:] == product


def test_the_capped_run_after_the_control_has_exactly_one_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The negative test patches soffice.command for the control (4 GiB) and then for the capped run (256 MiB).
    # A wrapper around the already patched command would put a second probe behind the first, which then
    # tries to raise the hard limit again and dies with EPERM before soffice starts (sandbox run 46150036977).
    product = soffice.command(tmp_path / "a.docx", tmp_path / "out", "990391")
    for cap in (4096 * 1024 * 1024, 256 * 1024 * 1024):
        monkeypatch.setattr(soffice, "command", capped_command(cap))
    capped = soffice.command(tmp_path / "a.docx", tmp_path / "out", "990391")
    assert capped.count(str(CAP_PROBE)) == 1
    assert capped[1:4] == ["-I", str(CAP_PROBE), str(256 * 1024 * 1024)]
    assert capped[4:] == product


# -- the harness: the real Runner, the real check children in process -----------------------


def _pdf(path: Path, pages: int) -> Path:
    document = pymupdf.open()
    for number in range(pages):
        document.new_page(width=595, height=842).insert_text((72, 100), f"Seite {number + 1}")
    document.save(path)
    document.close()
    return path


async def in_process_child(
    args: list[str],
    *,
    profile: str,
    cwd: Path,
    read: tuple[str, ...] = (),
    write: tuple[str, ...] = (),
    timeout_s: float | None = None,
) -> None:
    """The real main of each Python child, called here instead of in its jail."""
    del timeout_s
    name = args[3].rsplit(".", 1)[-1]
    assert profile == name
    assert write == (str(cwd),)
    assert all(Path(path).is_relative_to(cwd) for path in read)
    if name == "precheck":
        from pii_redaction_backend.workers import precheck as worker
    elif name == "sanitize":
        from pii_redaction_backend.workers import sanitize as worker
    else:
        from pii_redaction_backend.workers import render as worker
    if worker.main(args[4:]) != 0:
        raise child.ChildFailed(2)


class FakeSoffice:
    """LibreOffice for the harness test: a PDF of pages pages, or the error it is told to raise."""

    def __init__(self, pages: int = 3, error: Exception | None = None) -> None:
        self.pages = pages
        self.error = error
        self.sources: list[Path] = []

    async def __call__(self, src: Path, outdir: Path, job_id: str, *_args: Any) -> Path:
        assert job_id.isdigit()
        self.sources.append(src)
        if self.error is not None:
            raise self.error
        return await asyncio.to_thread(self._write, outdir, src.stem)

    def _write(self, outdir: Path, stem: str) -> Path:
        outdir.mkdir(parents=True, exist_ok=True)
        return _pdf(outdir / f"{stem}.pdf", self.pages)


def _watched(monkeypatch: pytest.MonkeyPatch, fake: FakeSoffice) -> WatchedConvert:
    monkeypatch.setattr(soffice, "convert", fake)
    return WatchedConvert()


async def test_harness_a_docx_reaches_review_through_cleaner_and_soffice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = docx_with_pages(tmp_path / "a.docx", 4)
    fake = FakeSoffice(pages=4)
    watched = _watched(monkeypatch, fake)

    run = await product_path.run_product(source, 990_300, tmp_path / "root", watched, in_process_child)

    assert (run.result, run.reason, run.pages) == (AckResult.REVIEW.value, None, 4)
    assert "converting" in run.stages
    # LibreOffice only ever saw the cleaned copy, never the source.
    assert fake.sources[0].stem == runner.CLEAN_STEM
    assert (watched.end, watched.pages) == ("pdf", 4)
    entry = corpus_entry(source, "original", run, watched, Sampler(samples=5, vmpeak_kb=700, vmhwm_kb=300))
    assert entry["ergebnis"] == "review"
    assert entry["grund"] is None
    assert (entry["soffice_ende"], entry["soffice_vmpeak_kb"], entry["soffice_vmhwm_kb"]) == ("pdf", 700, 300)
    assert (entry["seiten"], entry["seiten_herkunft"]) == (4, "product")
    assert entry["format"] == "docx"
    assert corpus_line("a.docx", entry).startswith("SOFFICE-CORPUS doc=a.docx format=docx origin=original bytes=")


async def test_harness_a_failing_soffice_is_render_failed_and_noted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = docx_with_pages(tmp_path / "a.docx", 2)
    watched = _watched(monkeypatch, FakeSoffice(error=child.ChildFailed(-6, "abort tail")))

    run = await product_path.run_product(source, 990_301, tmp_path / "root", watched, in_process_child)

    assert (run.result, run.reason) == ("failed", Reason.RENDER_FAILED.value)
    assert watched.end == "exit=-6 signal=6"
    assert watched.tail == "abort tail"
    entry = corpus_entry(source, "x.pdf", run, watched, Sampler(samples=2, vmpeak_kb=900, vmhwm_kb=100))
    assert entry["soffice_vmpeak_kb"] == 900
    assert entry["herkunft"] == "x.pdf"
    assert (entry["seiten"], entry["seiten_herkunft"]) == (None, "-")


async def test_harness_a_pdf_never_reaches_soffice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _pdf(tmp_path / "a.pdf", 3)
    fake = FakeSoffice()
    watched = _watched(monkeypatch, fake)

    run = await product_path.run_product(source, 990_302, tmp_path / "root", watched, in_process_child)

    assert (run.result, run.pages) == ("review", 3)
    assert fake.sources == []
    entry = corpus_entry(source, "original", run, watched, Sampler())
    assert (entry["soffice_ende"], entry["soffice_vmpeak_kb"], entry["soffice_vmhwm_kb"]) == (None, None, None)


async def test_harness_a_refusal_of_the_page_cap_is_a_result_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _pdf(tmp_path / "long.pdf", 301)
    watched = _watched(monkeypatch, FakeSoffice())

    run = await product_path.run_product(source, 990_303, tmp_path / "root", watched, in_process_child)

    assert (run.result, run.reason, run.pages) == ("failed", Reason.TOO_MANY_PAGES.value, None)
    # The product names no page count on a refusal; the record counts the source itself.
    assert pages_of(run, watched, source) == (301, "source")


async def test_harness_a_docx_over_the_page_cap_after_soffice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = docx_with_pages(tmp_path / "a.docx", 2)
    watched = _watched(monkeypatch, FakeSoffice(pages=301))

    run = await product_path.run_product(source, 990_304, tmp_path / "root", watched, in_process_child)

    assert (run.result, run.reason) == ("failed", Reason.TOO_MANY_PAGES.value)
    assert pages_of(run, watched, source) == (301, "soffice_pdf")


async def test_harness_a_damaged_file_is_refused_by_the_precheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "broken.docx"
    source.write_bytes(b"PK\x03\x04 not really a zip")
    fake = FakeSoffice()
    watched = _watched(monkeypatch, fake)

    run = await product_path.run_product(source, 990_305, tmp_path / "root", watched, in_process_child)

    assert run.result == "failed"
    assert run.reason in {"damaged", "wrong_type"}
    assert fake.sources == []
    assert watched.end is None


async def test_harness_a_file_over_the_download_cap_is_not_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pii_redaction_backend import config

    source = _pdf(tmp_path / "a.pdf", 1)
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", source.stat().st_size - 1)
    watched = _watched(monkeypatch, FakeSoffice())

    run = await product_path.run_product(source, 990_306, tmp_path / "root", watched, in_process_child)

    assert (run.result, run.reason) == ("failed", Reason.NOT_READABLE.value)


def test_harness_exactly_one_ack_or_the_run_is_broken() -> None:
    assert product_path.answer([("review", {"pages_total": 2})]) == ("review", None, 2)
    assert product_path.answer([("failed", {"reason": Reason.DAMAGED})]) == ("failed", "damaged", None)
    with pytest.raises(AssertionError):
        product_path.answer([])
    with pytest.raises(AssertionError):
        product_path.answer([("review", {}), ("failed", {})])


@pytest.mark.parametrize(("name", "fmt"), [("a.pdf", "pdf"), ("a.DOCX", "docx"), ("a_pdf.odt", "odt")])
def test_harness_the_format_comes_from_the_name(name: str, fmt: str) -> None:
    assert product_path.format_of(name) == fmt


@pytest.mark.parametrize("name", ["a.rtf", "a", "a.pdf.zip"])
def test_negative_harness_no_other_format(name: str) -> None:
    with pytest.raises(ValueError, match="no product format"):
        product_path.format_of(name)


async def test_harness_the_download_copies_and_hashes(tmp_path: Path) -> None:
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF-1.7 abc")
    world = product_path.Nextcloud(source)
    target = tmp_path / "src"
    result = await world.fetch(None, CLAIM, target, max_bytes=100)
    assert result.ok
    assert target.read_bytes() == source.read_bytes()
    assert result.size == len(b"%PDF-1.7 abc")
    small = await world.fetch(None, CLAIM, tmp_path / "src2", max_bytes=3)
    assert not small.ok
    assert not (tmp_path / "src2").exists()
