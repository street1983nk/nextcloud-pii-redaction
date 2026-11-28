"""Image inventory of the derived DOCX and ODT files and copies with 1x1 images (quick 261128-qaa).

usage: python -I soffice_diag.py <derived> <outdir>

Owner 28.11.2026: before the soffice address space cap of plan 02-24 is set,
its causes are measured. Sandbox run 46167327129 (commit 625eec7): soffice
needed VmHWM 4.41 GB for 1800107_pdf.odt (144 images, 112 pages), and
1800107_pdf.docx (144 images) ran into the 120 s wall of the product.

This script reads the folder that ci/convert_corpus.py wrote and prints, for
every file with result ok, how many images its package holds, their stored
size, their pixels and what the pixels need decoded (4 bytes each). It also
writes a copy of each 1800107 conversion in which every PNG, JPEG and GIF below
the media folder is a 1x1 image of the same format and name, every other
member byte-identical: tests/test_container_soffice_diag.py runs both through
soffice, so the memory of the decoded images is measured as a difference.

It runs in a throwaway container without network as uid 10001 (sandbox.yml),
the derived folder mounted read only. Nothing leaves RUNNER_TEMP: the copies
and manifest.json stay in <outdir>, the job log gets names and numbers only.

Lines in the job log:

    SOFFICE-DIAG-IMAGES doc=<name> format=<docx|odt> bytes= images= png= jpeg= gif= other= unreadable=
        image_bytes= pixels= decoded_bytes= largest_px=<w>x<h>
    SOFFICE-DIAG-STRIP doc=<name> source=<pdf> format= replaced= kept_other= bytes=

Standard library only (it runs with the interpreter of the image). Exit 2 for
wrong arguments, a missing or malformed manifest, a 1800107 conversion that is
missing or not ok, a named file that is absent or no package, or a copy that
cannot be made; otherwise 0.
"""

import json
import os
import struct
import sys
import zipfile
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

MANIFEST: Final = "manifest.json"
# The folder of the package that holds the images, as in ci/convert_corpus.py TARGETS.
PREFIXES: Final = {"docx": "word/media/", "odt": "Pictures/"}
# Only the conversions of this PDF get a copy with 1x1 images.
STRIP_SOURCES: Final = ("1800107.pdf",)
TINY_SUFFIX: Final = "_tiny"
BYTES_PER_PIXEL: Final = 4
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
JPEG_SOI: Final = b"\xff\xd8"
GIF_SIGNATURES: Final = (b"GIF87a", b"GIF89a")
# Markers of a JPEG frame header: SOF0 to SOF15 without DHT (C4), JPG (C8) and DAC (CC).
JPEG_SOF: Final = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# Markers without a length field: TEM, RST0 to RST7, SOI, EOI.
JPEG_STANDALONE: Final = frozenset({0x01, *range(0xD0, 0xDA)})
JPEG_SOS: Final = 0xDA


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _tiny_png() -> bytes:
    """A 1x1 RGBA PNG: IHDR (8 bit, colour type 6), one filtered scan line, IEND."""
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    scan_line = b"\x00" + b"\x80\x80\x80\xff"
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scan_line))
        + _png_chunk(b"IEND", b"")
    )


# A 1x1 baseline JPEG (one grey component, JFIF), written once with Pillow.
_TINY_JPEG: Final = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300100b0c0e0c0a100e0d0e1211101318281a181616183123251d283a333d"
    "3c3933383740485c4e404457453738506d51575f626768673e4d71797064785c656763ffc0000b080001000101011100ffc4001f0000"
    "010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d010203000411"
    "05122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445"
    "464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9"
    "aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda00080101"
    "00003f002bffd9"
)
# The common 1x1 GIF: one transparent pixel.
_TINY_GIF: Final = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)
TINY: Final = {"png": _tiny_png(), "jpeg": _TINY_JPEG, "gif": _TINY_GIF}


class DiagError(Exception):
    """A package that cannot be read or copied, or a derived folder that cannot be used."""


@dataclass(frozen=True, slots=True)
class Inventory:
    name: str
    format: str
    bytes: int
    images: int
    png: int
    jpeg: int
    gif: int
    other: int
    unreadable: int
    image_bytes: int
    pixels: int
    decoded_bytes: int
    largest_w: int
    largest_h: int


