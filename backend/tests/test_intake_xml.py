"""Stage C of the pre-check: one XML parser, no DOCTYPE, no entity, no network, parts under the cap.

The negative cases each have a positive control: the same document read by a
parser that resolves entities does show the canary, and a listening socket
that a resolving parser would reach is reached by nobody here.
"""

import io
import socket
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from lxml import etree  # pyright: ignore[reportAttributeAccessIssue] - compiled module, no stubs pinned

from pii_redaction_backend.intake import limits, xmlcheck
from pii_redaction_backend.intake.verdict import Rejected
from tests.conftest import BACKEND_ROOT

SOURCE_ROOT = BACKEND_ROOT / "src"
CANARY = "kanarienwert-4711-xxe"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _verdict(data: bytes) -> str:
    try:
        xmlcheck.parse_part(data)
    except Rejected as rejected:
        return rejected.verdict
    return "ok"


@pytest.fixture
def connects() -> Iterator[list[str]]:
    """Count socket.connect and getaddrinfo audit events while the test runs."""
    seen: list[str] = []
    active = [True]

    def hook(event: str, _args: tuple[object, ...]) -> None:
        if active[0] and event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname"}:
            seen.append(event)

    sys.addaudithook(hook)
    yield seen
    active[0] = False


@pytest.fixture
def listener() -> Iterator[socket.socket]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(4)
    server.setblocking(False)
    yield server
    server.close()


def _accepted(server: socket.socket) -> bool:
    try:
        connection, _ = server.accept()
    except BlockingIOError:
        return False
    connection.close()
    return True


# -- the factory -----------------------------------------------------------------------


def test_the_parser_has_exactly_the_six_options() -> None:
    source = (SOURCE_ROOT / "pii_redaction_backend" / "intake" / "xmlcheck.py").read_text(encoding="utf-8")
    for option in (
        "resolve_entities=False",
        "no_network=True",
        "huge_tree=False",
        "load_dtd=False",
        "dtd_validation=False",
        "remove_blank_text=False",
    ):
        assert source.count(option) == 1, option


def test_xmlparser_is_built_only_in_xmlcheck() -> None:
    offenders = [
        path.relative_to(SOURCE_ROOT)
        for path in SOURCE_ROOT.rglob("*.py")
        if "XMLParser(" in path.read_text(encoding="utf-8") and path.name != "xmlcheck.py"
    ]
    assert offenders == []


# -- single parts -----------------------------------------------------------------------


def test_a_plain_part_is_accepted() -> None:
    root = xmlcheck.parse_part(b"<a><b>text</b></a>")
    assert root.tag == "a"


@pytest.mark.parametrize(
    "document",
    [
        b'<?xml version="1.0"?><!DOCTYPE a><a/>',
        b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>',
        b'<!DOCTYPE a [<!ENTITY a0 "lol"><!ENTITY a1 "&a0;&a0;&a0;&a0;&a0;&a0;&a0;&a0;&a0;&a0;">]><a>&a1;</a>',
        b'<!DOCTYPE a SYSTEM "http://127.0.0.1:9/x.dtd"><a/>',
        b'<!DOCTYPE a [<!ENTITY % p SYSTEM "http://127.0.0.1:9/p.dtd"> %p;]><a/>',
    ],
    ids=["doctype_only", "internal_entity", "laughs", "external_dtd", "parameter_entity"],
)
def test_every_doctype_is_unsafe_content(document: bytes, connects: list[str]) -> None:
    assert _verdict(document) == "unsafe_content"
    assert connects == []


