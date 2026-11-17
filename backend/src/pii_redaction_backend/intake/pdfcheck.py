"""Stage B of the pre-check for PDF, with pikepdf (qpdf) in the pre-check child.

The answer is a PdfReport (pages, signed, owner_protected) or Rejected with a
word of the closed list:

- a user password: encrypted_pdf; only an owner password (the file opens with
  the empty password): accepted, owner_protected=True (D-02-10);
- more than MAX_PAGES pages: too_many_pages (the one page cap, D-02-08);
- more than MAX_PDF_OBJECTS objects, a page side over MAX_PAGE_SIDE_PT with
  UserUnit applied, an image over MAX_IMAGE_PIXELS, or a Flate stream that
  decodes beyond the ZIP ratio rule: too_large;
- a stream that names an external file (/F), a page tree loop, anything qpdf
  cannot open: damaged;
- AcroForm /SigFlags bit 1, or a /Sig field with a value: signed=True.

Images are judged by /Width x /Height and never decoded; the renderer decodes
them later under RLIMIT_AS. A non-image Flate stream is inflated in blocks
and the output thrown away, only to count it: it stops as soon as the ratio
rule of the ZIP check (ZIP_MAX_RATIO from ZIP_RATIO_MIN_BYTES on) is broken,
so a small bomb never reaches the renderer. A zlib error inside a stream is
left to the renderer (broken streams are common and MuPDF reads past them).
Any other exception is damaged: fail closed. Nothing is logged.
"""

import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pii_redaction_backend.intake import limits
from pii_redaction_backend.intake.verdict import Rejected

INFLATE_BLOCK: Final = 1024 * 1024
SIG_FLAGS_SIGNATURES_EXIST: Final = 1
# A field tree deeper than this is not a form, it is an attack on the walk.
MAX_FIELD_DEPTH: Final = 64
_FLATE: Final = frozenset({"/FlateDecode", "/Fl"})


@dataclass(frozen=True, slots=True)
class PdfReport:
    """What the PDF check saw on a file it accepts."""

    pages: int
    signed: bool
    owner_protected: bool


def check_pdf(path: Path) -> PdfReport:
    """Judge one PDF; returns its report or raises Rejected."""
    import pikepdf

    try:
        with pikepdf.open(path) as pdf:
            return _judge(pdf)
    except pikepdf.PasswordError:
        raise Rejected("encrypted_pdf") from None
    except Rejected:
        raise
    except Exception:
        raise Rejected("damaged") from None


def _judge(pdf: Any) -> PdfReport:
    declared = int(pdf.trailer.get("/Size", 0))
    if declared - 1 > limits.MAX_PDF_OBJECTS:
        raise Rejected("too_large")
    objects = pdf.objects
    if len(objects) > limits.MAX_PDF_OBJECTS:
        raise Rejected("too_large")
    pages = len(pdf.pages)
    if pages > limits.MAX_PAGES:
        raise Rejected("too_many_pages")
    for page in pdf.pages:
        _judge_page(page)
    for item in objects:
        _judge_object(item)
    return PdfReport(pages=pages, signed=_signed(pdf), owner_protected=bool(pdf.is_encrypted))


def _judge_page(page: Any) -> None:
    box = [float(value) for value in page.mediabox]
    unit = float(page.obj.get("/UserUnit", 1))
    width = abs(box[2] - box[0]) * unit
    height = abs(box[3] - box[1]) * unit
    if max(width, height) > limits.MAX_PAGE_SIDE_PT:
        raise Rejected("too_large")


def _judge_object(item: Any) -> None:
    import pikepdf

    if not isinstance(item, pikepdf.Stream):
        return
    if "/F" in item:
        raise Rejected("damaged")
    if item.get("/Subtype") == pikepdf.Name.Image:
        if int(item.get("/Width", 0)) * int(item.get("/Height", 0)) > limits.MAX_IMAGE_PIXELS:
            raise Rejected("too_large")
        return
    if _first_filter(item) not in _FLATE:
        return
    raw = item.read_raw_bytes()
    allowed = max(limits.ZIP_MAX_RATIO * max(len(raw), 1), limits.ZIP_RATIO_MIN_BYTES)
    declared = item.get("/DL")
    if declared is not None and int(declared) > allowed:
        raise Rejected("too_large")
    if _inflated_size(raw, allowed) > allowed:
        raise Rejected("too_large")


def _first_filter(item: Any) -> str:
    """The first filter of a stream: a name, or the head of a filter array."""
    import pikepdf

    chosen = item.get("/Filter")
    if isinstance(chosen, pikepdf.Array):
        return str(chosen[0]) if len(chosen) else ""
    return "" if chosen is None else str(chosen)


def _inflated_size(raw: bytes, stop_after: int) -> int:
    """Bytes the Flate data inflates to, counted in blocks; stops past stop_after."""
    inflater = zlib.decompressobj()
    total = 0
    pending = raw
    try:
        while pending and total <= stop_after:
            out = inflater.decompress(pending, INFLATE_BLOCK)
            total += len(out)
            pending = inflater.unconsumed_tail
            if not out and not pending:
                break
    except zlib.error:
        return total
    return total


def _signed(pdf: Any) -> bool:
    form = pdf.Root.get("/AcroForm")
    if form is None:
        return False
    if int(form.get("/SigFlags", 0)) & SIG_FLAGS_SIGNATURES_EXIST:
        return True
    return any(_is_signed_field(field, inherited) for field, inherited in _fields(form.get("/Fields")))


def _fields(roots: Any) -> Iterator[tuple[Any, Any]]:
    """Every field with its inherited /FT, depth first, each object once."""
    if roots is None:
        return
    seen: set[tuple[int, int]] = set()
    stack: list[tuple[Any, Any, int]] = [(field, None, 0) for field in roots]
    while stack:
        field, inherited, depth = stack.pop()
        key = field.objgen
        if key != (0, 0):
            if key in seen:
                continue
            seen.add(key)
        if depth > MAX_FIELD_DEPTH:
            raise Rejected("damaged")
        kind = field.get("/FT", inherited)
        yield field, kind
        stack.extend((kid, kind, depth + 1) for kid in field.get("/Kids", ()))


def _is_signed_field(field: Any, kind: Any) -> bool:
    return str(kind) == "/Sig" and field.get("/V") is not None
