"""Every limit of the pre-check, in one place (D-02-07, D-02-08, D-02-13).

The limits are fixed constants: no admin setting moves them, and a change is a
reviewed commit with its test. One cap, one text, one test, for every way into
the analysis: there is exactly one page cap (MAX_PAGES), and every check that
counts pages compares against it.

A file that is over a limit is refused with a word of the closed list in
verdict.py; the limit itself never travels into a message.
"""

from typing import Final

MIB: Final = 1024 * 1024

# The largest source file the container reads through the gateway. 256 MiB is
# far beyond a scanned 300 page document at 300 dpi and still small enough
# that the sanitized copy fits the sandbox file size limit.
MAX_SOURCE_BYTES: Final = 256 * MIB

# The page cap of D-02-08: longer documents are split by the user. The review
# page shows every page, and the detector runs up to half an hour; 300 pages
# keep both within reach.
MAX_PAGES: Final = 300

# PDF structure (checked by pikepdf in the pre-check child, plan 02-09). Real
# documents of 300 pages hold tens of thousands of objects; half a million is
# an object flood, not a document.
MAX_PDF_OBJECTS: Final = 500_000
# 14 400 pt is the largest page side the PDF specification allows (200 inches),
# measured with UserUnit applied.
MAX_PAGE_SIDE_PT: Final = 14_400
# One embedded image: 100 megapixels (a 10 000 x 10 000 scan). Larger is a
# decompression bomb for the renderer.
MAX_IMAGE_PIXELS: Final = 100_000_000
# One rendered page image for the review page and OCR.
MAX_RENDER_PIXELS: Final = 50_000_000

# ZIP containers (DOCX, ODT). A Word document has a few dozen parts; 10 000 is
# far beyond any real one and bounds the work of counting.
ZIP_MAX_ENTRIES: Final = 10_000
# The central directory is read in full; 8 MiB hold 10 000 entries with long names.
ZIP_MAX_CENTRAL_DIRECTORY_BYTES: Final = 8 * MIB
# One member, declared uncompressed. document.xml of a 300 page text is a few MiB.
ZIP_MAX_MEMBER_BYTES: Final = 64 * MIB
# All members together, declared uncompressed.
ZIP_MAX_TOTAL_BYTES: Final = 256 * MIB
# Uncompressed to compressed, judged from ZIP_RATIO_MIN_BYTES on: over 100 is
# too large for an office file, over 1000 is the signature of a bomb (Findling).
ZIP_MAX_RATIO: Final = 100
ZIP_MALICIOUS_RATIO: Final = 1000
ZIP_RATIO_MIN_BYTES: Final = MIB
# The longest member name in bytes (UTF-8), as file systems allow.
ZIP_MAX_NAME_BYTES: Final = 255
# Nested archives are never opened: a ZIP inside the package stays an opaque member.
ZIP_MAX_DEPTH: Final = 0

# One XML part is read at most as large as a member may be.
XML_MAX_PART_BYTES: Final = ZIP_MAX_MEMBER_BYTES

# The compound file directory of an encrypted Office document is read at most this far.
CFB_MAX_DIRECTORY_BYTES: Final = 4 * MIB
