"""ci/soffice_diag.py: image inventory of the derived packages and the tiny copies (quick 261128-qaa).

Owner 28.11.2026: before the soffice address space cap is set, its causes are
measured. The script counts and sizes the images of every DOCX and ODT that
ci/convert_corpus.py made and writes copies of the 1800107 conversions whose
images are 1x1 pictures of the same format. These tests build every test image
with pymupdf and decode the 1x1 constants of the script with pymupdf, so the
check never uses the parser of the script itself (rule "Gegenprobe nie mit dem
Muster der Umsetzung"). Packages are built in memory with zipfile.
"""

import io
import json
import re
import struct
import zipfile
from pathlib import Path
from types import ModuleType

import pymupdf
import pytest

from tests.conftest import ci_module


def sd() -> ModuleType:
    return ci_module("soffice_diag")


def cc() -> ModuleType:
    return ci_module("convert_corpus")


def _pixmap(width: int, height: int) -> pymupdf.Pixmap:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pixmap.set_rect(pixmap.irect, (200, 30, 90))
    return pixmap


def png(width: int, height: int) -> bytes:
    return _pixmap(width, height).tobytes("png")


def jpeg(width: int, height: int) -> bytes:
    return _pixmap(width, height).tobytes("jpg")


def gif(width: int, height: int) -> bytes:
    """A 13 byte GIF header (signature, logical screen size, flags) and the trailer."""
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00" + b"\x3b"


def _package(members: list[tuple[str, bytes, int]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index, (name, data, method) in enumerate(members):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 28, 10, index, 2 * index))
            info.compress_type = method
            archive.writestr(info, data)
    return buffer.getvalue()


STORED, DEFLATED = zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED


# -- 1, 2: header parsing ------------------------------------------------------------------


def test_dimensions_of_png_jpeg_and_gif() -> None:
    assert sd().dimensions(png(3, 2)) == (3, 2)
    baseline = jpeg(30, 17)
    assert sd().dimensions(baseline) == (30, 17)
    # An APP1 segment (Exif) in front of the frame header.
    app1 = b"\xff\xe1" + struct.pack(">H", 2 + 10) + b"Exif\x00\x00abcd"
    assert sd().dimensions(baseline[:2] + app1 + baseline[2:]) == (30, 17)
    # The same frame header marked progressive (SOF2).
    assert baseline.count(b"\xff\xc0") == 1
    assert sd().dimensions(baseline.replace(b"\xff\xc0", b"\xff\xc2")) == (30, 17)
    assert sd().dimensions(gif(5, 7)) == (5, 7)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        png(3, 2)[:20],
        b"\x88" + png(3, 2)[1:],
        b"\xff\xd8\xff\xd9",
        b"\xff\xd8\xff\xe0\x00\x40abcd",
        b"just some plain text, not an image",
    ],
    ids=["empty", "png_cut", "png_signature", "soi_eoi", "segment_past_end", "text"],
)
def test_negative_dimensions_of_broken_data_is_none(data: bytes) -> None:
    assert sd().dimensions(data) is None


def test_sniff_names_the_format() -> None:
    assert sd().sniff(png(2, 2)) == "png"
    assert sd().sniff(jpeg(2, 2)) == "jpeg"
    assert sd().sniff(gif(2, 2)) == "gif"
    assert sd().sniff(b"\x01\x00\x00\x00 emf") == "other"
    assert sd().sniff(b"") == "other"


# -- 3: the 1x1 images ---------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["png", "jpeg", "gif"])
def test_every_tiny_image_is_one_by_one_for_an_independent_decoder(fmt: str) -> None:
    data = sd().TINY[fmt]
    decoded = pymupdf.Pixmap(data)
    assert (decoded.width, decoded.height) == (1, 1)
    assert sd().sniff(data) == fmt
    assert sd().dimensions(data) == (1, 1)


# -- 4: the inventory ----------------------------------------------------------------------


def test_inventory_counts_sizes_and_pixels_below_the_prefix(tmp_path: Path) -> None:
    images = [
        ("word/media/image1.png", png(10, 20)),
        ("word/media/image2.png", png(30, 40)),
        ("word/media/image3.jpeg", jpeg(8, 8)),
        ("word/media/image4.emf", b"\x01\x00\x00\x00 not an image format we read"),
    ]
    members = [("word/document.xml", b"<w:document/>", DEFLATED)]
    members += [(name, data, DEFLATED) for name, data in images]
    members.append(("docProps/thumbnail.png", png(50, 50), DEFLATED))
    path = tmp_path / "sample_pdf.docx"
    path.write_bytes(_package(members))
    found = sd().inventory(path, "word/media/")
    assert found.name == "sample_pdf.docx"
    assert found.format == "docx"
    assert found.bytes == path.stat().st_size
    assert (found.images, found.png, found.jpeg, found.gif, found.other, found.unreadable) == (4, 2, 1, 0, 1, 0)
    assert found.image_bytes == sum(len(data) for _, data in images)
    assert found.pixels == 200 + 1200 + 64
    assert found.decoded_bytes == found.pixels * 4
    assert (found.largest_w, found.largest_h) == (30, 40)


