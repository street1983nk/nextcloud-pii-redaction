"""Self-test of the attack corpus (ci/make_corpus.py), with means independent of the pre-check.

Never with the pattern of the implementation: no import of
pii_redaction_backend.intake and no pikepdf here (checked below on the
syntax tree). ZIP files are judged with zipfile metadata and raw bytes, PDFs
with PyMuPDF and byte patterns. No bomb is unpacked; only declarations are read.
"""

import ast
import json
import re
import struct
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from types import ModuleType

import pymupdf
import pytest

from tests.conftest import REPO_ROOT

CI_SCRIPT = REPO_ROOT / "ci" / "make_corpus.py"
WORDS = {
    "ok",
    "confirm",
    "encrypted_pdf",
    "encrypted_document",
    "wrong_type",
    "damaged",
    "too_large",
    "too_many_pages",
    "unsafe_content",
    "unsupported_format",
}


def central_entries(data: bytes) -> list[tuple[str, int, int, int, bytes]]:
    """Raw central directory: (name, file size, compressed size, local offset, raw name bytes)."""
    entries = []
    at = data.find(b"PK\x01\x02")
    while at >= 0:
        compressed, size = struct.unpack_from("<II", data, at + 20)
        name_len = struct.unpack_from("<H", data, at + 28)[0]
        offset = struct.unpack_from("<I", data, at + 42)[0]
        raw = data[at + 46 : at + 46 + name_len]
        entries.append((raw.decode("utf-8", errors="replace"), size, compressed, offset, raw))
        at = data.find(b"PK\x01\x02", at + 1)
    return entries


def raw_names(path: Path) -> list[bytes]:
    return [entry[4] for entry in central_entries(path.read_bytes())]


def end_record_count(data: bytes) -> int:
    end = data.rfind(b"PK\x05\x06")
    return struct.unpack_from("<H", data, end + 10)[0]


def test_the_manifest_names_a_known_word_for_every_file(corpus: tuple[Path, dict]) -> None:
    folder, manifest = corpus
    assert len(manifest) >= 45
    for name, entry in manifest.items():
        assert (folder / name).is_file(), name
        assert entry["expect"], name
        assert set(entry["expect"]) <= WORDS, name
        assert entry["expected_format"] in {"pdf", "docx", "odt"}, name
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_no_corpus_file_is_checked_in() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.docx", "*.odt", "*.pdf", "*.zip"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tracked == []


def test_the_self_test_does_not_use_the_implementation() -> None:
    imported = set()
    for path in (Path(__file__), CI_SCRIPT):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not any(name.startswith(("pikepdf", "pii_redaction_backend")) for name in imported)


# -- ZIP structure -------------------------------------------------------------------


def test_the_ratio_bomb_is_over_one_thousand(corpus: tuple[Path, dict]) -> None:
    with zipfile.ZipFile(corpus[0] / "zip_ratio_bomb.docx") as archive:
        bomb = archive.getinfo("word/media/zeros.bin")
    assert bomb.file_size >= 32 * 1024 * 1024
    assert bomb.file_size / bomb.compress_size > 1000


def test_the_lying_size_declares_less_than_it_holds(corpus: tuple[Path, dict]) -> None:
    data = (corpus[0] / "zip_lying_size.docx").read_bytes()
    entry = next(entry for entry in central_entries(data) if entry[0] == "word/document.xml")
    assert entry[1] == 1000
    assert entry[2] > 1000  # the compressed stream alone is larger than the declared content


def test_the_overlap_shares_one_local_header(corpus: tuple[Path, dict]) -> None:
    offsets = [entry[3] for entry in central_entries((corpus[0] / "zip_overlap.docx").read_bytes())]
    assert len(offsets) != len(set(offsets))


@pytest.mark.parametrize(("name", "count"), [("zip_entries_10001.docx", 10_001), ("zip_entries_10000.docx", 10_000)])
def test_the_entry_floods_have_their_count(corpus: tuple[Path, dict], name: str, count: int) -> None:
    data = (corpus[0] / name).read_bytes()
    assert end_record_count(data) == count
    assert len(central_entries(data)) == count


@pytest.mark.parametrize(
    ("name", "raw"),
    [
        ("traversal_dotdot.docx", b"../evil.xml"),
        ("traversal_abs.docx", b"/abs.xml"),
        ("traversal_drive.docx", b"C:/drive.xml"),
        ("traversal_backslash.docx", b"word\\..\\..\\evil.xml"),
        ("traversal_nul.docx", b"word\x00nul.xml"),
    ],
)
def test_the_traversal_names_are_raw_in_the_directory(corpus: tuple[Path, dict], name: str, raw: bytes) -> None:
    assert raw in raw_names(corpus[0] / name)


