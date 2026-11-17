"""Stage C of the pre-check: every XML part of a DOCX or ODT through the one parser.

There is exactly one place that builds an lxml parser, make_parser (CLAUDE.md:
"Parser fest konfigurieren"; defusedxml.lxml is deprecated and not used). It
resolves no entity, loads no DTD, never touches the network and keeps the
libxml2 size limits (no huge trees). On top of that any DOCTYPE or internal
DTD is refused as unsafe_content: a Word or ODF part never needs one, and a
document that brings one is an attack (XXE, Billion Laughs). libxml2 itself
stops some of these with a syntax error (entity amplification); such a part
is still named unsafe_content, not damaged, when its text carries a DOCTYPE
or an entity declaration.

Every .xml and .rels member is read in blocks with a counter, so a member that
is longer than its declaration is caught while reading (XML_MAX_PART_BYTES),
not after the whole part is in memory. The caller has run zipcheck.check_zip
first. Nothing is logged; the answer is a word of the closed list.
"""

import zipfile
from pathlib import Path
from typing import Any, Final

from lxml import etree  # pyright: ignore[reportAttributeAccessIssue] - compiled module, no stubs pinned

from pii_redaction_backend.intake.limits import XML_MAX_PART_BYTES
from pii_redaction_backend.intake.verdict import Rejected

READ_BLOCK: Final = 64 * 1024
XML_SUFFIXES: Final = (".xml", ".rels")
MANIFEST: Final = "META-INF/manifest.xml"
_ENCRYPTION_DATA: Final = "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}encryption-data"
_DECLARATIONS: Final = ("<!DOCTYPE", "<!ENTITY")
_BOMS: Final = (
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xff\xfe", "utf-16-le"),
)
_UNREADABLE: Final = (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError, ValueError, NotImplementedError)


def make_parser() -> etree.XMLParser:
    """The only XML parser of the package."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
        dtd_validation=False,
        remove_blank_text=False,
    )


def parse_part(data: bytes) -> Any:
    """The root element of one part; a DOCTYPE or a syntax error ends the check."""
    try:
        root = etree.fromstring(data, make_parser())
    except etree.XMLSyntaxError:
        raise Rejected("unsafe_content" if _declares(data) else "damaged") from None
    info = root.getroottree().docinfo
    if info.doctype or info.internalDTD is not None or info.externalDTD is not None:
        raise Rejected("unsafe_content")
    return root


def _declares(data: bytes) -> bool:
    """Whether a part that did not parse carries a DOCTYPE or entity declaration."""
    encoding = next((name for bom, name in _BOMS if data.startswith(bom)), "utf-8")
    text = data.decode(encoding, errors="ignore")
    return any(mark in text for mark in _DECLARATIONS)


def _read_part(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > XML_MAX_PART_BYTES:
        raise Rejected("too_large")
    blocks: list[bytes] = []
    read = 0
    with archive.open(info) as stream:
        while block := stream.read(READ_BLOCK):
            read += len(block)
            if read > XML_MAX_PART_BYTES:
                raise Rejected("too_large")
            blocks.append(block)
    return b"".join(blocks)


def check_parts(path: Path, names: tuple[str, ...]) -> None:
    """Parse every XML part among names; raises Rejected, returns nothing on success."""
    wanted = [name for name in names if name.lower().endswith(XML_SUFFIXES)]
    try:
        with zipfile.ZipFile(path) as archive:
            for name in wanted:
                root = parse_part(_read_part(archive, archive.getinfo(name)))
                if name == MANIFEST and next(root.iter(_ENCRYPTION_DATA), None) is not None:
                    raise Rejected("encrypted_document")
    except (*_UNREADABLE, KeyError):
        raise Rejected("damaged") from None
