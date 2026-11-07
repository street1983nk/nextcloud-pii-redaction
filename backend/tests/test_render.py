"""Page 1 as PNG plus meta.json, and the LibreOffice command line.

The render child is called in process here (main(argv)); in the container it
runs as python -I -m pii_redaction_backend.workers.render. LibreOffice is not
installed on the development machine, so soffice is checked by its argument
list here and for real in CI (plan 15).
"""

import json
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.workers import render, soffice


def _two_page_pdf(path: Path) -> Path:
    document = pymupdf.open()
    for number in (1, 2):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Testseite {number}")
    document.save(path)
    document.close()
    return path


def test_page_one_becomes_a_png_with_its_meta(tmp_path: Path) -> None:
    source = _two_page_pdf(tmp_path / "in.pdf")
    out = tmp_path / "page-1.png"

    assert render.main([str(source), str(out), "120"]) == 0

    assert out.read_bytes().startswith(b"\x89PNG")
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["pages"] == 2
    assert 985 <= meta["width"] <= 1000, "A4 at 120 dpi is about 992 px wide"
    assert meta["height"] > meta["width"]


def test_a_broken_file_ends_with_exit_two_and_no_output(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7 this is not a pdf")
    out = tmp_path / "page-1.png"

    assert render.main([str(source), str(out), "120"]) == 2
    assert not out.exists()
    assert not (tmp_path / "meta.json").exists()


def test_wrong_arguments_end_with_exit_two(tmp_path: Path) -> None:
    assert render.main([]) == 2
    assert render.main([str(tmp_path / "a.pdf"), str(tmp_path / "b.png"), "zero"]) == 2


def test_the_soffice_command_is_exactly_the_documented_one(tmp_path: Path) -> None:
    source = tmp_path / "in.docx"
    outdir = tmp_path / "out"

    assert soffice.command(source, outdir, "17") == [
        "soffice",
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nologo",
        "-env:UserInstallation=file:///tmp/lo-17",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(outdir),
        str(source),
    ]


@pytest.mark.parametrize("job_id", ["", "1a", "../x", "-1", "1 2"])
def test_a_job_id_that_is_not_digits_is_refused(tmp_path: Path, job_id: str) -> None:
    with pytest.raises(ValueError, match="digits"):
        soffice.command(tmp_path / "in.odt", tmp_path, job_id)
