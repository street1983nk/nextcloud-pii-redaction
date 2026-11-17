"""The attack corpus of the pre-check (SAFE-04), made where it is used, never checked in.

usage: python3 ci/make_corpus.py <outdir> [--canary-port N] [--e2e]

Standard library only. Every file is written into <outdir> together with
manifest.json, which names for each file the words the pre-check may answer
("expect"), the format the file claims to be ("expected_format", from its
extension as Nextcloud would see it), whether the sanitizer has to clean it
before LibreOffice ("sanitize"), whether it is a PDF with an owner password
only ("owner_protected", D-02-10) and whether it is for unit tests only
("unit_only"). "ok" and "confirm" (signed PDF, D-02-04) are no rejections.

Bombs are written block by block (64 KiB of zeros per compressor call), so the
generator itself needs little memory; no test unpacks them, only their
metadata is read. The canary address of the network proof is
http://127.0.0.1:<canary-port>; port 0 stands for the discard port 9, for unit
tests where nothing listens. --e2e writes only the seven files of the
deploy-harp run.

Files:
  ZIP structure  zip_ratio_bomb.docx, zip_lying_size.docx, zip_overlap.docx,
                 zip_entries_10001.docx, zip_entries_10000.docx (unit only),
                 traversal_{dotdot,abs,drive,backslash,nul}.docx,
                 dup_{exact,case,nfc,dot}.docx, zip_prefix.docx
  XML            xml_billion_laughs.docx, xml_xxe_file.docx, xml_xxe_http.docx,
                 xml_param_entity.docx, xml_doctype_only.docx
  external, macro ext_image.docx, ext_template.docx, ext_includepicture.docx,
                 ext_altchunk.docx, macro_vba.docx, odt_ext_image.odt, odt_basic.odt
  encryption     odt_encrypted.odt, cfb_encrypted.docx, pdf_user_password.pdf,
                 pdf_owner_only.pdf
  PDF            pdf_301_pages.pdf, pdf_300_pages.pdf, pdf_huge_mediabox.pdf,
                 pdf_huge_image.pdf, pdf_flate_bomb.pdf, pdf_page_loop.pdf,
                 pdf_objects_500001.pdf, pdf_signed.pdf, pdf_prefix.pdf
  wrong, broken  wrong_pdf_as_docx.docx, wrong_docx_as_pdf.pdf,
                 wrong_odt_as_docx.docx, truncated.docx, truncated.pdf
  controls       harmless.pdf, harmless.docx, harmless.odt
"""

import hashlib
import io
import json
import struct
import sys
import warnings
import zipfile
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

MIB: Final = 1024 * 1024
BLOCK: Final = 64 * 1024
DISCARD_PORT: Final = 9
DATE: Final = (2026, 11, 16, 0, 0, 0)

E2E_FILES: Final = (
    "wrong_pdf_as_docx.docx",
    "pdf_301_pages.pdf",
    "pdf_user_password.pdf",
    "pdf_signed.pdf",
    "harmless.pdf",
    "ext_image.docx",
    "cfb_encrypted.docx",
)

ODT_MIMETYPE: Final = "application/vnd.oasis.opendocument.text"
W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_TYPE: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CONTENT_TYPES: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
MACRO_CONTENT_TYPES: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/>'
    "</Types>"
)
PACKAGE_RELS: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{REL_NS}">'
    f'<Relationship Id="rId1" Type="{REL_TYPE}/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
HARMLESS_TEXT: Final = "Harmloser Inhalt ohne Personenbezug."


def _document(body: str = "", *, prolog: str = "") -> str:
    paragraph = f"<w:p><w:r><w:t>{HARMLESS_TEXT}</w:t></w:r></w:p>"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"{prolog}"
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}"><w:body>{paragraph}{body}</w:body></w:document>'
    )


def _rels(*relations: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{REL_NS}">'
        + "".join(relations)
        + "</Relationships>"
    )