def test_the_duplicates_collide_the_way_their_name_says(corpus: tuple[Path, dict]) -> None:
    folder = corpus[0]
    exact = raw_names(folder / "dup_exact.docx")
    assert exact.count(b"word/document.xml") == 2
    case = [name.decode() for name in raw_names(folder / "dup_case.docx")]
    assert "word/document.xml" in case
    assert "Word/Document.xml" in case
    nfc = [
        name.decode() for name in raw_names(folder / "dup_nfc.docx") if name.startswith(b"word/") and b".xml" in name
    ]
    pair = [name for name in nfc if name not in ("word/document.xml",)]
    assert len(pair) == 2
    assert pair[0] != pair[1]
    assert unicodedata.normalize("NFC", pair[0]) == unicodedata.normalize("NFC", pair[1])
    dot = raw_names(folder / "dup_dot.docx")
    assert b"./word/a.xml" in dot
    assert b"word/a.xml" in dot


def test_the_prefix_case_hides_a_member_before_the_listed_ones(corpus: tuple[Path, dict]) -> None:
    data = (corpus[0] / "zip_prefix.docx").read_bytes()
    assert data.startswith(b"PK\x03\x04")
    offsets = [entry[3] for entry in central_entries(data)]
    assert min(offsets) > 0
    assert b"hidden.bin" in data[: min(offsets)]


# -- XML and external references ---------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["xml_billion_laughs.docx", "xml_xxe_file.docx", "xml_xxe_http.docx", "xml_param_entity.docx"]
)
def test_the_xml_attacks_carry_a_doctype_with_entities(corpus: tuple[Path, dict], name: str) -> None:
    with zipfile.ZipFile(corpus[0] / name) as archive:
        document = archive.read("word/document.xml")
    assert b"<!DOCTYPE" in document
    assert b"<!ENTITY" in document


def test_the_doctype_only_case_has_no_entity(corpus: tuple[Path, dict]) -> None:
    with zipfile.ZipFile(corpus[0] / "xml_doctype_only.docx") as archive:
        document = archive.read("word/document.xml")
    assert b"<!DOCTYPE" in document
    assert b"<!ENTITY" not in document


def test_the_external_cases_point_at_the_canary(tmp_path: Path) -> None:
    module = load_corpus_module()
    module.build(tmp_path, 41234)
    canary = b"http://127.0.0.1:41234"
    with zipfile.ZipFile(tmp_path / "ext_image.docx") as archive:
        rels = archive.read("word/_rels/document.xml.rels")
    assert b'TargetMode="External"' in rels
    assert canary in rels
    with zipfile.ZipFile(tmp_path / "ext_template.docx") as archive:
        assert canary in archive.read("word/_rels/settings.xml.rels")
    with zipfile.ZipFile(tmp_path / "ext_includepicture.docx") as archive:
        assert b"INCLUDEPICTURE" in archive.read("word/document.xml")
    with zipfile.ZipFile(tmp_path / "odt_ext_image.odt") as archive:
        assert canary in archive.read("content.xml")


def test_the_macro_cases_carry_their_macros(corpus: tuple[Path, dict]) -> None:
    with zipfile.ZipFile(corpus[0] / "macro_vba.docx") as archive:
        assert "word/vbaProject.bin" in archive.namelist()
        assert b"macroEnabled" in archive.read("[Content_Types].xml")
    with zipfile.ZipFile(corpus[0] / "odt_basic.odt") as archive:
        assert "Basic/Standard/Module1.xml" in archive.namelist()
        assert b"office:event-listeners" in archive.read("content.xml")
    assert all(corpus[1][name]["sanitize"] for name in ("macro_vba.docx", "odt_basic.odt", "ext_image.docx"))


def test_the_encrypted_office_files(corpus: tuple[Path, dict]) -> None:
    with zipfile.ZipFile(corpus[0] / "odt_encrypted.odt") as archive:
        assert b"encryption-data" in archive.read("META-INF/manifest.xml")
    cfb = (corpus[0] / "cfb_encrypted.docx").read_bytes()
    assert cfb.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
    assert "EncryptedPackage".encode("utf-16-le") in cfb


@pytest.mark.parametrize("name", ["harmless.docx", "harmless.odt"])
def test_the_office_controls_are_valid(corpus: tuple[Path, dict], name: str) -> None:
    with zipfile.ZipFile(corpus[0] / name) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        if name.endswith(".odt"):
            assert names[0] == "mimetype"
            assert archive.read("mimetype") == b"application/vnd.oasis.opendocument.text"
            assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        else:
            assert "[Content_Types].xml" in names
            assert b"wordprocessingml.document.main" in archive.read("[Content_Types].xml")


