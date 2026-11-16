"""Stage B of the pre-check for ZIP packages: count first, then judge declarations, names and layout."""

import zipfile
from pathlib import Path

import pytest

from pii_redaction_backend.intake import zipcheck
from pii_redaction_backend.intake.limits import (
    ZIP_MAX_ENTRIES,
    ZIP_MAX_MEMBER_BYTES,
    ZIP_MAX_NAME_BYTES,
    ZIP_RATIO_MIN_BYTES,
)
from pii_redaction_backend.intake.verdict import Rejected
from pii_redaction_backend.intake.zipcheck import check_zip, normalized_name, read_member_head
from tests.intake_builders import docx, header_offset_of, odt, patch_central, write_zip

STORED = zipfile.ZIP_STORED


def verdict_of(path: Path) -> str:
    try:
        check_zip(path)
    except Rejected as rejected:
        return rejected.verdict
    return "ok"


def test_a_clean_docx_passes_and_reports_its_names(tmp_path: Path) -> None:
    report = check_zip(docx(tmp_path / "d"))
    assert report.entries == 2
    assert report.names == ("[Content_Types].xml", "word/document.xml")


def test_a_clean_odt_passes(tmp_path: Path) -> None:
    assert verdict_of(odt(tmp_path / "o")) == "ok"


@pytest.fixture(scope="module")
def entry_flood(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    folder = tmp_path_factory.mktemp("flood")
    at_limit = write_zip(folder / "at", [(f"p/{n}", b"") for n in range(ZIP_MAX_ENTRIES)], compression=STORED)
    over = write_zip(folder / "over", [(f"p/{n}", b"") for n in range(ZIP_MAX_ENTRIES + 1)], compression=STORED)
    return at_limit, over


def test_ten_thousand_entries_pass(entry_flood: tuple[Path, Path]) -> None:
    assert check_zip(entry_flood[0]).entries == ZIP_MAX_ENTRIES


def test_one_entry_more_is_too_large_before_zipfile_is_built(
    entry_flood: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        built.append(args)
        raise AssertionError("ZipFile must not be built")

    monkeypatch.setattr(zipcheck, "ZipFile", refuse)
    assert verdict_of(entry_flood[1]) == "too_large"
    assert built == []


def test_a_directory_longer_than_its_cap_is_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = docx(tmp_path / "d")
    with path.open("rb") as handle:
        _, length = zipcheck._central_directory(handle, path.stat().st_size)
    monkeypatch.setattr(zipcheck, "ZIP_MAX_CENTRAL_DIRECTORY_BYTES", length)
    assert verdict_of(path) == "ok"
    monkeypatch.setattr(zipcheck, "ZIP_MAX_CENTRAL_DIRECTORY_BYTES", length - 1)
    assert verdict_of(path) == "too_large"


PACKED = 20_000


@pytest.mark.parametrize(
    ("declared", "verdict"),
    [
        (100 * PACKED, "ok"),
        (100 * PACKED + 1, "too_large"),
        (999 * PACKED, "too_large"),
        (1000 * PACKED, "too_large"),
        (1000 * PACKED + 1, "unsafe_content"),
    ],
)
def test_the_ratio_is_judged_in_two_steps(tmp_path: Path, declared: int, verdict: str) -> None:
    path = docx(tmp_path / "r", [("word/media/blob", b"x" * PACKED)], compression=STORED)
    patch_central(path, 2, file_size=declared)
    assert verdict_of(path) == verdict


def test_the_ratio_is_judged_only_from_one_mib_on(tmp_path: Path) -> None:
    path = docx(tmp_path / "small", [("word/media/blob", b"x" * 1000)], compression=STORED)
    patch_central(path, 2, file_size=ZIP_RATIO_MIN_BYTES - 1)
    assert verdict_of(path) == "ok"
    patch_central(path, 2, file_size=ZIP_RATIO_MIN_BYTES)
    assert verdict_of(path) == "unsafe_content"


def test_the_bomb_signature_wins_over_a_mere_ratio(tmp_path: Path) -> None:
    path = docx(tmp_path / "b", [("a", b"x" * PACKED), ("b", b"y" * PACKED)], compression=STORED)
    patch_central(path, 2, file_size=200 * PACKED)
    patch_central(path, 3, file_size=2000 * PACKED)
    assert verdict_of(path) == "unsafe_content"


def test_a_member_over_its_cap_is_too_large(tmp_path: Path) -> None:
    packed = ZIP_MAX_MEMBER_BYTES // 100 + 1
    path = docx(tmp_path / "m", [("word/media/big", b"x" * packed)], compression=STORED)
    patch_central(path, 2, file_size=ZIP_MAX_MEMBER_BYTES)
    assert verdict_of(path) == "ok"
    patch_central(path, 2, file_size=ZIP_MAX_MEMBER_BYTES + 1)
    assert verdict_of(path) == "too_large"


def test_the_sum_of_all_members_is_capped(tmp_path: Path) -> None:
    packed = ZIP_MAX_MEMBER_BYTES // 100 + 1
    members = [(f"m{n}", b"x" * packed) for n in range(4)] + [("last", b"")]
    path = write_zip(tmp_path / "t", members, compression=STORED)
    for index in range(4):
        patch_central(path, index, file_size=ZIP_MAX_MEMBER_BYTES)
    assert verdict_of(path) == "ok"  # exactly 256 MiB
    patch_central(path, 4, file_size=1)
    assert verdict_of(path) == "too_large"


@pytest.mark.parametrize("name", ["../x", "/abs", "C:/x", "a\\..\\b", "word/../../etc"])
def test_a_name_that_climbs_out_is_unsafe(tmp_path: Path, name: str) -> None:
    path = docx(tmp_path / "t", [(name, b"x")])
    assert verdict_of(path) == "unsafe_content"


def test_a_name_with_nul_is_unsafe(tmp_path: Path) -> None:
    path = docx(tmp_path / "n", [("wordXnul.xml", b"x")])
    path.write_bytes(path.read_bytes().replace(b"wordXnul", b"word\x00nul"))
    assert verdict_of(path) == "unsafe_content"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("word/document.xml", "word/document.xml"),
        ("word/document.xml", "Word/Document.xml"),
        ("word/\u00e4.xml", "word/a\u0308.xml"),
        ("./word/a.xml", "word/a.xml"),
        ("word//a.xml", "word/a.xml"),
        ("word\\a.xml", "word/a.xml"),
    ],
)
def test_two_names_for_one_part_are_unsafe(tmp_path: Path, first: str, second: str) -> None:
    path = write_zip(tmp_path / "dup", [("[Content_Types].xml", b"<x/>"), (first, b"1"), (second, b"2")])
    if "\\" in first:  # zipfile turns backslashes into slashes on Windows; write the raw name back
        path.write_bytes(path.read_bytes().replace(b"word/a.xml", b"word\\a.xml", 2))
    assert verdict_of(path) == "unsafe_content"


