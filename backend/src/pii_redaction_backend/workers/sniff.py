"""The format of a file by its bytes, never by its extension or a mime type.

PDF: the header %PDF-. DOCX: a ZIP with [Content_Types].xml and
word/document.xml. ODT: a ZIP whose first entry is "mimetype" with exactly the
ODF text type. Nothing is extracted; only the names of the archive and the
first 128 bytes of the mimetype entry are read.
"""

import zipfile
from pathlib import Path
from typing import Final, Literal

Format = Literal["pdf", "docx", "odt"]

PDF_MAGIC: Final = b"%PDF-"
ZIP_MAGIC: Final = b"PK\x03\x04"
ODT_MIMETYPE: Final = b"application/vnd.oasis.opendocument.text"
MIMETYPE_MAX_BYTES: Final = 128
DOCX_PARTS: Final = frozenset({"[Content_Types].xml", "word/document.xml"})


def detect(path: Path) -> Format | None:
    """pdf, docx or odt by content, or None for anything else (including broken files)."""
    with path.open("rb") as handle:
        head = handle.read(8)
    if head.startswith(PDF_MAGIC):
        return "pdf"
    if not head.startswith(ZIP_MAGIC):
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if names >= DOCX_PARTS:
                return "docx"
            if entries and entries[0].filename == "mimetype" and entries[0].file_size <= MIMETYPE_MAX_BYTES:
                with archive.open(entries[0]) as mimetype:
                    if mimetype.read(MIMETYPE_MAX_BYTES).strip() == ODT_MIMETYPE:
                        return "odt"
    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError):
        return None
    return None
