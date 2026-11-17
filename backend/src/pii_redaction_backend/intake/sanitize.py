"""The sanitizer in front of LibreOffice (SAFE-03, RESEARCH Pattern 4).

LibreOffice never sees the original DOCX or ODT. It gets a copy from which
everything that can load from elsewhere or run code is gone, the line
Gotenberg took in 8.34.0 (remove linked content at the source instead of
trusting LibreOffice settings). The copy is LibreOffice input only; what
happens to links in the redacted output is decided in phase 7.

DOCX: every relationship with TargetMode="External" goes (a hyperlink keeps
its id with an empty target), as do the relationships and parts of macros,
ActiveX, OLE embeddings, attached templates, sub documents, frames and
alternative chunks; a:blip r:link, w:altChunk, w:attachedTemplate and the
webSettings frameset go; fields that load (INCLUDEPICTURE, INCLUDETEXT, LINK,
DDE, DDEAUTO, IMPORT) are replaced by their cached result; a macro enabled
content type becomes the plain DOCX type.

ODT: external xlink:href on images, objects, OLE objects and floating frames
goes; section and table sources and DDE declarations go; office:scripts,
office:event-listeners, Basic/ and Scripts/ go, with their manifest entries.

Every XML part goes through the one parser of xmlcheck. The copy is checked
again by zipcheck and xmlcheck before it is handed on (the sanitizer must not
create a new danger). The report carries two numbers and nothing else.
Nothing is logged.
"""

import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from lxml import etree  # pyright: ignore[reportAttributeAccessIssue] - compiled module, no stubs pinned

from pii_redaction_backend.intake.limits import XML_MAX_PART_BYTES, ZIP_MAX_MEMBER_BYTES
from pii_redaction_backend.intake.verdict import Rejected
from pii_redaction_backend.intake.xmlcheck import check_parts, parse_part
from pii_redaction_backend.intake.zipcheck import check_zip

READ_BLOCK: Final = 64 * 1024
# The copy may grow a little when the archive is written anew; the sandbox
# file size limit of the sanitize profile carries the same 10 %.
GROWTH_PERCENT: Final = 10

# -- DOCX --------------------------------------------------------------------------------

W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_LINK: Final = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link"
REL: Final = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
CT_DEFAULT: Final = "{http://schemas.openxmlformats.org/package/2006/content-types}Default"
CT_OVERRIDE: Final = "{http://schemas.openxmlformats.org/package/2006/content-types}Override"
HYPERLINK_TYPE: Final = "/hyperlink"

# Relationship types whose target is code, an embedded program or a way to
# load something else; the relationship and its internal target part go.
DROPPED_REL_TYPES: Final = (
    "/vbaProject",
    "/wordVbaData",
    "/keyMapCustomizations",
    "/attachedToolbars",
    "/control",
    "/activeXControlBinary",
    "/oleObject",
    "/package",
    "/aFChunk",
    "/attachedTemplate",
    "/subDocument",
    "/frame",
)
# Parts that are code or embedded programs, by name (lower case).
DROPPED_DOCX_NAMES: Final = ("vbaproject.bin", "vbadata.xml", "customizations.xml", "attachedtoolbars.bin")
DROPPED_DOCX_PREFIXES: Final = ("word/activex/", "word/embeddings/")
MACRO_PARTS: Final = ("vbaproject.bin", "vbadata.xml", "customizations.xml", "attachedtoolbars.bin", "word/activex/")
LOADING_FIELDS: Final = frozenset({"INCLUDEPICTURE", "INCLUDETEXT", "LINK", "DDE", "DDEAUTO", "IMPORT"})
MACRO_CONTENT_TYPES: Final = {
    "application/vnd.ms-word.document.macroEnabled.main+xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    ),
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
    ),
}
VBA_CONTENT_TYPE_MARK: Final = "vbaproject"

# -- ODT ---------------------------------------------------------------------------------

