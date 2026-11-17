"""The sanitizer in front of LibreOffice, judged without its own functions.

Every check reads the cleaned copy with zipfile, plain byte search and
xml.etree from the standard library (project rule: the counter check never
uses the pattern of the implementation). Only sanitize and SanitizeReport are
imported from the module; an AST check below holds that.
"""

import ast
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from pii_redaction_backend.intake import xmlcheck, zipcheck
from pii_redaction_backend.intake.sanitize import SanitizeReport, sanitize
from pii_redaction_backend.intake.verdict import Rejected

Corpus = tuple[Path, dict[str, dict[str, object]]]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
XLINK = "{http://www.w3.org/1999/xlink}href"
MANIFEST = "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}"


def _clean(corpus: Corpus, name: str, tmp_path: Path) -> tuple[Path, SanitizeReport]:
    folder, manifest = corpus
    fmt = str(manifest[name]["expected_format"])
    out = tmp_path / f"clean.{fmt}"
    report = sanitize(folder / name, out, fmt)  # type: ignore[arg-type]
    return out, report


def _parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _all_bytes(path: Path) -> bytes:
    return b"\n".join(_parts(path).values())


def _passes_the_counter_check(path: Path) -> None:
    report = zipcheck.check_zip(path)
    xmlcheck.check_parts(path, report.names)


# -- the import rule --------------------------------------------------------------------


def test_the_test_uses_only_the_public_names_of_the_sanitizer() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "pii_redaction_backend.intake.sanitize"
        for alias in node.names
    }
    assert imported == {"sanitize", "SanitizeReport"}


# -- DOCX ---------------------------------------------------------------------------------


def test_docx_external_image_is_gone(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    assert b"127.0.0.1" in _all_bytes(folder / "ext_image.docx")  # positive control
    out, report = _clean(corpus, "ext_image.docx", tmp_path)
    everything = _all_bytes(out)
    assert b"127.0.0.1" not in everything
    assert b'TargetMode="External"' not in everything
    assert b"r:link" not in everything
    assert report.external_links_removed >= 1
    assert report.macros_removed is False
    _passes_the_counter_check(out)


def test_docx_attached_template_is_gone(corpus: Corpus, tmp_path: Path) -> None:
    out, report = _clean(corpus, "ext_template.docx", tmp_path)
    parts = _parts(out)
    assert b"attachedTemplate" not in parts.get("word/_rels/settings.xml.rels", b"")
    settings = ET.fromstring(parts["word/settings.xml"])  # noqa: S314
    assert settings.find(f"{W}attachedTemplate") is None
    assert b"127.0.0.1" not in _all_bytes(out)
    assert report.external_links_removed >= 1
    _passes_the_counter_check(out)


def test_docx_includepicture_field_keeps_its_cached_result(corpus: Corpus, tmp_path: Path) -> None:
    out, report = _clean(corpus, "ext_includepicture.docx", tmp_path)
    document = _parts(out)["word/document.xml"]
    assert b"INCLUDEPICTURE" not in document
    assert b"127.0.0.1" not in document
    texts = [node.text for node in ET.fromstring(document).iter(f"{W}t")]  # noqa: S314
    assert "Bild" in texts
    assert report.external_links_removed >= 1
    _passes_the_counter_check(out)


def test_docx_alt_chunk_is_gone(corpus: Corpus, tmp_path: Path) -> None:
    out, _ = _clean(corpus, "ext_altchunk.docx", tmp_path)
    parts = _parts(out)
    assert ET.fromstring(parts["word/document.xml"]).find(f".//{W}altChunk") is None  # noqa: S314
    assert b"aFChunk" not in _all_bytes(out)
    assert b"127.0.0.1" not in _all_bytes(out)
    _passes_the_counter_check(out)


def test_docx_macros_are_gone(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    assert b"macroEnabled" in _parts(folder / "macro_vba.docx")["[Content_Types].xml"]  # positive control
    out, report = _clean(corpus, "macro_vba.docx", tmp_path)
    parts = _parts(out)
    assert not [name for name in parts if name.lower().endswith("vbaproject.bin")]
    assert b"macroEnabled" not in parts["[Content_Types].xml"]
    assert b"vbaProject" not in _all_bytes(out)
    assert b"wordprocessingml.document.main+xml" in parts["[Content_Types].xml"]
    assert report.macros_removed is True
    _passes_the_counter_check(out)


def _docx_with(members: dict[str, str], tmp_path: Path, name: str = "in.docx") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, text in members.items():
            archive.writestr(member, text)
    return path


CT = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)
NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)


def _document(body: str) -> str:
    return f'<?xml version="1.0"?><w:document {NS}><w:body>{body}</w:body></w:document>'


