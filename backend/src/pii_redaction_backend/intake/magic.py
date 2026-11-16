"""Stage A of the pre-check: the format by its bytes, never by name or mime type (SAFE-02, JOB-05).

PDF: ``%PDF-`` at offset 0. A header further in (up to 1024 bytes, where
readers still look for it) is a polyglot and refused as damaged (A10). ZIP:
``PK\\x03\\x04`` at offset 0; the ZIP structure is checked before any ZipFile is
built, then [Content_Types].xml with word/document.xml makes a DOCX and a
first member "mimetype" with the ODF text type makes an ODT. A compound file
(CFB) is a password-protected Office document when its directory lists
EncryptionInfo or EncryptedPackage ([MS-OFFCRYPTO]); any other compound file is
an old binary format. The format found is compared with the one the file
claims (its Nextcloud mime type): a difference is wrong_type.

Only the head, the compound file directory (bounded) and the ZIP directory are
read; nothing is extracted. Every refusal is a Rejected with a word of the
closed list.
"""

import struct
from pathlib import Path
from typing import BinaryIO, Final, Literal

from .limits import CFB_MAX_DIRECTORY_BYTES, MAX_SOURCE_BYTES
from .verdict import Rejected
from .zipcheck import check_zip, read_member_head

Format = Literal["pdf", "docx", "odt"]

PDF_MAGIC: Final = b"%PDF-"
ZIP_MAGIC: Final = b"PK\x03\x04"
CFB_MAGIC: Final = bytes.fromhex("d0cf11e0a1b11ae1")
# How far in a PDF header is still looked for, to call a file with a prefix damaged.
PDF_HEADER_WINDOW: Final = 1024
ODT_MIMETYPE: Final = b"application/vnd.oasis.opendocument.text"
MIMETYPE_MAX_BYTES: Final = 128
DOCX_PARTS: Final = frozenset({"[Content_Types].xml", "word/document.xml"})

# [MS-CFB] 2.2 header and 2.6 directory entry.
_CFB_HEADER_BYTES: Final = 512
_CFB_SHIFT_AT: Final = 0x1E
_CFB_FAT_COUNT_AT: Final = 0x2C
_CFB_FIRST_DIRECTORY_AT: Final = 0x30
_CFB_DIFAT_AT: Final = 0x4C
_CFB_HEADER_DIFAT: Final = 109
_CFB_SHIFTS: Final = frozenset({9, 12})
_CFB_END_OF_CHAIN: Final = 0xFFFFFFFE
_CFB_MAX_REGULAR: Final = 0xFFFFFFFA
_CFB_ENTRY_BYTES: Final = 128
_CFB_NAME_LENGTH_AT: Final = 0x40
_CFB_TYPE_AT: Final = 0x42
_CFB_STREAM: Final = 2
_ENCRYPTED_STREAMS: Final = frozenset({"EncryptionInfo", "EncryptedPackage"})


class _Broken(Exception):
    """A compound file structure the specification does not allow."""


def detect(path: Path, expected: Format) -> Format:
    """The format of the file, if it is the one it claims to be; otherwise Rejected."""
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        if size == 0:
            raise Rejected("damaged")
        if size > MAX_SOURCE_BYTES:
            raise Rejected("too_large")
        handle.seek(0)
        head = handle.read(PDF_HEADER_WINDOW)
        if head.startswith(CFB_MAGIC):
            found = _compound_file(handle, size, expected)
        elif head.startswith(PDF_MAGIC):
            found = "pdf"
        elif head.startswith(ZIP_MAGIC):
            found = None
        elif PDF_MAGIC in head:
            raise Rejected("damaged")
        else:
            raise Rejected("unsupported_format")
    if found is None:
        found = _package(path)
    if found != expected:
        raise Rejected("wrong_type")
    return found


def _package(path: Path) -> Format:
    """docx or odt from a ZIP whose structure passed the check."""
    report = check_zip(path)
    if set(report.names) >= DOCX_PARTS:
        return "docx"
    if report.names and report.names[0] == "mimetype":
        head = read_member_head(path, "mimetype", MIMETYPE_MAX_BYTES)
        if head.strip() == ODT_MIMETYPE:
            return "odt"
    raise Rejected("unsupported_format")


def _compound_file(handle: BinaryIO, size: int, expected: Format) -> Format:
    """A compound file is never analysed: encrypted Office document or an old binary format."""
    try:
        names = _stream_names(handle, size)
    except (_Broken, struct.error):
        raise Rejected("damaged") from None
    if names & _ENCRYPTED_STREAMS:
        if expected == "pdf":
            raise Rejected("wrong_type")
        raise Rejected("encrypted_document")
    raise Rejected("unsupported_format")


def _read_at(handle: BinaryIO, offset: int, length: int, size: int) -> bytes:
    if offset < 0 or offset + length > size:
        raise _Broken
    handle.seek(offset)
    data = handle.read(length)
    if len(data) != length:
        raise _Broken
    return data


def _stream_names(handle: BinaryIO, size: int) -> set[str]:
    """Every stream name in the directory, following its sector chain through the FAT.

    Only the FAT sectors named in the header DIFAT are used (Findling cfb.py,
    the same named gap); a sector seen twice, a link out of the file or more
    than CFB_MAX_DIRECTORY_BYTES of directory is _Broken.
    """
    header = _read_at(handle, 0, _CFB_HEADER_BYTES, size)
    (shift,) = struct.unpack_from("<H", header, _CFB_SHIFT_AT)
    if shift not in _CFB_SHIFTS:
        raise _Broken
    sector = 1 << shift
    (fat_count,) = struct.unpack_from("<I", header, _CFB_FAT_COUNT_AT)
    (current,) = struct.unpack_from("<I", header, _CFB_FIRST_DIRECTORY_AT)
    fat_sectors = struct.unpack_from(f"<{_CFB_HEADER_DIFAT}I", header, _CFB_DIFAT_AT)[
        : min(fat_count, _CFB_HEADER_DIFAT)
    ]
    per_fat_sector = sector // 4
    names: set[str] = set()
    seen: set[int] = set()
    while current != _CFB_END_OF_CHAIN:
        if current in seen or current > _CFB_MAX_REGULAR or (len(seen) + 1) * sector > CFB_MAX_DIRECTORY_BYTES:
            raise _Broken
        seen.add(current)
        data = _read_at(handle, (current + 1) * sector, sector, size)
        for at in range(0, sector, _CFB_ENTRY_BYTES):
            entry = data[at : at + _CFB_ENTRY_BYTES]
            (length,) = struct.unpack_from("<H", entry, _CFB_NAME_LENGTH_AT)
            if entry[_CFB_TYPE_AT] == _CFB_STREAM and 2 <= length <= 64:
                names.add(entry[: length - 2].decode("utf-16-le", errors="replace"))
        index = current // per_fat_sector
        if index >= len(fat_sectors):
            raise _Broken
        fat = _read_at(handle, (fat_sectors[index] + 1) * sector, sector, size)
        (current,) = struct.unpack_from("<I", fat, (current % per_fat_sector) * 4)
    return names