@dataclass(frozen=True, slots=True)
class Stripped:
    name: str
    source: str
    format: str
    replaced: int
    kept_other: int
    bytes: int


def sniff(data: bytes) -> str:
    """png, jpeg, gif by the magic bytes, else other."""
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data.startswith(JPEG_SOI):
        return "jpeg"
    if data.startswith(GIF_SIGNATURES):
        return "gif"
    return "other"


def _sized(width: int, height: int) -> tuple[int, int] | None:
    return (width, height) if width > 0 and height > 0 else None


def _png_size(data: bytes) -> tuple[int, int] | None:
    # Signature (8), chunk length (4), IHDR (4), width (4), height (4).
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return _sized(width, height)


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(JPEG_SOI):
        return None
    position = 2
    while position < len(data):
        if data[position] != 0xFF:
            return None
        # Fill bytes: any number of 0xFF in front of a marker.
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return None
        marker = data[position]
        position += 1
        if marker in JPEG_STANDALONE:
            if marker == 0xD9:
                return None
            continue
        if position + 2 > len(data):
            return None
        (length,) = struct.unpack(">H", data[position : position + 2])
        if length < 2 or position + length > len(data):
            return None
        if marker in JPEG_SOF:
            # Length (2), precision (1), height (2), width (2).
            if length < 7:
                return None
            height, width = struct.unpack(">HH", data[position + 3 : position + 7])
            return _sized(width, height)
        if marker == JPEG_SOS:
            return None
        position += length
    return None


def _gif_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or not data.startswith(GIF_SIGNATURES):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return _sized(width, height)


def dimensions(data: bytes) -> tuple[int, int] | None:
    """Width and height from the header of a PNG, JPEG or GIF; None for anything else, never an exception."""
    kind = sniff(data)
    if kind == "png":
        return _png_size(data)
    if kind == "jpeg":
        return _jpeg_size(data)
    if kind == "gif":
        return _gif_size(data)
    return None


def _image_members(archive: zipfile.ZipFile, prefix: str) -> list[zipfile.ZipInfo]:
    return [info for info in archive.infolist() if info.filename.startswith(prefix) and not info.is_dir()]


def inventory(path: Path, prefix: str) -> Inventory:
    """Count, size and pixels of every member below prefix."""
    counts = {"png": 0, "jpeg": 0, "gif": 0, "other": 0}
    unreadable = image_bytes = pixels = 0
    largest = (0, 0)
    try:
        with zipfile.ZipFile(path) as archive:
            members = _image_members(archive, prefix)
            for info in members:
                data = archive.read(info)
                image_bytes += info.file_size
                kind = sniff(data)
                counts[kind] += 1
                if kind == "other":
                    continue
                size = dimensions(data)
                if size is None:
                    unreadable += 1
                    continue
                pixels += size[0] * size[1]
                if size[0] * size[1] > largest[0] * largest[1]:
                    largest = size
    except (OSError, zipfile.BadZipFile, zlib.error, EOFError) as exc:
        msg = f"{path.name} is no readable package"
        raise DiagError(msg) from exc
    return Inventory(
        name=path.name,
        format=path.suffix.removeprefix("."),
        bytes=path.stat().st_size,
        images=len(members),
        png=counts["png"],
        jpeg=counts["jpeg"],
        gif=counts["gif"],
        other=counts["other"],
        unreadable=unreadable,
        image_bytes=image_bytes,
        pixels=pixels,
        decoded_bytes=pixels * BYTES_PER_PIXEL,
        largest_w=largest[0],
        largest_h=largest[1],
    )


def strip(src: Path, dst: Path, prefix: str) -> tuple[int, int]:
    """Copy src to dst (a new file) with every PNG, JPEG and GIF below prefix as a 1x1 image; (replaced, kept_other).

    Every member keeps its place, name, date, compression and attributes; all
    others stay byte-identical after decompression. A package without such an
    image, one that is no zip, or an existing dst is a DiagError.
    """
    try:
        with zipfile.ZipFile(src) as source:
            infos = source.infolist()
            kinds = {info.filename: sniff(source.read(info)) for info in _image_members(source, prefix)}
            if not any(kind in TINY for kind in kinds.values()):
                msg = f"{src.name} has no PNG, JPEG or GIF below {prefix}"
                raise DiagError(msg)
            try:
                handle = dst.open("xb")
            except FileExistsError:
                msg = f"{dst.name} exists already"
                raise DiagError(msg) from None
            replaced = kept_other = 0
            with handle, zipfile.ZipFile(handle, "w") as target:
                for info in infos:
                    kind = kinds.get(info.filename)
                    if kind in TINY:
                        data = TINY[kind]
                        replaced += 1
                    else:
                        data = source.read(info)
                        kept_other += kind is not None
                    target.writestr(info, data)
    except (OSError, zipfile.BadZipFile, zlib.error, EOFError) as exc:
        msg = f"{src.name} cannot be copied"
        raise DiagError(msg) from exc
    return replaced, kept_other


