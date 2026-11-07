"""The fixtures of the integration proof and the stdlib PDF reader of the copy check.

ci/make_fixtures.py and ci/pdf_text.py run in the CI runner without PyMuPDF.
PyMuPDF appears here only, as the independent positive control: it opens the
fixture, finds two pages and finds the canary in the text, so the canary scan
at the end of the run (plan 17) has something it must be able to find.
"""

import importlib.util
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree

import pymupdf
import pytest

from tests.conftest import REPO_ROOT

CI = REPO_ROOT / "ci"
CANARY = "PIIKANARIE7Q4XZ9"
NAMES = ("Bescheid 2026-114.pdf", "Antrag.docx", "Vermerk.odt", "notes.txt")


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"ci_{name}", CI / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = _load("make_fixtures")
pdf_text = _load("pdf_text")


@pytest.fixture
def made(tmp_path: Path) -> Path:
    result = subprocess.run(  # noqa: S603 - a fixed script of this repository
        [sys.executable, "-I", str(CI / "make_fixtures.py"), str(tmp_path)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return tmp_path


def _stream_bodies(raw: bytes) -> bytes:
    return b"".join(re.findall(rb"stream\n(.*?)endstream", raw, re.DOTALL))


def test_the_script_writes_exactly_the_four_files(made: Path) -> None:
    assert sorted(path.name for path in made.iterdir()) == sorted(NAMES)


def test_the_canary_is_in_no_file_name() -> None:
    assert all(CANARY not in name for name in NAMES)
    assert CANARY in fixtures.CANARY


def test_the_pdf_carries_the_canary_in_its_raw_bytes_and_only_in_a_content_stream(made: Path) -> None:
    raw = (made / NAMES[0]).read_bytes()

    assert raw.startswith(b"%PDF-1.4")
    assert raw.count(CANARY.encode()) == 1
    assert CANARY.encode() in _stream_bodies(raw)
    assert b"/Info" not in raw
    assert b"/Filter" not in raw


def test_pymupdf_opens_two_pages_and_finds_the_canary_and_the_umlauts(made: Path) -> None:
    with pymupdf.open(made / NAMES[0]) as document:
        assert document.page_count == 2
        first = document[0].get_text()
        second = document[1].get_text()
        meta = " ".join(str(value) for value in (document.metadata or {}).values())

    assert CANARY in first
    assert "Rückfragen" in first
    assert "Grüßen" in second
    assert CANARY not in second
    assert CANARY not in meta


def test_pymupdf_finds_valid_cross_reference_offsets(made: Path) -> None:
    with pymupdf.open(made / NAMES[0]) as document:
        assert not document.is_repaired


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def test_the_docx_has_four_parts_and_the_canary_only_in_the_body(made: Path) -> None:
    members = _members(made / NAMES[1])

    assert set(members) == {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
    }
    assert not any(name.startswith("docProps") for name in members)
    assert [name for name, data in members.items() if CANARY.encode() in data] == ["word/document.xml"]
    for data in members.values():
        ElementTree.fromstring(data)  # noqa: S314 - our own fixed XML


def test_the_odt_starts_with_a_stored_mimetype_and_has_the_canary_only_in_content(made: Path) -> None:
    path = made / NAMES[2]
    with zipfile.ZipFile(path) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert archive.read(first) == b"application/vnd.oasis.opendocument.text"
    members = _members(path)

    assert "meta.xml" not in members
    assert set(members) == {"mimetype", "META-INF/manifest.xml", "content.xml", "styles.xml"}
    assert [name for name, data in members.items() if CANARY.encode() in data] == ["content.xml"]
    for name, data in members.items():
        if name.endswith(".xml"):
            ElementTree.fromstring(data)  # noqa: S314 - our own fixed XML


def test_the_text_file_carries_no_canary(made: Path) -> None:
    assert CANARY.encode() not in (made / NAMES[3]).read_bytes()


def test_pdf_text_finds_the_canary_in_the_fixture(made: Path) -> None:
    result = subprocess.run(  # noqa: S603 - a fixed script of this repository
        [sys.executable, "-I", str(CI / "pdf_text.py"), str(made / NAMES[0])],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    text = result.stdout.decode("utf-8")
    assert CANARY in text
    assert "Bitte geben Sie bei Rückfragen" in text


def test_pdf_text_reads_a_flate_stream_the_raw_bytes_hide(tmp_path: Path) -> None:
    target = tmp_path / "flate.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), f"Merkzeichen {CANARY}", fontname="helv", fontsize=12)
        document.save(target, garbage=4, deflate=True)
    raw = target.read_bytes()

    assert CANARY.encode() not in raw
    assert CANARY in pdf_text.text_of(raw)


def test_pdf_text_reads_the_placeholder_copy_and_finds_no_canary(tmp_path: Path) -> None:
    from pii_redaction_backend.workers import placeholder

    target = tmp_path / "copy.pdf"
    assert placeholder.main([str(target), "7"]) == 0
    text = pdf_text.text_of(target.read_bytes())

    assert "Placeholder from PII Redaction" in text
    assert CANARY not in text


def test_pdf_text_decodes_escapes_hex_and_arrays() -> None:
    body = b"BT (a\\(b\\)c\\\\d\\101) Tj <48656c6c6f> Tj [(Wo) -120 (rld)] TJ % (ignored)\n ET"

    assert pdf_text.runs(body) == ["a(b)c\\dA", "Hello", "World"]


def test_pdf_text_skips_images_and_unknown_filters() -> None:
    data = (
        b"<< /Subtype /Image /Length 5 >>\nstream\n(sec)endstream\n"
        b"<< /Filter /DCTDecode /Length 5 >>\nstream\n(sec)endstream\n"
        b"<< /Length 5 >>\nstream\n(ok) Tj\nendstream\n"
    )

    assert pdf_text.text_of(data) == "ok"


def test_both_scripts_refuse_a_wrong_call() -> None:
    assert fixtures.main([]) == 2
    assert pdf_text.main([]) == 2
    assert pdf_text.main(["/nonexistent/file.pdf"]) == 2


def test_neither_script_imports_pymupdf() -> None:
    for name in ("make_fixtures.py", "pdf_text.py"):
        source = (CI / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(fitz|pymupdf)\b", source, re.MULTILINE), name
