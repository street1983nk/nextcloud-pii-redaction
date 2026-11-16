"""Stage B of the pre-check for ZIP packages (DOCX, ODT): structure before content (SAFE-02).

The central directory is located and counted by this module, exactly as
CPython's zipfile would read it, before a single ZipInfo is built: a directory
with ten million entries costs a count, not ten million objects. Only then
does ZipFile open the file, and only the declarations are judged: sizes,
ratios, names, flags, offsets. No member is unpacked; the one read is the
ODF manifest, streamed under a byte cap, to find its encryption marker.

Copied, not imported, from Findling 1.6.5 (backend/src/findling/extract/
archive.py, commit 24c04abd): _is_traversal (lines 177-189),
count_central_directory (289-315), _central_directory (339-347), _end_record
(350-370), _end_record64 (373-408), _Window (411-444), the record constants
(105-141) and the two step ratio judgement of _judge_ratios (470-482). The
Findling exceptions map onto the verdicts here: CorruptDirectory is damaged,
an over limit without signature is too_large, with signature unsafe_content.

Added for this app (RESEARCH Pitfall 4, T-02-09): two names that end up as the
same part after normalisation (backslash to slash, "." segments and empty
segments dropped, Unicode NFC, casefold) are refused, because the preview and
the redaction could read different parts under one name. Data in front of
the first local header, two directory entries sharing or overlapping local
data, a name longer than ZIP_MAX_NAME_BYTES and the ZIP encryption bit are
refused as well.
"""

import re
import struct
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final
from zipfile import BadZipFile, ZipFile, ZipInfo

from .limits import (
    XML_MAX_PART_BYTES,
    ZIP_MALICIOUS_RATIO,
    ZIP_MAX_CENTRAL_DIRECTORY_BYTES,
    ZIP_MAX_ENTRIES,
    ZIP_MAX_MEMBER_BYTES,
    ZIP_MAX_NAME_BYTES,
    ZIP_MAX_RATIO,
    ZIP_MAX_TOTAL_BYTES,
    ZIP_RATIO_MIN_BYTES,
)
from .verdict import Rejected

# PKWARE APPNOTE 6.3.10: end of central directory record (4.3.16, 22 bytes plus
# a comment of at most 65 535), ZIP64 end record (4.3.14, 56 bytes fixed) and
# its locator (4.3.15, 20 bytes, directly in front of the end record), central
# directory header (4.3.12, 46 bytes fixed, then name, extra field, comment),
# local file header (4.3.7, 30 bytes fixed, then name and extra field).
_END = b"PK\x05\x06"
_END64 = b"PK\x06\x06"
_LOCATOR64 = b"PK\x06\x07"
_CENTRAL = b"PK\x01\x02"
_LOCAL = b"PK\x03\x04"
_END_SIZE = 22
_END64_SIZE = 56
_LOCATOR64_SIZE = 20
_CENTRAL_SIZE = 46
_LOCAL_SIZE = 30
_COMMENT_MAX = 0xFFFF

# The block the directory is read in while it is counted.
_READ_BLOCK = 64 * 1024
_ENCRYPTED_FLAG: Final = 0x1

# A drive letter in front of a raw member name; the separators of both worlds.
_DRIVE: Final = re.compile(r"[A-Za-z]:")
_SEPARATORS: Final = re.compile(r"[/\\]")

MANIFEST: Final = "META-INF/manifest.xml"
# The element an encrypted ODF package carries per encrypted file
# (ODF 1.3 part 2, 3.8.3). Matched without its prefix, which a writer may choose.
_ENCRYPTION_MARK: Final = b"encryption-data"

# What zipfile raises on a broken directory or a member it cannot read.
_UNREADABLE: Final = (BadZipFile, NotImplementedError, UnicodeDecodeError, ValueError, EOFError, zlib.error, OSError)


class CorruptDirectory(Exception):
    """The end record or the central directory is not what zipfile could read."""


class _OverLimit(Exception):
    """The directory is longer than ZIP_MAX_CENTRAL_DIRECTORY_BYTES."""


@dataclass(frozen=True, slots=True)
class ZipReport:
    """What the check saw: the number of entries and their names in directory order."""

    entries: int
    names: tuple[str, ...]


def _is_traversal(raw_name: str) -> bool:
    """True for a raw member name that climbs out of the folder it would be unpacked to (Findling).

    A ``..`` segment between ``/`` or ``\\``, a separator or a drive letter in
    front, or a NUL anywhere. Dots that are no segment of their own
    (``..x.txt``, ``a..b``) are names like any other.
    """
    if "\x00" in raw_name or raw_name.startswith(("/", "\\")) or _DRIVE.match(raw_name):
        return True
    return ".." in _SEPARATORS.split(raw_name)


def normalized_name(raw_name: str) -> str:
    """The key two names collide under: slashes, no "." or empty segments, NFC, casefold."""
    segments = [part for part in raw_name.replace("\\", "/").split("/") if part not in ("", ".")]
    return unicodedata.normalize("NFC", "/".join(segments)).casefold()