def _zip(members: Sequence[tuple[str, bytes | str]], *, stored: frozenset[str] = frozenset()) -> bytes:
    """A ZIP in this member order; duplicate names are what some cases want."""
    buffer = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(buffer, "w") as archive:
        warnings.simplefilter("ignore", UserWarning)
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=DATE)
            info.compress_type = zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
            archive.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)
    return buffer.getvalue()


def _docx(extra: Sequence[tuple[str, bytes | str]] | None = None, *, document: str | None = None) -> bytes:
    members: list[tuple[str, bytes | str]] = [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", PACKAGE_RELS),
        ("word/document.xml", document if document is not None else _document()),
    ]
    return _zip([*members, *(extra or ())])


def _odt(
    content_body: str = "", *, manifest_extra: str = "", extra: Sequence[tuple[str, bytes | str]] | None = None
) -> bytes:
    ns = (
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:script="urn:oasis:names:tc:opendocument:xmlns:script:1.0"'
    )
    content = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {ns} office:version="1.3">'
        f"<office:body><office:text><text:p>{HARMLESS_TEXT}</text:p>{content_body}</office:text></office:body>"
        "</office:document-content>"
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
        f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{ODT_MIMETYPE}"/>'
        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml">'
        f"{manifest_extra}</manifest:file-entry></manifest:manifest>"
    )
    members: list[tuple[str, bytes | str]] = [
        ("mimetype", ODT_MIMETYPE),
        ("content.xml", content),
        ("META-INF/manifest.xml", manifest),
    ]
    return _zip([*members, *(extra or ())], stored=frozenset({"mimetype"}))


# -- ZIP structure ------------------------------------------------------------------


