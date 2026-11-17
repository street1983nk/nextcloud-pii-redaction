"""The product conversion on the pushed image, before docker.yml tags it (plan 02-16, risk R3).

usage: /app/.venv/bin/python -I soffice_gate.py   (inside the runtime image, as uid 10001)

LibreOffice is not pinned: a rebuild on a new base digest, the monthly
rebuild included, can bring a new package and with it a profile template made
by the new version. docker.yml copies this file into the container it started
from the digest it just pushed and runs it there; the merge job that sets the
dev and version tags needs this job, so an image whose LibreOffice does not
convert in the product jail never gets a tag.

It writes a one-paragraph DOCX with the standard library, converts it with
workers.soffice.convert (template copy, jail, cleanup: the product path) and
checks the PDF with PyMuPDF. One line goes to stdout:

    SOFFICE-GATE pdf=<ja|nein> marker=<ja|nein> rest=<n> ms=<ms> reason=<word>

rest counts LibreOffice pipe sockets left in /tmp after the cleanup. Exit 0
only for pdf=ja marker=ja rest=0. Standard library plus the image's own
packages; nothing is fetched.
"""

import asyncio
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Final

MARKER: Final = "Gate Umwandlung 4711"
JOB_ID: Final = "990009"
W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
PACKAGE_RELS: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


def write_docx(path: Path) -> Path:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}">'
        f"<w:body><w:p><w:r><w:t>{MARKER}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/document.xml", document)
    return path


def gate_line(facts: dict[str, object]) -> str:
    return (
        f"SOFFICE-GATE pdf={facts['pdf']} marker={facts['marker']} rest={facts['rest']} "
        f"ms={facts['ms']} reason={facts['reason']}"
    )


def passed(facts: dict[str, object]) -> bool:
    return facts["pdf"] == "ja" and facts["marker"] == "ja" and facts["rest"] == 0


async def convert_once(folder: Path) -> dict[str, object]:
    import pymupdf

    from pii_redaction_backend.workers import child, soffice

    facts: dict[str, object] = {"pdf": "nein", "marker": "nein", "rest": 0, "ms": 0, "reason": "ok"}
    source = write_docx(folder / "gate.docx")
    started = time.monotonic()
    try:
        pdf = await soffice.convert(source, folder / "pdf", JOB_ID)
    except soffice.ProfileTemplateMissing as missing:
        facts["reason"] = f"template_{missing.reason}"
    except child.ChildFailed as failed:
        facts["reason"] = f"exit{failed.exit_code}"
    except (child.ChildTimeout, soffice.ConversionFailed, OSError) as error:
        facts["reason"] = type(error).__name__
    else:
        facts["pdf"] = "ja"
        with pymupdf.open(pdf) as document:
            facts["marker"] = "ja" if MARKER in document[0].get_text() else "nein"
    facts["ms"] = int((time.monotonic() - started) * 1000)
    return facts


def pipe_rest() -> int:
    """LibreOffice pipe sockets still in /tmp after the cleanup of convert."""
    from pii_redaction_backend.workers import soffice

    return len(list(Path(soffice.PROFILE_ROOT).glob(soffice.IPC_SOCKET_GLOB)))


def main() -> int:
    folder = Path(tempfile.mkdtemp(prefix="soffice-gate-"))
    try:
        facts = asyncio.run(convert_once(folder))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    facts["rest"] = pipe_rest()
    print(gate_line(facts), flush=True)
    return 0 if passed(facts) else 1


if __name__ == "__main__":
    sys.exit(main())