def count_central_directory(handle: BinaryIO, size: int, *, limit: int) -> int:
    """The number of headers zipfile would read from this directory, at most ``limit + 1`` (Findling).

    Located and walked exactly like CPython 3.13 does it, so the number is what
    ``len(ZipFile(path).infolist())`` would be without building a single
    ZipInfo. Raises CorruptDirectory where zipfile would raise BadZipFile.
    """
    start, length = _central_directory(handle, size)
    if length > ZIP_MAX_CENTRAL_DIRECTORY_BYTES:
        raise _OverLimit
    window = _Window(handle, start, min(length, max(size - start, 0)))
    total = 0
    count = 0
    # zipfile, _RealGetContents: "while total < size_cd", one 46 byte header with
    # its signature, then name, extra field and comment by their declared lengths.
    while total < length:
        header = window.take(_CENTRAL_SIZE)
        if len(header) != _CENTRAL_SIZE or header[:4] != _CENTRAL:
            raise CorruptDirectory
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", header, 28)
        window.skip(name_len + extra_len + comment_len)
        total += _CENTRAL_SIZE + name_len + extra_len + comment_len
        count += 1
        if count > limit:
            break
    return count


def _central_directory(handle: BinaryIO, size: int) -> tuple[int, int]:
    """Start and byte length of the central directory, as zipfile computes them."""
    location, length, offset = _end_record(handle, size)
    # _RealGetContents: concat = location - size_cd - offset_cd, and the
    # directory starts at offset_cd + concat, which is location - size_cd.
    start = offset + (location - length - offset)
    if start < 0:
        raise CorruptDirectory
    return start, length


def _concatenated(handle: BinaryIO, size: int) -> int:
    """Bytes zipfile would assume in front of the archive (its "concat"); 0 for a clean file."""
    location, length, offset = _end_record(handle, size)
    return location - length - offset


def _end_record(handle: BinaryIO, size: int) -> tuple[int, int, int]:
    """Location of the end record, directory length and offset; zipfile's _EndRecData."""
    if size < _END_SIZE:
        raise CorruptDirectory
    handle.seek(size - _END_SIZE)
    data = handle.read(_END_SIZE)
    if len(data) == _END_SIZE and data[:4] == _END and data[-2:] == b"\x00\x00":
        location = size - _END_SIZE
    else:
        earliest = max(size - _COMMENT_MAX - _END_SIZE, 0)
        handle.seek(earliest)
        tail = handle.read(_COMMENT_MAX + _END_SIZE)
        found = tail.rfind(_END)
        if found < 0:
            raise CorruptDirectory
        data = tail[found : found + _END_SIZE]
        if len(data) != _END_SIZE:
            raise CorruptDirectory
        location = earliest + found
    length, offset = struct.unpack_from("<II", data, 12)
    return _end_record64(handle, location, length, offset)


def _end_record64(handle: BinaryIO, location: int, length: int, offset: int) -> tuple[int, int, int]:
    """zipfile's _EndRecData64: a locator in front of the end record overrides it, whatever its fields say."""
    at = location - _LOCATOR64_SIZE
    if at < 0:
        return location, length, offset
    handle.seek(at)
    data = handle.read(_LOCATOR64_SIZE)
    if len(data) != _LOCATOR64_SIZE:
        raise CorruptDirectory
    signature, disk, relative, disks = struct.unpack("<4sLQL", data)
    if signature != _LOCATOR64:
        return location, length, offset
    if disk != 0 or disks > 1:
        raise CorruptDirectory
    at -= _END64_SIZE
    if relative > at:
        raise CorruptDirectory
    handle.seek(relative)
    extra = at - relative
    record = handle.read(_END64_SIZE)
    if len(record) != _END64_SIZE:
        raise CorruptDirectory
    if not record.startswith(_END64) and relative != at:
        # Data in front of the ZIP file: zipfile assumes no extensible data sector.
        handle.seek(at)
        extra = 0
        record = handle.read(_END64_SIZE)
        if len(record) != _END64_SIZE:
            raise CorruptDirectory
    if not record.startswith(_END64):
        raise CorruptDirectory
    record_size = struct.unpack_from("<Q", record, 4)[0]
    length64, offset64 = struct.unpack_from("<QQ", record, 40)
    if offset64 + length64 != relative or record_size + 12 != _END64_SIZE + extra:
        raise CorruptDirectory
    return at - extra, length64, offset64


class _Window:
    """A bounded region of the file, read in blocks; reads past its end come back short, like BytesIO."""

    def __init__(self, handle: BinaryIO, start: int, length: int) -> None:
        handle.seek(start)
        self._handle = handle
        self._left = length
        self._buffer = b""
        self._at = 0

    def take(self, count: int) -> bytes:
        while len(self._buffer) - self._at < count and self._left > 0:
            block = self._handle.read(min(_READ_BLOCK, self._left))
            if not block:
                self._left = 0
                break
            self._left -= len(block)
            self._buffer = self._buffer[self._at :] + block
            self._at = 0
        piece = self._buffer[self._at : self._at + count]
        self._at += len(piece)
        return piece

    def skip(self, count: int) -> None:
        buffered = len(self._buffer) - self._at
        if count <= buffered:
            self._at += count
            return
        count -= buffered
        self._buffer = b""
        self._at = 0
        jump = min(count, self._left)
        self._handle.seek(jump, 1)
        self._left -= jump