def _zeros_member(archive: zipfile.ZipFile, name: str, size: int, *, head: bytes = b"", tail: bytes = b"") -> None:
    """Stream ``size`` zero bytes (or spaces between head and tail) into one deflated member."""
    info = zipfile.ZipInfo(name, date_time=DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    filler = b" " if head else b"\x00"
    with archive.open(info, "w", force_zip64=False) as stream:
        stream.write(head)
        left = size
        while left > 0:
            step = min(BLOCK, left)
            stream.write(filler * step)
            left -= step
        stream.write(tail)


def _ratio_bomb() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compresslevel=9) as archive:
        for name, data in (("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", PACKAGE_RELS)):
            archive.writestr(zipfile.ZipInfo(name, date_time=DATE), data, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(zipfile.ZipInfo("word/document.xml", date_time=DATE), _document(), zipfile.ZIP_DEFLATED)
        _zeros_member(archive, "word/media/zeros.bin", 32 * MIB)
    return buffer.getvalue()


def _central_headers(data: bytes) -> list[int]:
    offsets = []
    at = data.find(b"PK\x01\x02")
    while at >= 0:
        offsets.append(at)
        at = data.find(b"PK\x01\x02", at + 1)
    return offsets


def _local_header_of(data: bytes, central_at: int) -> int:
    return struct.unpack_from("<I", data, central_at + 42)[0]


def _lying_size() -> bytes:
    """document.xml is 32 MiB of spaces, but both headers declare 1000 bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compresslevel=9) as archive:
        archive.writestr(zipfile.ZipInfo("[Content_Types].xml", date_time=DATE), CONTENT_TYPES, zipfile.ZIP_DEFLATED)
        archive.writestr(zipfile.ZipInfo("_rels/.rels", date_time=DATE), PACKAGE_RELS, zipfile.ZIP_DEFLATED)
        head = _document().split("<w:body>")[0].encode() + b"<w:body>"
        _zeros_member(archive, "word/document.xml", 32 * MIB, head=head, tail=b"</w:body></w:document>")
    data = bytearray(buffer.getvalue())
    central = _central_headers(bytes(data))[2]
    struct.pack_into("<I", data, central + 24, 1000)
    local = _local_header_of(bytes(data), central)
    struct.pack_into("<I", data, local + 22, 1000)
    return bytes(data)


def _overlap() -> bytes:
    """Two directory entries point at the same local header (Fifield's overlap construction)."""
    data = bytearray(_docx([("word/a.xml", "<a/>"), ("word/b.xml", "<b/>")]))
    centrals = _central_headers(bytes(data))
    struct.pack_into("<I", data, centrals[4] + 42, _local_header_of(bytes(data), centrals[3]))
    return bytes(data)


def _entries(total: int) -> bytes:
    filler = [(f"word/parts/p{number}.xml", "") for number in range(total - 3)]
    return _docx(filler)


def _renamed(placeholder: str, raw: bytes) -> bytes:
    """A docx with one member whose raw name is ``raw`` (backslashes, NUL), written over a placeholder."""
    data = _docx([(placeholder, "<x/>")])
    encoded = placeholder.encode("ascii")
    if len(encoded) != len(raw):
        raise ValueError(placeholder)
    return data.replace(encoded, raw)


def _hidden_prefix() -> bytes:
    """A docx whose first local header belongs to a member the directory does not list."""
    data = _zip(
        [("hidden.bin", b"hidden" * 16)]
        + [("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", PACKAGE_RELS), ("word/document.xml", _document())],
        stored=frozenset({"hidden.bin"}),
    )
    centrals = _central_headers(data)
    end = data.rfind(b"PK\x05\x06")
    record = bytearray(data[end:])
    struct.pack_into("<HH", record, 8, 3, 3)
    struct.pack_into("<I", record, 12, end - centrals[1])
    struct.pack_into("<I", record, 16, centrals[0])
    return data[: centrals[0]] + data[centrals[1] : end] + bytes(record)


# -- XML --------------------------------------------------------------------------


def _xml_case(prolog: str, body: str) -> bytes:
    return _docx(document=_document(body, prolog=prolog))


def _billion_laughs() -> bytes:
    entities = '<!ENTITY lol0 "lol">' + "".join(
        f'<!ENTITY lol{n} "{("&lol" + str(n - 1) + ";") * 10}">' for n in range(1, 10)
    )
    return _xml_case(f"<!DOCTYPE w:document [{entities}]>", "<w:p><w:r><w:t>&lol9;</w:t></w:r></w:p>")


# -- external references and macros -----------------------------------------------


def _ext_image(canary: str) -> bytes:
    body = (
        '<w:p><w:r><w:drawing><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:blipFill><a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" r:link="rIdImg"/>'
        "</pic:blipFill></pic:pic></w:drawing></w:r></w:p>"
    )
    rels = _rels(f'<Relationship Id="rIdImg" Type="{REL_TYPE}/image" Target="{canary}/img.png" TargetMode="External"/>')
    return _docx([("word/_rels/document.xml.rels", rels)], document=_document(body))


def _ext_template(canary: str) -> bytes:
    settings = f'<?xml version="1.0"?><w:settings xmlns:w="{W_NS}" xmlns:r="{R_NS}"><w:attachedTemplate r:id="rIdT"/></w:settings>'
    rels = _rels(
        f'<Relationship Id="rIdT" Type="{REL_TYPE}/attachedTemplate" Target="{canary}/t.dotm" TargetMode="External"/>'
    )
    doc_rels = _rels(f'<Relationship Id="rIdS" Type="{REL_TYPE}/settings" Target="settings.xml"/>')
    return _docx(
        [
            ("word/_rels/document.xml.rels", doc_rels),
            ("word/settings.xml", settings),
            ("word/_rels/settings.xml.rels", rels),
        ]
    )


def _ext_includepicture(canary: str) -> bytes:
    # The quotes of the field code are escaped: the instruction sits in an attribute.
    instr = f'INCLUDEPICTURE &quot;{canary}/p.png&quot; \\d'
    body = f'<w:p><w:fldSimple w:instr="{instr}"><w:r><w:t>Bild</w:t></w:r></w:fldSimple></w:p>'
    return _docx(document=_document(body))


def _ext_altchunk(canary: str) -> bytes:
    rels = _rels(
        f'<Relationship Id="rIdA" Type="{REL_TYPE}/aFChunk" Target="{canary}/chunk.html" TargetMode="External"/>'
    )
    return _docx([("word/_rels/document.xml.rels", rels)], document=_document('<w:altChunk r:id="rIdA"/>'))


def _macro_vba() -> bytes:
    rels = _rels(
        f'<Relationship Id="rIdV" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/>'
    )
    members: list[tuple[str, bytes | str]] = [
        ("[Content_Types].xml", MACRO_CONTENT_TYPES),
        ("_rels/.rels", PACKAGE_RELS),
        ("word/document.xml", _document()),
        ("word/_rels/document.xml.rels", rels),
        ("word/vbaProject.bin", bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 504),
    ]
    return _zip(members)


def _odt_ext_image(canary: str) -> bytes:
    frame = (
        '<draw:frame><draw:image xlink:href="'
        f'{canary}/img.png" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>'
    )
    return _odt(f"<text:p>{frame}</text:p>")


def _odt_basic() -> bytes:
    listeners = (
        "<office:event-listeners>"
        '<script:event-listener script:language="ooo:script" script:event-name="dom:load" '
        'xlink:href="vnd.sun.star.script:Standard.Module1.Main?language=Basic&amp;location=document"/>'
        "</office:event-listeners>"
    )
    module = (
        '<?xml version="1.0" encoding="UTF-8"?><script:module xmlns:script="http://openoffice.org/2000/script" '
        'script:name="Module1" script:language="StarBasic">Sub Main\nEnd Sub</script:module>'
    )
    return _odt(listeners, extra=[("Basic/Standard/Module1.xml", module)])


# -- compound file (password-protected OOXML) -------------------------------------------


def _cfb_encrypted() -> bytes:
    """[MS-CFB] version 3 with a directory naming EncryptionInfo and EncryptedPackage."""
    free, end, fatsect, nostream = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF

    def entry(name: str, kind: int, child: int = nostream, right: int = nostream) -> bytes:
        encoded = (name + "\x00").encode("utf-16-le")
        return (
            encoded.ljust(64, b"\x00") + struct.pack("<HBBIII", len(encoded), kind, 1, nostream, right, child)
        ).ljust(128, b"\x00")

    directory = entry("Root Entry", 5, child=1) + entry("EncryptionInfo", 2, right=2) + entry("EncryptedPackage", 2)
    directory = directory.ljust(512, b"\x00")
    fat = struct.pack("<128I", fatsect, end, *([free] * 126))
    header = bytearray(512)
    header[0:8] = bytes.fromhex("d0cf11e0a1b11ae1")
    struct.pack_into("<HHHHH", header, 0x18, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<III", header, 0x2C, 1, 1, 0)
    struct.pack_into("<IIIII", header, 0x38, 4096, end, 0, end, 0)
    struct.pack_into("<109I", header, 0x4C, 0, *([free] * 108))
    return bytes(header) + fat + directory


# -- PDF --------------------------------------------------------------------------------


def _stream(data: bytes, extra: bytes = b"") -> bytes:
    return b"<< /Length " + str(len(data)).encode() + b" " + extra + b">>\nstream\n" + data + b"\nendstream"


def _pdf(objects: list[bytes], *, trailer: bytes = b"") -> bytes:
    """A PDF with these objects (1 is the catalog) and an exact cross reference table."""
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R ".encode() + trailer + b">>\n"
    out += f"startxref\n{xref}\n".encode() + b"%%EOF\n"
    return bytes(out)


TEXT_CONTENT: Final = b"BT /F1 12 Tf 72 720 Td (Harmloser Inhalt) Tj ET"
FONT: Final = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"


def _pages(count: int, *, media_box: bytes = b"[0 0 595 842]") -> bytes:
    """count pages sharing one content stream and one font."""
    first_page = 5
    kids = b" ".join(f"{first_page + n} 0 R".encode() for n in range(count))
    page = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox "
        + media_box
        + b" /Contents 3 0 R /Resources << /Font << /F1 4 0 R >> >> >>"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(count).encode() + b" >>",
        _stream(TEXT_CONTENT),
        FONT,
    ] + [page] * count
    return _pdf(objects)


def _huge_image() -> bytes:
    image = _stream(
        zlib.compress(b"\x00" * 1024),
        b"/Type /XObject /Subtype /Image /Width 100000 /Height 100000 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Filter /FlateDecode ",
    )
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /XObject << /Im1 5 0 R >> >> >>",
            _stream(b"q 100 0 0 100 0 0 cm /Im1 Do Q"),
            image,
        ]
    )


