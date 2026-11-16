"""Stage A of the pre-check: the format by its bytes, compared with what the file claims to be."""

from pathlib import Path

import pytest

from tests.intake_builders import compound_file, docx, odt, write_zip
from pii_redaction_backend.intake import magic
from pii_redaction_backend.intake.magic import detect
from pii_redaction_backend.intake.verdict import Rejected

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def verdict_of(path: Path, expected: str) -> str:
    try:
        detect(path, expected)  # type: ignore[arg-type]
    except Rejected as rejected:
        return rejected.verdict
    return "ok"


def test_an_empty_file_is_damaged(tmp_path: Path) -> None:
    path = tmp_path / "empty"
    path.write_bytes(b"")
    assert verdict_of(path, "pdf") == "damaged"


def test_a_pdf_header_at_offset_zero_is_a_pdf(tmp_path: Path) -> None:
    path = tmp_path / "a"
    path.write_bytes(PDF)
    assert detect(path, "pdf") == "pdf"


@pytest.mark.parametrize("prefix", [b" ", b"GIF89a", b"PK\x03\x04junk" + b"\x00" * 30])
def test_a_pdf_header_behind_a_prefix_is_damaged(tmp_path: Path, prefix: bytes) -> None:
    path = tmp_path / "polyglot"
    path.write_bytes(prefix + PDF)
    assert verdict_of(path, "pdf") == "damaged"


def test_a_pdf_header_far_behind_is_not_a_pdf(tmp_path: Path) -> None:
    path = tmp_path / "late"
    path.write_bytes(b"x" * 2048 + PDF)
    assert verdict_of(path, "pdf") == "unsupported_format"


def test_a_docx_and_an_odt_are_told_apart(tmp_path: Path) -> None:
    assert detect(docx(tmp_path / "d"), "docx") == "docx"
    assert detect(odt(tmp_path / "o"), "odt") == "odt"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("pdf", "docx"), ("pdf", "odt"), ("docx", "pdf"), ("docx", "odt"), ("odt", "docx"), ("odt", "pdf")],
)
def test_a_file_that_is_not_what_it_claims_is_wrong_type(tmp_path: Path, kind: str, expected: str) -> None:
    path = tmp_path / "f"
    if kind == "pdf":
        path.write_bytes(PDF)
    elif kind == "docx":
        docx(path)
    else:
        odt(path)
    assert verdict_of(path, expected) == "wrong_type"


def test_a_zip_that_is_neither_docx_nor_odt_is_unsupported(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "z", [("readme.txt", b"hello")])
    assert verdict_of(path, "docx") == "unsupported_format"


def test_an_odt_with_another_mimetype_is_unsupported(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "s", [("mimetype", b"application/vnd.oasis.opendocument.spreadsheet")])
    assert verdict_of(path, "odt") == "unsupported_format"


@pytest.mark.parametrize("stream", ["EncryptedPackage", "EncryptionInfo"])
def test_a_password_protected_office_file_is_encrypted(tmp_path: Path, stream: str) -> None:
    path = compound_file(tmp_path / "enc", ["\x06DataSpaces", stream])
    assert verdict_of(path, "docx") == "encrypted_document"


def test_the_encryption_stream_is_found_in_a_later_directory_sector(tmp_path: Path) -> None:
    streams = [f"Stream{number}" for number in range(9)] + ["EncryptedPackage"]
    path = compound_file(tmp_path / "long", streams)
    assert path.stat().st_size > 512 * 4  # header, FAT and more than one directory sector
    assert verdict_of(path, "docx") == "encrypted_document"


def test_an_old_binary_office_file_is_unsupported(tmp_path: Path) -> None:
    path = compound_file(tmp_path / "doc", ["WordDocument", "1Table"])
    assert verdict_of(path, "docx") == "unsupported_format"


def test_an_encrypted_office_file_claiming_to_be_a_pdf_is_wrong_type(tmp_path: Path) -> None:
    path = compound_file(tmp_path / "enc", ["EncryptedPackage"])
    assert verdict_of(path, "pdf") == "wrong_type"


def test_a_truncated_compound_file_is_damaged(tmp_path: Path) -> None:
    path = compound_file(tmp_path / "cut", ["EncryptedPackage"])
    path.write_bytes(path.read_bytes()[:600])
    assert verdict_of(path, "docx") == "damaged"


def test_a_compound_file_with_a_directory_cycle_is_damaged(tmp_path: Path) -> None:
    path = compound_file(tmp_path / "cycle", ["A", "B", "C", "D", "E"])
    data = bytearray(path.read_bytes())
    # FAT entry of directory sector 2 points back to sector 1.
    data[512 + 2 * 4 : 512 + 3 * 4] = (1).to_bytes(4, "little")
    path.write_bytes(bytes(data))
    assert verdict_of(path, "docx") == "damaged"


def test_a_source_over_the_size_limit_is_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "big"
    path.write_bytes(PDF)
    monkeypatch.setattr(magic, "MAX_SOURCE_BYTES", len(PDF))
    assert detect(path, "pdf") == "pdf"  # exactly at the limit
    monkeypatch.setattr(magic, "MAX_SOURCE_BYTES", len(PDF) - 1)
    assert verdict_of(path, "pdf") == "too_large"


def test_unknown_bytes_are_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert verdict_of(path, "pdf") == "unsupported_format"