def _judge_ratios(members: list[ZipInfo]) -> None:
    """The ratio of every member from ZIP_RATIO_MIN_BYTES on, in two steps (Findling).

    The signature is looked for in all members first, so a member over the
    attack ratio is named even behind one that is merely over the limit.
    """
    judged = [(info.file_size, max(info.compress_size, 1)) for info in members if info.file_size >= ZIP_RATIO_MIN_BYTES]
    if any(size > ZIP_MALICIOUS_RATIO * packed for size, packed in judged):
        raise Rejected("unsafe_content")
    if any(size > ZIP_MAX_RATIO * packed for size, packed in judged):
        raise Rejected("too_large")


def _judge_names(members: list[ZipInfo]) -> None:
    seen: set[str] = set()
    for info in members:
        raw = info.orig_filename
        if _is_traversal(raw) or len(raw.encode("utf-8", errors="surrogateescape")) > ZIP_MAX_NAME_BYTES:
            raise Rejected("unsafe_content")
        key = normalized_name(raw)
        if key in seen:
            raise Rejected("unsafe_content")
        seen.add(key)


def _judge_layout(handle: BinaryIO, members: list[ZipInfo], directory_start: int) -> None:
    """Local data starts at offset 0, and no two members share or overlap their bytes."""
    ordered = sorted(members, key=lambda info: info.header_offset)
    if ordered and ordered[0].header_offset != 0:
        raise Rejected("unsafe_content")
    end = 0
    for info in ordered:
        if info.header_offset < end:
            raise Rejected("unsafe_content")
        handle.seek(info.header_offset)
        local = handle.read(_LOCAL_SIZE)
        if len(local) != _LOCAL_SIZE or local[:4] != _LOCAL:
            raise Rejected("damaged")
        name_len, extra_len = struct.unpack_from("<HH", local, 26)
        end = info.header_offset + _LOCAL_SIZE + name_len + extra_len + info.compress_size
    if end > directory_start:
        raise Rejected("unsafe_content")


def _manifest_is_encrypted(archive: ZipFile, info: ZipInfo) -> bool:
    """Stream the ODF manifest under XML_MAX_PART_BYTES and look for the encryption marker."""
    tail = b""
    read = 0
    with archive.open(info) as stream:
        while block := stream.read(_READ_BLOCK):
            read += len(block)
            if read > XML_MAX_PART_BYTES:
                raise Rejected("too_large")
            if _ENCRYPTION_MARK in tail + block:
                return True
            tail = block[-len(_ENCRYPTION_MARK) :]
    return False


def check_zip(path: Path) -> ZipReport:
    """Judge the structure of a ZIP package; returns what it saw or raises Rejected."""
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        handle.seek(0)
        if handle.read(4) != _LOCAL:
            raise Rejected("unsafe_content")
        try:
            directory_start, _ = _central_directory(handle, size)
            count = count_central_directory(handle, size, limit=ZIP_MAX_ENTRIES)
            concat = _concatenated(handle, size)
        except CorruptDirectory:
            raise Rejected("damaged") from None
        except _OverLimit:
            raise Rejected("too_large") from None
        if count > ZIP_MAX_ENTRIES:
            raise Rejected("too_large")
        if concat != 0:
            raise Rejected("unsafe_content")
        try:
            with ZipFile(path) as archive:
                members = archive.infolist()
                if len(members) != count:
                    raise Rejected("damaged")
                if sum(info.file_size for info in members) > ZIP_MAX_TOTAL_BYTES or any(
                    info.file_size > ZIP_MAX_MEMBER_BYTES for info in members
                ):
                    raise Rejected("too_large")
                _judge_ratios(members)
                _judge_names(members)
                _judge_layout(handle, members, directory_start)
                if any(info.flag_bits & _ENCRYPTED_FLAG for info in members):
                    raise Rejected("encrypted_document")
                manifest = next((info for info in members if info.orig_filename == MANIFEST), None)
                if manifest is not None and _manifest_is_encrypted(archive, manifest):
                    raise Rejected("encrypted_document")
        except _UNREADABLE:
            raise Rejected("damaged") from None
    return ZipReport(entries=count, names=tuple(info.orig_filename for info in members))


def read_member_head(path: Path, name: str, limit: int) -> bytes:
    """The first ``limit`` bytes of one member, for a package that passed check_zip."""
    try:
        with ZipFile(path) as archive, archive.open(name) as stream:
            return stream.read(limit)
    except (*_UNREADABLE, KeyError):
        raise Rejected("damaged") from None
