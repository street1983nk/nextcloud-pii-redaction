"""Format by magic bytes, never by extension or mime."""

import zipfile
from pathlib import Path

from pii_redaction_backend.workers import sniff


def _zip(path: Path, entries: dict[str, str], *, stored_first: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        if stored_first is not None:
            archive.writestr(zipfile.ZipInfo(stored_first), entries.pop(stored_first))
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def test_a_pdf_is_recognised_by_its_header(tmp_path: Path) -> None:
    path = tmp_path / "no-extension"
    path.write_bytes(b"%PDF-1.7\n%...")
    assert sniff.detect(path) == "pdf"


def test_a_docx_needs_content_types_and_the_main_document(tmp_path: Path) -> None:
    path = _zip(tmp_path / "file.bin", {"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>"})
    assert sniff.detect(path) == "docx"


def test_an_odt_needs_the_mimetype_entry_first(tmp_path: Path) -> None:
    entries = {"mimetype": "application/vnd.oasis.opendocument.text", "content.xml": "<office/>"}
    path = _zip(tmp_path / "file.docx", entries, stored_first="mimetype")
    assert sniff.detect(path) == "odt"


def test_a_spreadsheet_is_not_a_text_document(tmp_path: Path) -> None:
    entries = {"mimetype": "application/vnd.oasis.opendocument.spreadsheet", "content.xml": "<office/>"}
    assert sniff.detect(_zip(tmp_path / "file.odt", entries, stored_first="mimetype")) is None


def test_an_odt_mimetype_that_is_not_first_does_not_count(tmp_path: Path) -> None:
    entries = {"content.xml": "<office/>", "mimetype": "application/vnd.oasis.opendocument.text"}
    assert sniff.detect(_zip(tmp_path / "file.odt", entries)) is None


def test_plain_text_and_other_zips_are_nothing(tmp_path: Path) -> None:
    text = tmp_path / "file.pdf"
    text.write_text("just text, named like a pdf", encoding="utf-8")
    assert sniff.detect(text) is None
    assert sniff.detect(_zip(tmp_path / "other.zip", {"readme.txt": "hello"})) is None
    assert sniff.detect(_zip(tmp_path / "half.docx", {"[Content_Types].xml": "<Types/>"})) is None


def test_a_broken_zip_and_an_empty_file_are_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"PK\x03\x04garbage")
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    assert sniff.detect(broken) is None
    assert sniff.detect(empty) is None