def test_negative_a_truncated_png_counts_as_png_and_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "cut_pdf.odt"
    whole = png(6, 6)
    path.write_bytes(_package([("Pictures/whole.png", whole, STORED), ("Pictures/cut.png", png(9, 9)[:20], STORED)]))
    found = sd().inventory(path, "Pictures/")
    assert (found.images, found.png, found.unreadable) == (2, 2, 1)
    assert found.pixels == 36
    assert (found.largest_w, found.largest_h) == (6, 6)


# -- 5, 6: the tiny copies -----------------------------------------------------------------


def _odt_members() -> list[tuple[str, bytes, int]]:
    return [
        ("mimetype", b"application/vnd.oasis.opendocument.text", STORED),
        ("content.xml", b"<office:document-content>" + b"x" * 500 + b"</office:document-content>", DEFLATED),
        ("META-INF/manifest.xml", b"<manifest:manifest/>", DEFLATED),
        ("Pictures/a.png", png(40, 30), STORED),
        ("Pictures/b.jpg", jpeg(25, 25), DEFLATED),
        ("Pictures/c.svm", b"VCLMTF svm vector data", DEFLATED),
    ]


def _docx_members() -> list[tuple[str, bytes, int]]:
    return [
        ("[Content_Types].xml", b"<Types/>", DEFLATED),
        ("word/document.xml", b"<w:document>" + b"y" * 300 + b"</w:document>", DEFLATED),
        ("word/media/image1.png", png(64, 64), DEFLATED),
        ("word/media/image2.jpeg", jpeg(33, 11), DEFLATED),
        ("word/media/image3.emf", b"\x01\x00\x00\x00 emf", DEFLATED),
    ]


@pytest.mark.parametrize(
    ("members", "prefix", "suffix"),
    [(_odt_members(), "Pictures/", "odt"), (_docx_members(), "word/media/", "docx")],
    ids=["odt", "docx"],
)
def test_strip_keeps_every_other_member_byte_identical(
    tmp_path: Path, members: list[tuple[str, bytes, int]], prefix: str, suffix: str
) -> None:
    src, dst = tmp_path / f"doc.{suffix}", tmp_path / f"doc_tiny.{suffix}"
    src.write_bytes(_package(members))
    replaced, kept_other = sd().strip(src, dst, prefix)
    assert (replaced, kept_other) == (2, 1)
    with zipfile.ZipFile(src) as before, zipfile.ZipFile(dst) as after:
        assert after.namelist() == before.namelist()
        assert after.testzip() is None
        for old, new in zip(before.infolist(), after.infolist(), strict=True):
            assert new.filename == old.filename
            assert new.compress_type == old.compress_type
            assert new.date_time == old.date_time
            data = after.read(new)
            if new.filename.startswith(prefix) and new.filename.rsplit(".", 1)[-1] in {"png", "jpg", "jpeg"}:
                fmt = "png" if new.filename.endswith(".png") else "jpeg"
                assert data == sd().TINY[fmt], new.filename
                decoded = pymupdf.Pixmap(data)
                assert (decoded.width, decoded.height) == (1, 1)
            else:
                assert data == before.read(old), new.filename
        if suffix == "odt":
            first = after.infolist()[0]
            assert first.filename == "mimetype"
            assert first.compress_type == STORED