def _flate_bomb() -> bytes:
    compressor = zlib.compressobj(9)
    parts = [compressor.compress(b"\x00" * BLOCK) for _ in range(32 * MIB // BLOCK)]
    data = b"".join(parts) + compressor.flush()
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>",
            _stream(data, b"/Filter /FlateDecode "),
        ]
    )


def _page_loop() -> bytes:
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [2 0 R 3 0 R] /Count 2 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
        ]
    )


def _many_objects(total: int) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
    ] + [b"null"] * (total - 3)
    return _pdf(objects)


def _signed() -> bytes:
    contents = b"<" + b"00" * 64 + b">"
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [5 0 R] /SigFlags 3 >> >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Annots [5 0 R] "
            b"/Resources << /Font << /F1 7 0 R >> >> >>",
            _stream(TEXT_CONTENT),
            b"<< /Type /Annot /Subtype /Widget /FT /Sig /T (Signature1) /V 6 0 R /Rect [0 0 0 0] /P 3 0 R /F 132 >>",
            b"<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached "
            b"/ByteRange [0 1000 1130 2000] /Contents " + contents + b" /M (D:20261116000000Z) >>",
            FONT,
        ]
    )


# Standard security handler, revision 2, RC4 with 40 bit keys (ISO 32000-1, 7.6.3.3,
# algorithms 2, 3 and 4; 7.6.2 algorithm 1 for the per object key).
_PASSWORD_PAD: Final = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")
_FILE_ID: Final = hashlib.md5(b"pii-redaction corpus").digest()  # noqa: S324 - the PDF format prescribes MD5


