"""The test documents of the integration proof, made in the runner, never checked in.

usage: python3 ci/make_fixtures.py <outdir>

Four files, standard library only (the runner has no PyMuPDF):

  Bescheid 2026-114.pdf  two pages, Helvetica, content streams without a
                         filter, so the canary stands in the raw bytes
  Antrag.docx            the four parts a word processor needs, nothing else
  Vermerk.odt            mimetype first and stored, manifest, content, styles
  notes.txt              plain text, the format the file action must not offer

The canary PIIKANARIE7Q4XZ9 stands in the body text of the three documents and
nowhere else: not in a file name, not in an info dictionary, no docProps, no
meta.xml (01-RESEARCH.md, decision 10 and pitfall I). The scan at the end of
the run first finds it in the uploaded originals (positive control) and then
must not find it in any database, log or copy.
"""

import sys
import zipfile
from pathlib import Path
from typing import Final

CANARY: Final = "PIIKANARIE7Q4XZ9"
PDF_NAME: Final = "Bescheid 2026-114.pdf"
DOCX_NAME: Final = "Antrag.docx"
ODT_NAME: Final = "Vermerk.odt"
TXT_NAME: Final = "notes.txt"

# Synthetic German body text with umlauts and the canary in one sentence.
LINES: Final = (
    "Bescheid über die Gewährung von Akteneinsicht",
    "Sehr geehrte Frau Jürgensen,",
    "Ihr Antrag vom 3. März 2026 wurde geprüft und ist zulässig.",
    f"Bitte geben Sie bei Rückfragen das Merkzeichen {CANARY} an.",
    "Die Unterlagen liegen zur Einsicht im Bürgerbüro bereit.",
)
PAGE_TWO: Final = (
    "Rechtsbehelfsbelehrung",
    "Gegen diesen Bescheid kann innerhalb eines Monats Widerspruch erhoben werden.",
    "Mit freundlichen Grüßen",
)
NOTES: Final = "Notizen zur Besprechung, ohne Personenbezug.\n"


def _pdf_literal(text: str) -> bytes:
    """A PDF literal string in WinAnsiEncoding (cp1252 covers the umlauts and ß)."""
    raw = text.encode("cp1252")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _content(lines: tuple[str, ...]) -> bytes:
    parts = [b"BT", b"/F1 12 Tf", b"14 TL", b"72 770 Td"]
    for line in lines:
        parts.append(_pdf_literal(line) + b" Tj T*")
    parts.append(b"ET")
    return b"\n".join(parts) + b"\n"


def make_pdf() -> bytes:
    """Hand written objects with exact xref offsets; no /Info in the trailer."""
    contents = (_content(LINES), _content(PAGE_TWO))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R 5 0 R] /Count 2 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for number in (6, 7):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents " + str(number).encode() + b" 0 R >>"
        )
    for stream in contents:
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return bytes(out)


def _xml_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


DOCX_TYPES: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
DOCX_RELS: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)
DOCX_DOCUMENT_RELS: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
)


def make_docx() -> bytes:
    paragraphs = "".join(f'<w:p><w:r><w:t xml:space="preserve">{_xml_text(line)}</w:t></w:r></w:p>' for line in LINES)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}<w:sectPr/></w:body></w:document>"
    )
    return _zip(
        [
            ("[Content_Types].xml", DOCX_TYPES),
            ("_rels/.rels", DOCX_RELS),
            ("word/document.xml", document),
            ("word/_rels/document.xml.rels", DOCX_DOCUMENT_RELS),
        ]
    )


ODT_MIME: Final = "application/vnd.oasis.opendocument.text"
ODT_MANIFEST: Final = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
    f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{ODT_MIME}"/>'
    '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
    '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
    "</manifest:manifest>"
)
ODT_NS: Final = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.3"'
)
ODT_STYLES: Final = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f"<office:document-styles {ODT_NS}><office:styles/></office:document-styles>"
)


def make_odt() -> bytes:
    paragraphs = "".join(f"<text:p>{_xml_text(line)}</text:p>" for line in LINES)
    content = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-content {ODT_NS}>'
        f"<office:body><office:text>{paragraphs}</office:text></office:body></office:document-content>"
    )
    return _zip(
        [
            ("mimetype", ODT_MIME),
            ("META-INF/manifest.xml", ODT_MANIFEST),
            ("content.xml", content),
            ("styles.xml", ODT_STYLES),
        ]
    )


def _zip(parts: list[tuple[str, str]]) -> bytes:
    """A ZIP with fixed timestamps; an ODT mimetype entry stays stored and first."""
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in parts:
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            archive.writestr(info, data.encode("utf-8"))
    return buffer.getvalue()


def write_all(outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, data in (
        (PDF_NAME, make_pdf()),
        (DOCX_NAME, make_docx()),
        (ODT_NAME, make_odt()),
        (TXT_NAME, NOTES.encode("utf-8")),
    ):
        target = outdir / name
        target.write_bytes(data)
        made.append(target)
    return made


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: make_fixtures.py <outdir>", file=sys.stderr)
        return 2
    for path in write_all(Path(argv[0])):
        print(path.name, path.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