OFFICE: Final = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT: Final = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE: Final = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
DRAW: Final = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
XLINK_HREF: Final = "{http://www.w3.org/1999/xlink}href"
MANIFEST_NS: Final = "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}"
ODT_MACRO_PREFIXES: Final = ("Basic/", "Scripts/")
# Elements that run code when the document opens.
ODT_SCRIPT_ELEMENTS: Final = (f"{OFFICE}scripts", f"{OFFICE}event-listeners")
# Elements that name a source to load the content from: they go as a whole.
ODT_SOURCE_ELEMENTS: Final = (
    f"{TEXT}section-source",
    f"{TABLE}table-source",
    f"{OFFICE}dde-source",
    f"{TEXT}dde-connection-decls",
    f"{TEXT}dde-connection",
    f"{TABLE}dde-links",
)
# Elements whose external xlink:href is removed, the element stays.
ODT_LINKED_ELEMENTS: Final = (
    f"{DRAW}image",
    f"{DRAW}object",
    f"{DRAW}object-ole",
    f"{DRAW}floating-frame",
    f"{DRAW}plugin",
    f"{DRAW}applet",
    f"{DRAW}fill-image",
)
MIMETYPE: Final = "mimetype"
MANIFEST: Final = "META-INF/manifest.xml"

# A URL scheme (http:, file:, smb:, vnd.sun.star.script:, C: on Windows) means outside the package.
_SCHEME: Final = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_UNREADABLE: Final = (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError, ValueError, NotImplementedError)


@dataclass(frozen=True, slots=True)
class SanitizeReport:
    """What the sanitizer removed: for the file card and the protocol (D-02-12)."""

    macros_removed: bool
    external_links_removed: int


@dataclass
class _Tally:
    macros: bool = False
    links: int = 0


def sanitize(src: Path, dst: Path, fmt: Literal["docx", "odt"]) -> SanitizeReport:
    """Write the cleaned copy of src to dst; raises Rejected and leaves no dst on failure."""
    tally = _Tally()
    try:
        with zipfile.ZipFile(src) as archive:
            members = archive.infolist()
            dropped = _docx_dropped(archive, members, tally) if fmt == "docx" else _odt_dropped(members, tally)
            _write(archive, members, dropped, dst, fmt, tally)
        if dst.stat().st_size > src.stat().st_size * (100 + GROWTH_PERCENT) // 100:
            raise Rejected("too_large")
        report = check_zip(dst)
        check_parts(dst, report.names)
    except Rejected as rejected:
        dst.unlink(missing_ok=True)
        verdict = rejected.verdict if rejected.verdict == "too_large" else "damaged"
        raise Rejected(verdict) from None
    except (*_UNREADABLE, KeyError, etree.LxmlError):
        dst.unlink(missing_ok=True)
        raise Rejected("damaged") from None
    return SanitizeReport(macros_removed=tally.macros, external_links_removed=tally.links)


# -- reading and writing -----------------------------------------------------------------