def _rc4(key: bytes, data: bytes) -> bytes:
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        out.append(byte ^ state[(state[i] + state[j]) % 256])
    return bytes(out)


def _padded(password: bytes) -> bytes:
    return (password + _PASSWORD_PAD)[:32]


def _encrypted_pdf(user: bytes, owner: bytes, permissions: int) -> bytes:
    owner_key = hashlib.md5(_padded(owner or user)).digest()[:5]  # noqa: S324 - algorithm 3
    owner_entry = _rc4(owner_key, _padded(user))
    file_key = hashlib.md5(  # noqa: S324 - algorithm 2
        _padded(user) + owner_entry + struct.pack("<i", permissions) + _FILE_ID
    ).digest()[:5]
    user_entry = _rc4(file_key, _PASSWORD_PAD)  # algorithm 4
    object_key = hashlib.md5(file_key + (3).to_bytes(3, "little") + (0).to_bytes(2, "little")).digest()[:10]  # noqa: S324
    content = _rc4(object_key, TEXT_CONTENT)
    encrypt = (
        b"<< /Filter /Standard /V 1 /R 2 /O <" + owner_entry.hex().encode() + b"> /U <" + user_entry.hex().encode()
        + b"> /P " + str(permissions).encode() + b" >>"
    )  # fmt: skip
    file_id = b"<" + _FILE_ID.hex().encode() + b">"
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
            _stream(content),
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 3 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            FONT,
            encrypt,
        ],
        trailer=b"/Encrypt 6 0 R /ID [" + file_id + b" " + file_id + b"] ",
    )


# -- the corpus ----------------------------------------------------------------------


Case = tuple[Callable[[str], bytes], tuple[str, ...], str, dict[str, bool]]