@pytest.mark.parametrize("keyword", ["INCLUDETEXT", "LINK", "DDE", "DDEAUTO", "IMPORT", "INCLUDEPICTURE"])
def test_a_complex_field_that_loads_keeps_only_its_result(tmp_path: Path, keyword: str) -> None:
    body = (
        "<w:p>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> {keyword} "http://127.0.0.1:9/x" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>Ergebnis</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "<w:r><w:t>danach</w:t></w:r>"
        "</w:p>"
    )
    src = _docx_with({"[Content_Types].xml": CT, "word/document.xml": _document(body)}, tmp_path)
    out = tmp_path / "out.docx"
    report = sanitize(src, out, "docx")
    document = _parts(out)["word/document.xml"]
    assert keyword.encode() not in document
    assert b"127.0.0.1" not in document
    assert b"fldChar" not in document
    texts = [node.text for node in ET.fromstring(document).iter(f"{W}t")]  # noqa: S314
    assert texts == ["Ergebnis", "danach"]
    assert report.external_links_removed == 1


def test_positive_control_a_harmless_field_stays(tmp_path: Path) -> None:
    body = (
        "<w:p>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>1</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p>"
    )
    src = _docx_with({"[Content_Types].xml": CT, "word/document.xml": _document(body)}, tmp_path)
    out = tmp_path / "out.docx"
    report = sanitize(src, out, "docx")
    document = _parts(out)["word/document.xml"]
    assert b"PAGE" in document
    assert document.count(b"<w:fldChar ") == 3
    assert report.external_links_removed == 0


def test_activex_embeddings_and_customizations_are_gone(tmp_path: Path) -> None:
    rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/control" '
        'Target="activeX/activeX1.xml"/>'
        '<Relationship Id="r2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" '
        'Target="embeddings/oleObject1.bin"/>'
        '<Relationship Id="r3" Type="http://schemas.microsoft.com/office/2006/relationships/keyMapCustomizations" '
        'Target="customizations.xml"/>'
        "</Relationships>"
    )
    src = _docx_with(
        {
            "[Content_Types].xml": CT,
            "word/document.xml": _document("<w:p/>"),
            "word/_rels/document.xml.rels": rels,
            "word/activeX/activeX1.xml": "<ax/>",
            "word/embeddings/oleObject1.bin": "OLE",
            "word/customizations.xml": "<c/>",
            "word/vbaData.xml": "<v/>",
        },
        tmp_path,
    )
    out = tmp_path / "out.docx"
    report = sanitize(src, out, "docx")
    names = set(_parts(out))
    assert names == {"[Content_Types].xml", "word/document.xml", "word/_rels/document.xml.rels"}
    assert b"Relationship " not in _parts(out)["word/_rels/document.xml.rels"]
    assert report.macros_removed is True


def test_an_external_hyperlink_keeps_its_id_with_an_empty_target(tmp_path: Path) -> None:
    rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rH" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="http://127.0.0.1:9/page" TargetMode="External"/></Relationships>'
    )
    body = '<w:p><w:hyperlink r:id="rH"><w:r><w:t>Link</w:t></w:r></w:hyperlink></w:p>'
    src = _docx_with(
        {"[Content_Types].xml": CT, "word/document.xml": _document(body), "word/_rels/document.xml.rels": rels},
        tmp_path,
    )
    out = tmp_path / "out.docx"
    sanitize(src, out, "docx")
    relationship = ET.fromstring(_parts(out)["word/_rels/document.xml.rels"])[0]  # noqa: S314
    assert relationship.get("Id") == "rH"
    assert relationship.get("Target") == ""
    assert relationship.get("TargetMode") is None
    assert b"127.0.0.1" not in _all_bytes(out)


def test_web_settings_frameset_is_gone(tmp_path: Path) -> None:
    web = (
        f'<?xml version="1.0"?><w:webSettings {NS}><w:frameset><w:frame>'
        '<w:sourceFileName r:id="rF"/></w:frame></w:frameset></w:webSettings>'
    )
    src = _docx_with(
        {"[Content_Types].xml": CT, "word/document.xml": _document("<w:p/>"), "word/webSettings.xml": web},
        tmp_path,
    )
    out = tmp_path / "out.docx"
    sanitize(src, out, "docx")
    assert b"frameset" not in _parts(out)["word/webSettings.xml"]