def test_an_xxe_file_entity_never_reaches_the_result(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text(CANARY, encoding="utf-8")
    document = f'<!DOCTYPE a [<!ENTITY x SYSTEM "{secret.as_uri()}">]><a>&x;</a>'.encode()

    with pytest.raises(Rejected) as rejected:
        xmlcheck.parse_part(document)
    assert rejected.value.verdict == "unsafe_content"
    assert CANARY not in str(rejected.value)
    # Even before the rejection, the parser itself did not read the file.
    tree = etree.fromstring(document, xmlcheck.make_parser())
    assert CANARY not in etree.tostring(tree).decode()

    # Positive control: a resolving parser does read it, so the test can see a leak.
    leaky = etree.XMLParser(resolve_entities=True, load_dtd=True, no_network=True)
    assert CANARY in etree.tostring(etree.fromstring(document, leaky)).decode()


def test_an_xxe_network_entity_reaches_no_server(listener: socket.socket, connects: list[str]) -> None:
    port = listener.getsockname()[1]
    documents = [
        f'<!DOCTYPE a [<!ENTITY x SYSTEM "http://127.0.0.1:{port}/x">]><a>&x;</a>'.encode(),
        f'<!DOCTYPE a [<!ENTITY % p SYSTEM "http://127.0.0.1:{port}/p.dtd"> %p;]><a/>'.encode(),
        f'<!DOCTYPE a SYSTEM "http://127.0.0.1:{port}/a.dtd"><a/>'.encode(),
    ]
    for document in documents:
        assert _verdict(document) == "unsafe_content"
    assert not _accepted(listener)
    assert connects == []


def test_positive_control_the_listener_sees_a_real_connection(listener: socket.socket) -> None:
    probe = socket.create_connection(listener.getsockname(), timeout=2)
    try:
        listener.setblocking(True)
        listener.settimeout(2)
        assert _accepted(listener)
    finally:
        probe.close()


def test_a_utf16_part_with_a_doctype_is_unsafe() -> None:
    document = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE a><a/>'.encode("utf-16")
    assert b"DOCTYPE" not in document  # a byte search alone would miss it
    assert _verdict(document) == "unsafe_content"


def test_broken_xml_is_damaged() -> None:
    assert _verdict(b"<a><b></a>") == "damaged"


# -- parts inside a package -------------------------------------------------------------


def _package(tmp_path: Path, members: dict[str, bytes], name: str = "p.docx") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return path


def test_check_parts_reads_only_xml_and_rels(tmp_path: Path) -> None:
    path = _package(
        tmp_path,
        {"word/document.xml": b"<a/>", "word/_rels/document.xml.rels": b"<r/>", "word/media/x.png": b"<!DOCTYPE"},
    )
    xmlcheck.check_parts(path, ("word/document.xml", "word/_rels/document.xml.rels", "word/media/x.png"))


def test_a_rels_part_with_a_doctype_is_unsafe(tmp_path: Path) -> None:
    path = _package(tmp_path, {"_rels/.rels": b"<!DOCTYPE r><r/>"})
    with pytest.raises(Rejected, match="unsafe_content"):
        xmlcheck.check_parts(path, ("_rels/.rels",))


def test_a_part_over_the_cap_is_too_large_while_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xmlcheck, "XML_MAX_PART_BYTES", 1000)
    body = b"<a>" + b" " * 2000 + b"</a>"
    path = _package(tmp_path, {"word/document.xml": body})
    with pytest.raises(Rejected, match="too_large"):
        xmlcheck.check_parts(path, ("word/document.xml",))
    # Positive control: the same part under a larger cap passes.
    monkeypatch.setattr(xmlcheck, "XML_MAX_PART_BYTES", 4000)
    xmlcheck.check_parts(path, ("word/document.xml",))


def test_the_cap_is_the_owner_limit() -> None:
    assert xmlcheck.XML_MAX_PART_BYTES == limits.XML_MAX_PART_BYTES


def test_an_odf_manifest_with_encryption_data_is_encrypted(tmp_path: Path) -> None:
    manifest = (
        b'<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        b'<manifest:file-entry manifest:full-path="content.xml">'
        b"<manifest:encryption-data/></manifest:file-entry></manifest:manifest>"
    )
    path = _package(tmp_path, {"META-INF/manifest.xml": manifest}, "p.odt")
    with pytest.raises(Rejected, match="encrypted_document"):
        xmlcheck.check_parts(path, ("META-INF/manifest.xml",))
    plain = manifest.replace(b"<manifest:encryption-data/>", b"")
    xmlcheck.check_parts(_package(tmp_path, {"META-INF/manifest.xml": plain}, "q.odt"), ("META-INF/manifest.xml",))


# -- the corpus --------------------------------------------------------------------------


def _names(path: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(path) as archive:
        return tuple(archive.namelist())


def _corpus_verdict(path: Path) -> str:
    try:
        xmlcheck.check_parts(path, _names(path))
    except Rejected as rejected:
        return rejected.verdict
    return "ok"


def test_every_xml_case_of_the_corpus_is_unsafe(corpus: tuple[Path, dict[str, dict[str, object]]]) -> None:
    folder, manifest = corpus
    cases = sorted(name for name in manifest if name.startswith("xml_"))
    assert len(cases) >= 5
    for name in cases:
        assert _corpus_verdict(folder / name) == "unsafe_content", name


@pytest.mark.parametrize(("name", "verdict"), [("harmless.docx", "ok"), ("harmless.odt", "ok")])
def test_the_harmless_packages_pass(corpus: tuple[Path, dict[str, dict[str, object]]], name: str, verdict: str) -> None:
    folder, _ = corpus
    assert _corpus_verdict(folder / name) == verdict


def test_the_encrypted_odt_of_the_corpus(corpus: tuple[Path, dict[str, dict[str, object]]]) -> None:
    folder, _ = corpus
    assert _corpus_verdict(folder / "odt_encrypted.odt") == "encrypted_document"


def test_the_lying_size_member_is_refused(corpus: tuple[Path, dict[str, dict[str, object]]]) -> None:
    folder, manifest = corpus
    verdict = _corpus_verdict(folder / "zip_lying_size.docx")
    assert verdict in manifest["zip_lying_size.docx"]["expect"]  # type: ignore[operator]


def test_a_member_whose_data_is_longer_than_declared_is_refused(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("word/document.xml", b"<a>" + b" " * 100 + b"</a>")
    data = bytearray(buffer.getvalue())
    # Declare 10 bytes in both headers: CPython stops at 10 and the CRC no longer matches.
    data[22:26] = (10).to_bytes(4, "little")
    central = data.rfind(b"PK\x01\x02")
    data[central + 24 : central + 28] = (10).to_bytes(4, "little")
    path = tmp_path / "lie.docx"
    path.write_bytes(bytes(data))
    assert _corpus_verdict(path) in {"damaged", "too_large"}