def test_negative_strip_refuses_what_it_cannot_copy(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "plain_pdf.odt"
    not_a_zip.write_bytes(b"this is no zip at all")
    with pytest.raises(sd().DiagError):
        sd().strip(not_a_zip, tmp_path / "a_tiny.odt", "Pictures/")
    assert not (tmp_path / "a_tiny.odt").exists()
    no_images = tmp_path / "text_pdf.odt"
    no_images.write_bytes(_package([("mimetype", b"x", STORED), ("Pictures/c.svm", b"svm", STORED)]))
    with pytest.raises(sd().DiagError):
        sd().strip(no_images, tmp_path / "b_tiny.odt", "Pictures/")
    source = tmp_path / "doc_pdf.odt"
    source.write_bytes(_package(_odt_members()))
    existing = tmp_path / "doc_tiny.odt"
    existing.write_bytes(b"already here")
    with pytest.raises(sd().DiagError):
        sd().strip(source, existing, "Pictures/")
    assert existing.read_bytes() == b"already here"


# -- 7: the constants ----------------------------------------------------------------------


def test_the_prefixes_are_those_of_convert_corpus_and_only_1800107_is_stripped() -> None:
    assert {fmt: prefix for fmt, _export, prefix in cc().TARGETS} == sd().PREFIXES
    assert sd().STRIP_SOURCES == ("1800107.pdf",)


# -- 8: main -------------------------------------------------------------------------------


def _derived(root: Path, entries: list[dict[str, object]] | None = None, *, write: bool = True) -> Path:
    """A derived folder like ci/convert_corpus.py writes it."""
    root.mkdir()
    packages = {
        "1800107_pdf.docx": _package(_docx_members()),
        "1800107_pdf.odt": _package(_odt_members()),
        "1913500_pdf.odt": _package([("mimetype", b"x", STORED), ("Pictures/p.png", png(12, 5), STORED)]),
    }
    if entries is None:
        entries = [
            {"name": name, "source": name.split("_pdf.")[0] + ".pdf", "format": name.rsplit(".", 1)[1]}
            | {"result": "ok", "bytes": len(data), "images": 2, "ms": 1000}
            for name, data in packages.items()
        ]
        entries.append(
            {"name": "1913500_pdf.docx", "source": "1913500.pdf", "format": "docx", "result": "timeout"}
            | {"bytes": 0, "images": 0, "ms": 1800000}
        )
    if write:
        for name, data in packages.items():
            (root / name).write_bytes(data)
    (root / "manifest.json").write_text(json.dumps({"files": entries}), encoding="utf-8")
    return root


def test_positive_main_inventories_every_ok_file_and_makes_both_tiny_copies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    derived = _derived(tmp_path / "derived")
    out = tmp_path / "diag"
    out.mkdir()
    assert sd().main([str(derived), str(out)]) == 0
    lines = capsys.readouterr().out.splitlines()
    images = [line for line in lines if line.startswith("SOFFICE-DIAG-IMAGES ")]
    strips = [line for line in lines if line.startswith("SOFFICE-DIAG-STRIP ")]
    docs = sorted(line.split(" ", 2)[1].removeprefix("doc=") for line in images)
    assert docs == sorted(
        ["1800107_pdf.docx", "1800107_pdf.odt", "1913500_pdf.odt", "1800107_pdf_tiny.docx", "1800107_pdf_tiny.odt"]
    )
    assert not any("1913500_pdf.docx" in line for line in lines)
    for line in images:
        for key in ("format", "bytes", "images", "png", "jpeg", "gif", "other", "unreadable", "image_bytes"):
            assert re.search(rf" {key}=\d+| {key}=(docx|odt)", line), (key, line)
        assert re.search(r" pixels=\d+ decoded_bytes=\d+ largest_px=\d+x\d+$", line), line
    assert len(strips) == 2
    assert any("doc=1800107_pdf_tiny.odt source=1800107.pdf format=odt replaced=2 kept_other=1" in s for s in strips)
    assert any("doc=1800107_pdf_tiny.docx source=1800107.pdf format=docx replaced=2 kept_other=1" in s for s in strips)
    assert sorted(path.name for path in out.iterdir()) == [
        "1800107_pdf_tiny.docx",
        "1800107_pdf_tiny.odt",
        "manifest.json",
    ]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["inventory"]) == 5
    assert len(manifest["stripped"]) == 2
    values = [value for entry in manifest["inventory"] + manifest["stripped"] for value in entry.values()]
    for value in values:
        assert isinstance(value, int | str), value
        if isinstance(value, str):
            assert "/" not in value, value
            assert "\\" not in value, value
            assert not re.match(r"^[A-Za-z]:", value), value


def _broken(case: str, root: Path) -> Path:
    if case == "no_manifest":
        root.mkdir()
        return root
    if case == "malformed":
        root.mkdir()
        (root / "manifest.json").write_text("{not json", encoding="utf-8")
        return root
    ok = {"result": "ok", "bytes": 1, "images": 1, "ms": 1}
    full = [
        {"name": "1800107_pdf.docx", "source": "1800107.pdf", "format": "docx"} | ok,
        {"name": "1800107_pdf.odt", "source": "1800107.pdf", "format": "odt"} | ok,
        {"name": "1913500_pdf.odt", "source": "1913500.pdf", "format": "odt"} | ok,
    ]
    if case == "odt_missing":
        return _derived(root, [entry for entry in full if entry["name"] != "1800107_pdf.odt"])
    if case == "docx_missing":
        return _derived(root, [entry for entry in full if entry["name"] != "1800107_pdf.docx"])
    if case == "docx_timeout":
        return _derived(root, [entry | {"result": "timeout"} if entry["format"] == "docx" else entry for entry in full])
    assert case == "file_absent"
    return _derived(root, full, write=False)


@pytest.mark.parametrize(
    "case", ["no_manifest", "malformed", "odt_missing", "docx_missing", "docx_timeout", "file_absent"]
)
def test_negative_main_exit_2_on_a_broken_derived_folder(
    tmp_path: Path, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    derived = _broken(case, tmp_path / "derived")
    assert sd().main([str(derived), str(tmp_path / "diag")]) == 2
    error = capsys.readouterr().err
    assert error.strip()
    assert len(error.strip().splitlines()) == 1


def test_wrong_arguments_are_exit_2() -> None:
    assert sd().main([]) == 2
    assert sd().main(["a"]) == 2
    assert sd().main(["a", "b", "c"]) == 2