def tiny_name(derived_name: str) -> str:
    """1800107_pdf.odt: 1800107_pdf_tiny.odt."""
    stem, _, fmt = derived_name.rpartition(".")
    return f"{stem}{TINY_SUFFIX}.{fmt}"


def ok_entries(derived: Path) -> list[dict[str, str]]:
    """The entries with result ok of <derived>/manifest.json; DiagError when it is unusable."""
    try:
        files = json.loads((derived / MANIFEST).read_text(encoding="utf-8"))["files"]
        entries = [
            {"name": entry["name"], "source": entry["source"], "format": entry["format"]}
            for entry in files
            if entry["result"] == "ok"
        ]
    except (OSError, ValueError, KeyError, TypeError):
        msg = f"the derived folder has no usable {MANIFEST}"
        raise DiagError(msg) from None
    for entry in entries:
        if not all(isinstance(value, str) for value in entry.values()):
            msg = f"{MANIFEST} has an entry that is not names only"
            raise DiagError(msg)
        if "/" in entry["name"] or "\\" in entry["name"] or entry["format"] not in PREFIXES:
            msg = f"{MANIFEST} names a file that is no DOCX or ODT of this folder"
            raise DiagError(msg)
    for source in STRIP_SOURCES:
        for fmt in PREFIXES:
            if not any(entry["source"] == source and entry["format"] == fmt for entry in entries):
                msg = f"the {fmt} conversion of {source} is missing or not ok"
                raise DiagError(msg)
    for entry in entries:
        if not (derived / entry["name"]).is_file():
            msg = f"{entry['name']} is named in {MANIFEST} but absent"
            raise DiagError(msg)
    return entries


def images_line(entry: Inventory) -> str:
    return (
        f"SOFFICE-DIAG-IMAGES doc={entry.name} format={entry.format} bytes={entry.bytes} images={entry.images} "
        f"png={entry.png} jpeg={entry.jpeg} gif={entry.gif} other={entry.other} unreadable={entry.unreadable} "
        f"image_bytes={entry.image_bytes} pixels={entry.pixels} decoded_bytes={entry.decoded_bytes} "
        f"largest_px={entry.largest_w}x{entry.largest_h}"
    )


def strip_line(entry: Stripped) -> str:
    return (
        f"SOFFICE-DIAG-STRIP doc={entry.name} source={entry.source} format={entry.format} "
        f"replaced={entry.replaced} kept_other={entry.kept_other} bytes={entry.bytes}"
    )


def run(derived: Path, outdir: Path) -> None:
    entries = ok_entries(derived)
    found = [inventory(derived / entry["name"], PREFIXES[entry["format"]]) for entry in entries]
    for entry in found:
        print(images_line(entry))
    outdir.mkdir(parents=True, exist_ok=True)
    stripped: list[Stripped] = []
    for entry in entries:
        if entry["source"] not in STRIP_SOURCES:
            continue
        prefix = PREFIXES[entry["format"]]
        target = outdir / tiny_name(entry["name"])
        replaced, kept_other = strip(derived / entry["name"], target, prefix)
        stripped.append(
            Stripped(target.name, entry["source"], entry["format"], replaced, kept_other, target.stat().st_size)
        )
        tiny = inventory(target, prefix)
        found.append(tiny)
        print(images_line(tiny))
    for entry in stripped:
        print(strip_line(entry))
    temporary = outdir / f"{MANIFEST}.tmp"
    payload = {"inventory": [asdict(entry) for entry in found], "stripped": [asdict(entry) for entry in stripped]}
    temporary.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    os.replace(temporary, outdir / MANIFEST)
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -I soffice_diag.py <derived> <outdir>\n")
        return 2
    try:
        run(Path(argv[0]), Path(argv[1]))
    except DiagError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
