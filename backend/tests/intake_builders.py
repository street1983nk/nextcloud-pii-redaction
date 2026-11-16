"""Builders for pre-check test files: ZIP packages and compound files, made in tmp_path, never committed."""

import struct
import zipfile
from pathlib import Path

ODT_MIMETYPE = b"application/vnd.oasis.opendocument.text"
CONTENT_TYPES = b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
DOCUMENT_XML = b'<?xml version="1.0"?><w:document xmlns:w="urn:w"><w:body/></w:document>'


def write_zip(path: Path, members: list[tuple[str, bytes]], *, compression: int = zipfile.ZIP_DEFLATED) -> Path:
    """A ZIP with these members in this order (duplicate names allowed, zipfile only warns)."""
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in members:
            info = zipfile.ZipInfo(name)
            info.compress_type = compression
            archive.writestr(info, data)
    return path


def docx(path: Path, extra: list[tuple[str, bytes]] | None = None) -> Path:
    return write_zip(path, [("[Content_Types].xml", CONTENT_TYPES), ("word/document.xml", DOCUMENT_XML), *(extra or [])])


def odt(path: Path, manifest: bytes = b"<manifest:manifest/>") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), ODT_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("content.xml", b"<office:document-content/>", compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("META-INF/manifest.xml", manifest, compress_type=zipfile.ZIP_DEFLATED)
    return path


def _central_entries(data: bytes) -> list[int]:
    """Offsets of every central directory header (PK\\x01\\x02)."""
    offsets = []
    at = data.find(b"PK\x01\x02")
    while at >= 0:
        offsets.append(at)
        at = data.find(b"PK\x01\x02", at + 1)
    return offsets


def patch_central(path: Path, index: int, *, file_size: int | None = None, compress_size: int | None = None,
                  flags: int | None = None, header_offset: int | None = None) -> None:  # fmt: skip
    """Rewrite declared fields of one central directory header in place."""
    data = bytearray(path.read_bytes())
    at = _central_entries(bytes(data))[index]
    if flags is not None:
        struct.pack_into("<H", data, at + 8, flags)
    if compress_size is not None:
        struct.pack_into("<I", data, at + 20, compress_size)
    if file_size is not None:
        struct.pack_into("<I", data, at + 24, file_size)
    if header_offset is not None:
        struct.pack_into("<I", data, at + 42, header_offset)
    path.write_bytes(bytes(data))


def header_offset_of(path: Path, index: int) -> int:
    data = path.read_bytes()
    at = _central_entries(data)[index]
    return struct.unpack_from("<I", data, at + 42)[0]


# Compound file ([MS-CFB] 2.2 header, 2.6 directory entry), version 3, 512 byte sectors.
_FREE = 0xFFFFFFFF
_END = 0xFFFFFFFE
_FATSECT = 0xFFFFFFFD
_NOSTREAM = 0xFFFFFFFF


def _entry(name: str, kind: int, child: int = _NOSTREAM, right: int = _NOSTREAM) -> bytes:
    encoded = (name + "\x00").encode("utf-16-le")
    field = encoded.ljust(64, b"\x00")
    rest = struct.pack("<HBBIII", len(encoded), kind, 1, _NOSTREAM, right, child)
    return (field + rest).ljust(128, b"\x00")


def compound_file(path: Path, streams: list[str]) -> Path:
    """A compound file whose directory lists these streams below the root; spans sectors as needed."""
    entries = [_entry("Root Entry", 5, child=1 if streams else _NOSTREAM)]
    for number, name in enumerate(streams, start=1):
        right = number + 1 if number < len(streams) else _NOSTREAM
        entries.append(_entry(name, 2, right=right))
    directory = b"".join(entries)
    directory += b"\x00" * (-len(directory) % 512)
    directory_sectors = len(directory) // 512
    fat = [_FATSECT]
    for number in range(directory_sectors):
        fat.append(number + 2 if number + 1 < directory_sectors else _END)
    fat += [_FREE] * (128 - len(fat))
    header = bytearray(512)
    header[0:8] = bytes.fromhex("d0cf11e0a1b11ae1")
    struct.pack_into("<HHHHH", header, 0x18, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<I", header, 0x2C, 1)  # one FAT sector
    struct.pack_into("<I", header, 0x30, 1)  # directory starts at sector 1
    struct.pack_into("<I", header, 0x38, 4096)
    struct.pack_into("<IIII", header, 0x3C, _END, 0, _END, 0)
    difat = [0] + [_FREE] * 108
    struct.pack_into("<109I", header, 0x4C, *difat)
    path.write_bytes(bytes(header) + struct.pack("<128I", *fat) + directory)
    return path