def _cases() -> dict[str, Case]:
    """name -> (maker(canary), expected words, claimed format, flags)."""
    harmless_pdf = _pages(1)

    def fixed(data: Callable[[], bytes]) -> Callable[[str], bytes]:
        return lambda _canary: data()

    unsafe = ("unsafe_content",)
    return {
        "zip_ratio_bomb.docx": (fixed(_ratio_bomb), unsafe, "docx", {}),
        "zip_lying_size.docx": (fixed(_lying_size), ("unsafe_content", "too_large", "damaged"), "docx", {}),
        "zip_overlap.docx": (fixed(_overlap), unsafe, "docx", {}),
        "zip_entries_10001.docx": (fixed(lambda: _entries(10_001)), ("too_large",), "docx", {}),
        "zip_entries_10000.docx": (fixed(lambda: _entries(10_000)), ("ok",), "docx", {"unit_only": True}),
        "traversal_dotdot.docx": (fixed(lambda: _docx([("../evil.xml", "<x/>")])), unsafe, "docx", {}),
        "traversal_abs.docx": (fixed(lambda: _docx([("/abs.xml", "<x/>")])), unsafe, "docx", {}),
        "traversal_drive.docx": (fixed(lambda: _docx([("C:/drive.xml", "<x/>")])), unsafe, "docx", {}),
        "traversal_backslash.docx": (
            fixed(lambda: _renamed("wordQ..Q..Qevil.xml", b"word\\..\\..\\evil.xml")),
            unsafe,
            "docx",
            {},
        ),
        "traversal_nul.docx": (fixed(lambda: _renamed("wordXnul.xml", b"word\x00nul.xml")), unsafe, "docx", {}),
        "dup_exact.docx": (fixed(lambda: _docx([("word/document.xml", _document())])), unsafe, "docx", {}),
        "dup_case.docx": (fixed(lambda: _docx([("Word/Document.xml", _document())])), unsafe, "docx", {}),
        "dup_nfc.docx": (
            fixed(lambda: _docx([("word/\u00e4.xml", "<a/>"), ("word/a\u0308.xml", "<b/>")])),
            unsafe,
            "docx",
            {},
        ),
        "dup_dot.docx": (fixed(lambda: _docx([("./word/a.xml", "<a/>"), ("word/a.xml", "<b/>")])), unsafe, "docx", {}),
        "zip_prefix.docx": (fixed(_hidden_prefix), unsafe, "docx", {}),
        "xml_billion_laughs.docx": (fixed(_billion_laughs), unsafe, "docx", {}),
        "xml_xxe_file.docx": (
            fixed(
                lambda: _xml_case('<!DOCTYPE w:document [<!ENTITY x SYSTEM "file:///etc/passwd">]>', "<w:p>&x;</w:p>")
            ),
            unsafe,
            "docx",
            {},
        ),
        "xml_xxe_http.docx": (
            lambda canary: _xml_case(f'<!DOCTYPE w:document [<!ENTITY x SYSTEM "{canary}/xxe">]>', "<w:p>&x;</w:p>"),
            unsafe,
            "docx",
            {},
        ),
        "xml_param_entity.docx": (
            lambda canary: _xml_case(f'<!DOCTYPE w:document [<!ENTITY % p SYSTEM "{canary}/p.dtd"> %p;]>', ""),
            unsafe,
            "docx",
            {},
        ),
        "xml_doctype_only.docx": (fixed(lambda: _xml_case("<!DOCTYPE w:document>", "")), unsafe, "docx", {}),
        "ext_image.docx": (_ext_image, ("ok",), "docx", {"sanitize": True}),
        "ext_template.docx": (_ext_template, ("ok",), "docx", {"sanitize": True}),
        "ext_includepicture.docx": (_ext_includepicture, ("ok",), "docx", {"sanitize": True}),
        "ext_altchunk.docx": (_ext_altchunk, ("ok",), "docx", {"sanitize": True}),
        "macro_vba.docx": (fixed(_macro_vba), ("ok",), "docx", {"sanitize": True}),
        "odt_ext_image.odt": (_odt_ext_image, ("ok",), "odt", {"sanitize": True}),
        "odt_basic.odt": (fixed(_odt_basic), ("ok",), "odt", {"sanitize": True}),
        "odt_encrypted.odt": (
            fixed(lambda: _odt(manifest_extra='<manifest:encryption-data manifest:checksum-type="SHA1/1K"/>')),
            ("encrypted_document",),
            "odt",
            {},
        ),
        "cfb_encrypted.docx": (fixed(_cfb_encrypted), ("encrypted_document",), "docx", {}),
        "pdf_301_pages.pdf": (fixed(lambda: _pages(301)), ("too_many_pages",), "pdf", {}),
        "pdf_300_pages.pdf": (fixed(lambda: _pages(300)), ("ok",), "pdf", {}),
        "pdf_huge_mediabox.pdf": (fixed(lambda: _pages(1, media_box=b"[0 0 20000 20000]")), ("too_large",), "pdf", {}),
        "pdf_huge_image.pdf": (fixed(_huge_image), ("too_large",), "pdf", {}),
        "pdf_flate_bomb.pdf": (fixed(_flate_bomb), ("too_large", "damaged"), "pdf", {}),
        "pdf_page_loop.pdf": (fixed(_page_loop), ("damaged",), "pdf", {}),
        "pdf_objects_500001.pdf": (fixed(lambda: _many_objects(500_001)), ("too_large",), "pdf", {}),
        "pdf_user_password.pdf": (
            fixed(lambda: _encrypted_pdf(b"geheim", b"besitzer", -4)),
            ("encrypted_pdf",),
            "pdf",
            {},
        ),
        "pdf_owner_only.pdf": (
            fixed(lambda: _encrypted_pdf(b"", b"besitzer", -64)),
            ("ok",),
            "pdf",
            {"owner_protected": True},
        ),
        "pdf_signed.pdf": (fixed(_signed), ("confirm",), "pdf", {}),
        "pdf_prefix.pdf": (fixed(lambda: b"JUNK\n" + harmless_pdf), ("damaged",), "pdf", {}),
        "wrong_pdf_as_docx.docx": (fixed(lambda: harmless_pdf), ("wrong_type",), "docx", {}),
        "wrong_docx_as_pdf.pdf": (fixed(_docx), ("wrong_type",), "pdf", {}),
        "wrong_odt_as_docx.docx": (fixed(_odt), ("wrong_type",), "docx", {}),
        "truncated.docx": (fixed(lambda: _docx()[: len(_docx()) // 2]), ("damaged",), "docx", {}),
        "truncated.pdf": (fixed(lambda: harmless_pdf[:40]), ("damaged",), "pdf", {}),
        "harmless.pdf": (fixed(lambda: harmless_pdf), ("ok",), "pdf", {}),
        "harmless.docx": (fixed(_docx), ("ok",), "docx", {}),
        "harmless.odt": (fixed(_odt), ("ok",), "odt", {}),
    }


def canary_address(port: int) -> str:
    return f"http://127.0.0.1:{port or DISCARD_PORT}"


def build(outdir: Path, canary_port: int = 0, *, e2e: bool = False) -> dict[str, dict[str, object]]:
    """Write the corpus and manifest.json into ``outdir``; returns the manifest."""
    outdir.mkdir(parents=True, exist_ok=True)
    canary = canary_address(canary_port)
    manifest: dict[str, dict[str, object]] = {}
    for name, (maker, expect, claimed, flags) in _cases().items():
        if e2e and name not in E2E_FILES:
            continue
        (outdir / name).write_bytes(maker(canary))
        manifest[name] = {
            "expect": list(expect),
            "expected_format": claimed,
            "sanitize": flags.get("sanitize", False),
            "owner_protected": flags.get("owner_protected", False),
            "unit_only": flags.get("unit_only", False),
        }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    return manifest


def main(argv: list[str]) -> int:
    args = list(argv)
    e2e = "--e2e" in args
    if e2e:
        args.remove("--e2e")
    port = 0
    if "--canary-port" in args:
        at = args.index("--canary-port")
        try:
            port = int(args[at + 1])
        except (IndexError, ValueError):
            port = -1
        del args[at : at + 2]
    if len(args) != 1 or not 0 <= port <= 65535:
        print("usage: make_corpus.py <outdir> [--canary-port N] [--e2e]", file=sys.stderr)
        return 2
    build(Path(args[0]), port, e2e=e2e)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