def test_harmless_docx_comes_out_the_same(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    out, report = _clean(corpus, "harmless.docx", tmp_path)
    before, after = _parts(folder / "harmless.docx"), _parts(out)
    assert list(before) == list(after)
    assert ET.canonicalize(before["word/document.xml"]) == ET.canonicalize(after["word/document.xml"])
    assert report == SanitizeReport(macros_removed=False, external_links_removed=0)
    _passes_the_counter_check(out)


# -- ODT ------------------------------------------------------------------------------------


def test_odt_external_image_is_gone(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    assert b"127.0.0.1" in _all_bytes(folder / "odt_ext_image.odt")  # positive control
    out, report = _clean(corpus, "odt_ext_image.odt", tmp_path)
    content = ET.fromstring(_parts(out)["content.xml"])  # noqa: S314
    external = [node.get(XLINK) for node in content.iter() if re.match(r"^[a-z][a-z0-9+.-]*:", node.get(XLINK) or "")]
    assert external == []
    assert b"127.0.0.1" not in _all_bytes(out)
    assert report.external_links_removed >= 1
    _passes_the_counter_check(out)


def test_odt_basic_and_event_listeners_are_gone(corpus: Corpus, tmp_path: Path) -> None:
    out, report = _clean(corpus, "odt_basic.odt", tmp_path)
    parts = _parts(out)
    assert not [name for name in parts if name.startswith(("Basic/", "Scripts/"))]
    content = ET.fromstring(parts["content.xml"])  # noqa: S314
    assert content.find(f".//{OFFICE}event-listeners") is None
    assert content.find(f".//{OFFICE}scripts") is None
    manifest = ET.fromstring(parts["META-INF/manifest.xml"])  # noqa: S314
    paths = [entry.get(f"{MANIFEST}full-path") or "" for entry in manifest.iter(f"{MANIFEST}file-entry")]
    assert not [path for path in paths if path.startswith(("Basic", "Scripts"))]
    assert report.macros_removed is True
    _passes_the_counter_check(out)


def test_odt_mimetype_is_first_and_stored(corpus: Corpus, tmp_path: Path) -> None:
    out, _ = _clean(corpus, "odt_basic.odt", tmp_path)
    with zipfile.ZipFile(out) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
    assert out.read_bytes()[30:38] == b"mimetype"


def _odt_with(content_body: str, tmp_path: Path) -> Path:
    ns = (
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
        'xmlns:xlink="http://www.w3.org/1999/xlink"'
    )
    content = (
        f'<?xml version="1.0"?><office:document-content {ns}><office:body><office:text>'
        f"{content_body}</office:text></office:body></office:document-content>"
    )
    path = tmp_path / "in.odt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text", zipfile.ZIP_STORED)
        archive.writestr("content.xml", content, zipfile.ZIP_DEFLATED)
    return path


@pytest.mark.parametrize(
    "body",
    [
        '<text:section text:name="S"><text:section-source xlink:href="http://127.0.0.1:9/s.odt"/></text:section>',
        '<table:table table:name="T"><table:table-source xlink:href="file:///etc/passwd"/></table:table>',
        '<text:p><draw:frame><draw:object xlink:href="http://127.0.0.1:9/obj"/></draw:frame></text:p>',
        '<text:p><draw:frame><draw:object-ole xlink:href="smb://127.0.0.1/x"/></draw:frame></text:p>',
        (
            '<text:dde-connection-decls><text:dde-connection-decl office:name="d" office:dde-application="x" '
            'office:dde-topic="file:///etc/passwd" office:dde-item="a"/></text:dde-connection-decls>'
        ),
    ],
    ids=["section_source", "table_source", "object", "object_ole", "dde"],
)
def test_odt_external_sources_are_gone(tmp_path: Path, body: str) -> None:
    out = tmp_path / "out.odt"
    report = sanitize(_odt_with(body, tmp_path), out, "odt")
    content = _parts(out)["content.xml"]
    assert b"127.0.0.1" not in content
    assert b"/etc/passwd" not in content
    assert report.external_links_removed >= 1


def test_positive_control_an_internal_odt_image_stays(tmp_path: Path) -> None:
    body = '<text:p><draw:frame><draw:image xlink:href="Pictures/a.png"/></draw:frame></text:p>'
    out = tmp_path / "out.odt"
    report = sanitize(_odt_with(body, tmp_path), out, "odt")
    assert b"Pictures/a.png" in _parts(out)["content.xml"]
    assert report.external_links_removed == 0


def test_harmless_odt_comes_out_the_same(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    out, report = _clean(corpus, "harmless.odt", tmp_path)
    before, after = _parts(folder / "harmless.odt"), _parts(out)
    assert list(before) == list(after)
    assert ET.canonicalize(before["content.xml"]) == ET.canonicalize(after["content.xml"])
    assert report == SanitizeReport(macros_removed=False, external_links_removed=0)
    _passes_the_counter_check(out)


# -- limits and failure ---------------------------------------------------------------------


def test_an_output_over_the_growth_allowance_is_too_large(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = corpus
    source = folder / "harmless.docx"
    out = tmp_path / "out.docx"
    # Positive control: with the real allowance (10 %) the copy passes.
    sanitize(source, out, "docx")
    assert out.stat().st_size <= source.stat().st_size * 11 // 10
    # An allowance below zero makes every copy too large.
    monkeypatch.setattr("pii_redaction_backend.intake.sanitize.GROWTH_PERCENT", -90)
    out.unlink()
    with pytest.raises(Rejected, match="too_large"):
        sanitize(source, out, "docx")
    assert not out.exists()


def test_a_broken_source_is_damaged_and_leaves_no_output(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    src.write_bytes(b"PK\x03\x04 not really a zip")
    out = tmp_path / "out.docx"
    with pytest.raises(Rejected, match="damaged"):
        sanitize(src, out, "docx")
    assert not out.exists()


@pytest.mark.parametrize("name", ["ext_image.docx", "ext_template.docx", "macro_vba.docx", "odt_ext_image.odt"])
def test_every_sanitize_case_of_the_corpus_passes_the_counter_check(corpus: Corpus, tmp_path: Path, name: str) -> None:
    _folder, manifest = corpus
    assert manifest[name]["sanitize"] is True
    out, _ = _clean(corpus, name, tmp_path)
    _passes_the_counter_check(out)