# -- PDF ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "pages"), [("pdf_301_pages.pdf", 301), ("pdf_300_pages.pdf", 300), ("harmless.pdf", 1)]
)
def test_pymupdf_counts_the_pages(corpus: tuple[Path, dict], name: str, pages: int) -> None:
    with pymupdf.open(corpus[0] / name) as document:
        assert document.page_count == pages


def test_the_harmless_pdf_has_its_text(corpus: tuple[Path, dict]) -> None:
    with pymupdf.open(corpus[0] / "harmless.pdf") as document:
        assert "Harmloser Inhalt" in document[0].get_text()


def test_the_user_password_pdf_needs_a_password(corpus: tuple[Path, dict]) -> None:
    with pymupdf.open(corpus[0] / "pdf_user_password.pdf") as document:
        assert document.needs_pass
        assert document.authenticate("geheim")
        assert "Harmloser Inhalt" in document[0].get_text()  # the RC4 key is right


def test_the_owner_only_pdf_opens_without_a_password(corpus: tuple[Path, dict]) -> None:
    with pymupdf.open(corpus[0] / "pdf_owner_only.pdf") as document:
        assert not document.needs_pass
        assert document.metadata is not None
        assert "RC4" in (document.metadata.get("encryption") or "")  # still encrypted, opened with the empty password
        assert "Harmloser Inhalt" in document[0].get_text()
    assert corpus[1]["pdf_owner_only.pdf"]["owner_protected"] is True


def test_the_signed_pdf_has_a_signature_field(corpus: tuple[Path, dict]) -> None:
    data = (corpus[0] / "pdf_signed.pdf").read_bytes()
    assert b"/SigFlags 3" in data
    assert b"/ByteRange" in data
    assert b"/FT /Sig" in data


def test_the_huge_cases_declare_their_size(corpus: tuple[Path, dict]) -> None:
    image = (corpus[0] / "pdf_huge_image.pdf").read_bytes()
    assert b"/Width 100000" in image
    assert b"/Height 100000" in image
    assert len(image) < 4096
    assert b"[0 0 20000 20000]" in (corpus[0] / "pdf_huge_mediabox.pdf").read_bytes()
    bomb = (corpus[0] / "pdf_flate_bomb.pdf").read_bytes()
    assert b"/FlateDecode" in bomb
    assert len(bomb) < 1024 * 1024


def test_the_object_flood_has_500001_objects(corpus: tuple[Path, dict]) -> None:
    data = (corpus[0] / "pdf_objects_500001.pdf").read_bytes()
    assert len(re.findall(rb"(?m)^\d+ 0 obj$", data)) == 500_001


def test_the_page_loop_names_its_own_pages_node(corpus: tuple[Path, dict]) -> None:
    assert b"2 0 obj\n<< /Type /Pages /Kids [2 0 R" in (corpus[0] / "pdf_page_loop.pdf").read_bytes()


def test_the_broken_and_wrong_files(corpus: tuple[Path, dict]) -> None:
    folder, manifest = corpus
    assert (folder / "pdf_prefix.pdf").read_bytes().startswith(b"JUNK\n%PDF-")
    assert (folder / "wrong_pdf_as_docx.docx").read_bytes().startswith(b"%PDF-")
    assert (folder / "wrong_docx_as_pdf.pdf").read_bytes().startswith(b"PK\x03\x04")
    assert manifest["wrong_docx_as_pdf.pdf"]["expected_format"] == "pdf"
    assert b"opendocument" in (folder / "wrong_odt_as_docx.docx").read_bytes()
    with pytest.raises(zipfile.BadZipFile):
        zipfile.ZipFile(folder / "truncated.docx")
    assert len((folder / "truncated.pdf").read_bytes()) == 40


# -- the command line ------------------------------------------------------------------


def load_corpus_module() -> ModuleType:
    import importlib.util

    spec = importlib.util.spec_from_file_location("ci_make_corpus_selftest", CI_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_e2e_mode_writes_exactly_seven_files(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-I", str(CI_SCRIPT), str(tmp_path), "--e2e", "--canary-port", "8099"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    made = sorted(path.name for path in tmp_path.iterdir() if path.name != "manifest.json")
    assert made == sorted(
        [
            "wrong_pdf_as_docx.docx",
            "pdf_301_pages.pdf",
            "pdf_user_password.pdf",
            "pdf_signed.pdf",
            "harmless.pdf",
            "ext_image.docx",
            "cfb_encrypted.docx",
        ]
    )


@pytest.mark.parametrize("args", [[], ["a", "b"], ["out", "--canary-port"], ["out", "--canary-port", "70000"]])
def test_a_wrong_call_is_refused(args: list[str], tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-I", str(CI_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr
