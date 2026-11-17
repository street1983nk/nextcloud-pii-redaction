"""Stage B of the pre-check for PDF: pages, objects, page size, pixels, streams, passwords, signature.

The PDFs are written here with the standard library (and by ci/make_corpus.py),
never by pikepdf, so the check is not tested against the pattern it uses.
"""

import zlib
from pathlib import Path
from types import ModuleType

import pytest

from pii_redaction_backend.intake import limits, pdfcheck
from pii_redaction_backend.intake.pdfcheck import PdfReport
from pii_redaction_backend.intake.verdict import Rejected
from tests.conftest import ci_module

Corpus = tuple[Path, dict[str, dict[str, object]]]


def maker() -> ModuleType:
    return ci_module("make_corpus")


def _verdict(path: Path) -> str:
    try:
        pdfcheck.check_pdf(path)
    except Rejected as rejected:
        return rejected.verdict
    return "ok"


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _one_page(tmp_path: Path, page_extra: bytes = b"", extra_objects: tuple[bytes, ...] = ()) -> Path:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] " + page_extra + b">>",
        *extra_objects,
    ]
    return _write(tmp_path, "one.pdf", maker()._pdf(objects))


# -- the corpus ---------------------------------------------------------------------------


PDF_CASES = [
    "harmless.pdf",
    "pdf_300_pages.pdf",
    "pdf_301_pages.pdf",
    "pdf_huge_mediabox.pdf",
    "pdf_huge_image.pdf",
    "pdf_flate_bomb.pdf",
    "pdf_page_loop.pdf",
    "pdf_objects_500001.pdf",
    "pdf_user_password.pdf",
    "pdf_owner_only.pdf",
    "pdf_signed.pdf",
    "truncated.pdf",
]


@pytest.mark.parametrize("name", PDF_CASES)
def test_every_pdf_of_the_corpus_gets_a_word_of_its_manifest(corpus: Corpus, name: str) -> None:
    folder, manifest = corpus
    expected = set(manifest[name]["expect"])  # type: ignore[arg-type]
    # "confirm" is the job answer for a signed file; the check itself accepts it.
    if "confirm" in expected:
        expected = {"ok"}
    assert _verdict(folder / name) in expected


def test_three_hundred_pages_are_counted(corpus: Corpus) -> None:
    folder, _ = corpus
    assert pdfcheck.check_pdf(folder / "pdf_300_pages.pdf") == PdfReport(pages=300, signed=False, owner_protected=False)


def test_the_owner_password_alone_is_accepted_and_marked(corpus: Corpus) -> None:
    folder, _ = corpus
    report = pdfcheck.check_pdf(folder / "pdf_owner_only.pdf")
    assert report.owner_protected is True
    assert report.signed is False


def test_a_user_password_is_encrypted_pdf(corpus: Corpus) -> None:
    folder, _ = corpus
    assert _verdict(folder / "pdf_user_password.pdf") == "encrypted_pdf"


def test_the_signed_pdf_is_marked(corpus: Corpus) -> None:
    folder, _ = corpus
    assert pdfcheck.check_pdf(folder / "pdf_signed.pdf").signed is True


def test_the_harmless_pdf_is_plain(corpus: Corpus) -> None:
    folder, _ = corpus
    assert pdfcheck.check_pdf(folder / "harmless.pdf") == PdfReport(pages=1, signed=False, owner_protected=False)


# -- limits at their edge ---------------------------------------------------------------


def test_exactly_the_object_cap_is_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path, "max.pdf", maker()._many_objects(limits.MAX_PDF_OBJECTS))
    assert _verdict(path) == "ok"


def test_one_object_over_the_cap_is_too_large(tmp_path: Path) -> None:
    path = _write(tmp_path, "over.pdf", maker()._many_objects(limits.MAX_PDF_OBJECTS + 1))
    assert _verdict(path) == "too_large"


def test_the_page_side_counts_the_user_unit(tmp_path: Path) -> None:
    assert _verdict(_one_page(tmp_path, b"/UserUnit 10 /MediaBox [0 0 1440 1440] ")) == "ok"
    assert _verdict(_one_page(tmp_path, b"/UserUnit 10 /MediaBox [0 0 1441 1440] ")) == "too_large"


def test_the_page_side_at_the_cap_is_accepted(tmp_path: Path) -> None:
    assert _verdict(_one_page(tmp_path, b"/MediaBox [0 0 14400 100] ")) == "ok"
    assert _verdict(_one_page(tmp_path, b"/MediaBox [-1 0 14400 100] ")) == "too_large"


def _image(width: int, height: int) -> bytes:
    return maker()._stream(
        zlib.compress(b"\x00" * 64),
        b"/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Filter /FlateDecode " % (width, height),
    )


def test_an_image_at_the_pixel_cap_is_accepted_one_over_is_not(tmp_path: Path) -> None:
    resources = b"/Resources << /XObject << /Im1 4 0 R >> >> "
    assert _verdict(_one_page(tmp_path, resources, (_image(10_000, 10_000),))) == "ok"
    assert _verdict(_one_page(tmp_path, resources, (_image(10_000, 10_001),))) == "too_large"


def test_an_image_hidden_in_a_form_xobject_is_found(tmp_path: Path) -> None:
    form = maker()._stream(
        b"/Im1 Do", b"/Type /XObject /Subtype /Form /BBox [0 0 1 1] /Resources << /XObject << /Im1 5 0 R >> >> "
    )
    path = _one_page(tmp_path, b"/Resources << /XObject << /Fm1 4 0 R >> >> ", (form, _image(20_000, 20_000)))
    assert _verdict(path) == "too_large"


def test_a_stream_with_an_external_file_is_damaged(tmp_path: Path) -> None:
    external = b"<< /Length 0 /F (file:///etc/passwd) >>\nstream\n\nendstream"
    assert _verdict(_one_page(tmp_path, b"/Contents 4 0 R ", (external,))) == "damaged"


def test_positive_control_the_same_stream_without_f_passes(tmp_path: Path) -> None:
    internal = b"<< /Length 0 >>\nstream\n\nendstream"
    assert _verdict(_one_page(tmp_path, b"/Contents 4 0 R ", (internal,))) == "ok"


def test_a_declared_decoded_length_over_the_ratio_is_too_large(tmp_path: Path) -> None:
    data = zlib.compress(b"q Q\n" * 64)
    declared = maker()._stream(data, b"/Filter /FlateDecode /DL %d " % (2 * 1024 * 1024 * 1024))
    assert _verdict(_one_page(tmp_path, b"/Contents 4 0 R ", (declared,))) == "too_large"


def test_an_ordinary_compressed_content_stream_passes(tmp_path: Path) -> None:
    text = b"".join(b"BT /F1 12 Tf 72 %d Td (Zeile %d) Tj ET\n" % (700 - n, n) for n in range(20_000))
    stream = maker()._stream(zlib.compress(text, 9), b"/Filter /FlateDecode ")
    assert _verdict(_one_page(tmp_path, b"/Contents 4 0 R ", (stream,))) == "ok"


# -- signatures ----------------------------------------------------------------------------


def _form(tmp_path: Path, acroform: bytes, field: bytes) -> Path:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R] " + acroform + b">> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
        field,
        b"<< /Type /Sig /Filter /Adobe.PPKLite >>",
    ]
    return _write(tmp_path, "form.pdf", maker()._pdf(objects))


def test_a_sig_field_with_a_value_is_signed_without_sigflags(tmp_path: Path) -> None:
    path = _form(tmp_path, b"", b"<< /FT /Sig /T (S) /V 5 0 R >>")
    assert pdfcheck.check_pdf(path).signed is True


def test_an_empty_sig_field_without_sigflags_is_not_signed(tmp_path: Path) -> None:
    path = _form(tmp_path, b"", b"<< /FT /Sig /T (S) >>")
    assert pdfcheck.check_pdf(path).signed is False


def test_sigflags_bit_one_alone_is_signed(tmp_path: Path) -> None:
    path = _form(tmp_path, b"/SigFlags 1 ", b"<< /FT /Tx /T (S) >>")
    assert pdfcheck.check_pdf(path).signed is True
    path = _form(tmp_path, b"/SigFlags 2 ", b"<< /FT /Tx /T (S) >>")
    assert pdfcheck.check_pdf(path).signed is False


def test_a_sig_value_on_a_kid_with_inherited_type_is_signed(tmp_path: Path) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R] >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
        b"<< /FT /Sig /T (P) /Kids [5 0 R] >>",
        b"<< /Parent 4 0 R /V 6 0 R >>",
        b"<< /Type /Sig >>",
    ]
    path = _write(tmp_path, "kids.pdf", maker()._pdf(objects))
    assert pdfcheck.check_pdf(path).signed is True


def test_a_field_tree_loop_ends(tmp_path: Path) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R] >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
        b"<< /T (A) /Kids [5 0 R] >>",
        b"<< /T (B) /Kids [4 0 R] >>",
    ]
    path = _write(tmp_path, "loop.pdf", maker()._pdf(objects))
    assert _verdict(path) in {"ok", "damaged"}


def test_a_file_that_is_no_pdf_is_damaged(tmp_path: Path) -> None:
    assert _verdict(_write(tmp_path, "x.pdf", b"not a pdf at all")) == "damaged"


def test_the_inflater_stops_soon_after_the_allowance() -> None:
    raw = zlib.compress(b"\x00" * (64 * 1024 * 1024), 9)
    counted = pdfcheck._inflated_size(raw, 2 * 1024 * 1024)
    assert 2 * 1024 * 1024 < counted <= 2 * 1024 * 1024 + pdfcheck.INFLATE_BLOCK
    # Positive control: with room for everything it counts the whole stream.
    assert pdfcheck._inflated_size(raw, 128 * 1024 * 1024) == 64 * 1024 * 1024