def _read(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    if info.file_size > limit:
        raise Rejected("too_large")
    blocks: list[bytes] = []
    read = 0
    with archive.open(info) as stream:
        while block := stream.read(READ_BLOCK):
            read += len(block)
            if read > limit:
                raise Rejected("too_large")
            blocks.append(block)
    return b"".join(blocks)


def _is_xml(name: str) -> bool:
    return name.lower().endswith((".xml", ".rels"))


def _write(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    dropped: set[str],
    dst: Path,
    fmt: str,
    tally: _Tally,
) -> None:
    kept = [info for info in members if info.filename not in dropped]
    if fmt == "odt":
        # ODF: the mimetype member comes first and is stored.
        kept.sort(key=lambda info: info.filename != MIMETYPE)
    with zipfile.ZipFile(dst, "w", compresslevel=9) as out:
        for info in kept:
            target = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            target.external_attr = 0o644 << 16
            stored = fmt == "odt" and info.filename == MIMETYPE
            target.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            if _is_xml(info.filename):
                data = _read(archive, info, XML_MAX_PART_BYTES)
                data = _clean_xml(info.filename, data, fmt, dropped, tally)
            else:
                data = _read(archive, info, ZIP_MAX_MEMBER_BYTES)
            out.writestr(target, data)


def _serialize(root: Any) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clean_xml(name: str, data: bytes, fmt: str, dropped: set[str], tally: _Tally) -> bytes:
    root = parse_part(data)
    changed = (
        _clean_docx_part(name, root, dropped, tally) if fmt == "docx" else _clean_odt_part(name, root, dropped, tally)
    )
    return _serialize(root) if changed else data


def _remove(element: Any) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


# -- DOCX rules ----------------------------------------------------------------------------


def _is_dropped_docx_name(name: str) -> bool:
    lower = name.lower()
    return lower.rsplit("/", 1)[-1] in DROPPED_DOCX_NAMES or lower.startswith(DROPPED_DOCX_PREFIXES)


def _rels_source_dir(rels_name: str) -> str:
    """word/_rels/document.xml.rels -> word; _rels/.rels -> the package root."""
    return posixpath.dirname(posixpath.dirname(rels_name))


def _resolve(rels_name: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(_rels_source_dir(rels_name), target))


def _docx_dropped(archive: zipfile.ZipFile, members: list[zipfile.ZipInfo], tally: _Tally) -> set[str]:
    """The parts that do not go into the copy: by name and as targets of dropped relationships."""
    names = {info.filename for info in members}
    dropped = {name for name in names if _is_dropped_docx_name(name)}
    for info in members:
        if not info.filename.lower().endswith(".rels"):
            continue
        root = parse_part(_read(archive, info, XML_MAX_PART_BYTES))
        for relationship in root.iter(REL):
            kind = relationship.get("Type", "")
            external = relationship.get("TargetMode") == "External"
            if not external and kind.endswith(DROPPED_REL_TYPES):
                target = _resolve(info.filename, relationship.get("Target", ""))
                if target in names:
                    dropped.add(target)
    # A relationship part of a dropped part goes with it.
    for name in list(dropped):
        folder, base = posixpath.split(name)
        dropped.add(posixpath.join(folder, "_rels", f"{base}.rels"))
    tally.macros = any(
        name.lower().endswith(MACRO_PARTS) or name.lower().startswith(MACRO_PARTS) for name in dropped & names
    )
    return dropped & names


def _clean_docx_part(name: str, root: Any, dropped: set[str], tally: _Tally) -> bool:
    if name.lower().endswith(".rels"):
        return _clean_rels(name, root, dropped, tally)
    if name == "[Content_Types].xml":
        return _clean_content_types(root, dropped, tally)
    changed = False
    for element in list(root.iter(f"{W}altChunk", f"{W}attachedTemplate", f"{W}frameset")):
        _remove(element)
        changed = True
    for element in root.iter():
        if element.get(R_LINK) is not None:
            del element.attrib[R_LINK]
            changed = True
    changed |= _clean_simple_fields(root, tally)
    changed |= _clean_complex_fields(root, tally)
    return changed


def _clean_rels(name: str, root: Any, dropped: set[str], tally: _Tally) -> bool:
    changed = False
    for relationship in list(root.iter(REL)):
        kind = relationship.get("Type", "")
        if relationship.get("TargetMode") == "External":
            tally.links += 1
            changed = True
            if kind.endswith(HYPERLINK_TYPE):
                relationship.set("Target", "")
                del relationship.attrib["TargetMode"]
            else:
                _remove(relationship)
            continue
        target = _resolve(name, relationship.get("Target", ""))
        if kind.endswith(DROPPED_REL_TYPES) or target in dropped:
            _remove(relationship)
            changed = True
    return changed


def _clean_content_types(root: Any, dropped: set[str], tally: _Tally) -> bool:
    changed = False
    for element in list(root.iter(CT_DEFAULT, CT_OVERRIDE)):
        content_type = element.get("ContentType", "")
        if content_type in MACRO_CONTENT_TYPES:
            element.set("ContentType", MACRO_CONTENT_TYPES[content_type])
            tally.macros = True
            changed = True
            continue
        part = element.get("PartName", "").lstrip("/")
        if VBA_CONTENT_TYPE_MARK in content_type.lower() or (part and part in dropped):
            _remove(element)
            changed = True
    return changed


def _field_keyword(instruction: str) -> str:
    words = instruction.strip().split()
    return words[0].upper() if words else ""


def _clean_simple_fields(root: Any, tally: _Tally) -> bool:
    changed = False
    for field in list(root.iter(f"{W}fldSimple")):
        if _field_keyword(field.get(f"{W}instr", "")) not in LOADING_FIELDS:
            continue
        parent = field.getparent()
        if parent is None:
            continue
        index = parent.index(field)
        for offset, child in enumerate(list(field)):
            parent.insert(index + offset, child)
        parent.remove(field)
        tally.links += 1
        changed = True
    return changed


@dataclass
class _Field:
    elements: list[Any]
    instruction: list[str]
    in_code: bool = True


def _clean_complex_fields(root: Any, tally: _Tally) -> bool:
    """Fields made of fldChar runs: a loading one keeps only the runs of its result."""
    stack: list[_Field] = []
    doomed: list[Any] = []
    for run in list(root.iter(f"{W}r")):
        for child in list(run):
            if child.tag == f"{W}fldChar":
                kind = child.get(f"{W}fldCharType")
                if kind == "begin":
                    stack.append(_Field(elements=[], instruction=[]))
                if not stack:
                    continue
                for field in stack:
                    if field.in_code:
                        field.elements.append(child)
                if kind == "separate":
                    stack[-1].in_code = False
                elif kind == "end":
                    field = stack.pop()
                    field.elements.append(child)
                    if _field_keyword("".join(field.instruction)) in LOADING_FIELDS:
                        doomed.extend(field.elements)
                        tally.links += 1
                continue
            if child.tag in (f"{W}instrText", f"{W}delInstrText") and stack and stack[-1].in_code:
                stack[-1].instruction.append(child.text or "")
            if child.tag == f"{W}rPr":
                continue
            for field in stack:
                if field.in_code:
                    field.elements.append(child)
    for element in dict.fromkeys(doomed):
        _remove(element)
    return bool(doomed)


# -- ODT rules ------------------------------------------------------------------------------


def _external(href: str) -> bool:
    if not href:
        return False
    if href.startswith(("/", "\\", "../")) or "/../" in href or "\\" in href:
        return True
    return _SCHEME.match(href) is not None


def _odt_dropped(members: list[zipfile.ZipInfo], tally: _Tally) -> set[str]:
    dropped = {info.filename for info in members if info.filename.startswith(ODT_MACRO_PREFIXES)}
    if dropped:
        tally.macros = True
    return dropped


def _clean_odt_part(name: str, root: Any, dropped: set[str], tally: _Tally) -> bool:
    changed = False
    if name == MANIFEST:
        for entry in list(root.iter(f"{MANIFEST_NS}file-entry")):
            path = entry.get(f"{MANIFEST_NS}full-path", "")
            if path.startswith(ODT_MACRO_PREFIXES) or path in dropped:
                _remove(entry)
                changed = True
        return changed
    for element in list(root.iter(*ODT_SCRIPT_ELEMENTS)):
        _remove(element)
        tally.macros = True
        changed = True
    for element in list(root.iter(*ODT_SOURCE_ELEMENTS)):
        _remove(element)
        tally.links += 1
        changed = True
    for element in root.iter(*ODT_LINKED_ELEMENTS):
        if _external(element.get(XLINK_HREF, "")):
            del element.attrib[XLINK_HREF]
            tally.links += 1
            changed = True
    return changed