def test_distinct_names_pass_as_positive_control(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "ok", [("word/a.xml", b"1"), ("word/b.xml", b"2"), ("word/\u00e4.xml", b"3")])
    assert verdict_of(path) == "ok"


def test_the_normalisation(tmp_path: Path) -> None:
    assert normalized_name("./Word//A.xml") == "word/a.xml"
    assert normalized_name("word\\a.xml") == "word/a.xml"
    assert normalized_name("a\u0308") == normalized_name("\u00e4")
    assert normalized_name("STRASSE") == normalized_name("stra\u00dfe")


def test_a_name_over_255_bytes_is_unsafe(tmp_path: Path) -> None:
    assert verdict_of(docx(tmp_path / "ok", [("n" * ZIP_MAX_NAME_BYTES, b"x")])) == "ok"
    assert verdict_of(docx(tmp_path / "long", [("n" * (ZIP_MAX_NAME_BYTES + 1), b"x")])) == "unsafe_content"
    # Bytes, not characters: 128 times a two byte letter is 256 bytes.
    assert verdict_of(docx(tmp_path / "wide", [("\u00e4" * 128, b"x")])) == "unsafe_content"


def test_data_in_front_of_the_archive_is_unsafe(tmp_path: Path) -> None:
    path = docx(tmp_path / "p")
    clean = path.read_bytes()
    path.write_bytes(b"junk" + clean)
    assert verdict_of(path) == "unsafe_content"
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 40 + clean)
    assert verdict_of(path) == "unsafe_content"


def test_hidden_data_before_the_first_member_is_unsafe(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "h", [("hidden", b"secret" * 10), ("a", b"1"), ("b", b"2")], compression=STORED)
    # The directory forgets the first member: its bytes stay in the file, in front of the others.
    data = path.read_bytes()
    central = data.find(b"PK\x01\x02")
    second = data.find(b"PK\x01\x02", central + 1)
    end = data.rfind(b"PK\x05\x06")
    record = bytearray(data[end:])
    record[8:12] = (2).to_bytes(2, "little") * 2
    record[12:16] = (end - second).to_bytes(4, "little")
    record[16:20] = central.to_bytes(4, "little")
    path.write_bytes(data[:central] + data[second:end] + bytes(record))
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == ["a", "b"]  # zipfile itself sees nothing wrong
    assert verdict_of(path) == "unsafe_content"


def test_two_entries_on_the_same_local_data_are_unsafe(tmp_path: Path) -> None:
    path = docx(tmp_path / "o", [("word/a.xml", b"1"), ("word/b.xml", b"2")])
    patch_central(path, 3, header_offset=header_offset_of(path, 2))
    assert verdict_of(path) == "unsafe_content"


def test_a_member_that_runs_into_the_next_is_unsafe(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "o", [("a", b"1" * 100), ("b", b"2")], compression=STORED)
    patch_central(path, 0, compress_size=150)
    assert verdict_of(path) == "unsafe_content"


def test_the_encryption_bit_is_encrypted_document(tmp_path: Path) -> None:
    path = docx(tmp_path / "e")
    patch_central(path, 1, flags=0x1)
    assert verdict_of(path) == "encrypted_document"


def test_an_encrypted_odt_is_encrypted_document(tmp_path: Path) -> None:
    manifest = (
        b'<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        b'<manifest:file-entry manifest:full-path="content.xml"><manifest:encryption-data/>'
        b"</manifest:file-entry></manifest:manifest>"
    )
    assert verdict_of(odt(tmp_path / "e", manifest)) == "encrypted_document"
    assert verdict_of(odt(tmp_path / "plain")) == "ok"


def test_a_truncated_zip_is_damaged(tmp_path: Path) -> None:
    path = docx(tmp_path / "c")
    path.write_bytes(path.read_bytes()[:-30])
    assert verdict_of(path) == "damaged"


def test_a_broken_local_header_is_damaged(tmp_path: Path) -> None:
    path = docx(tmp_path / "l")
    patch_central(path, 1, header_offset=header_offset_of(path, 1) + 1)
    assert verdict_of(path) == "damaged"


def test_the_head_of_a_member_is_read_under_its_cap(tmp_path: Path) -> None:
    path = odt(tmp_path / "o")
    assert read_member_head(path, "mimetype", 11) == b"application"
    with pytest.raises(Rejected, match="damaged"):
        read_member_head(path, "missing", 10)
