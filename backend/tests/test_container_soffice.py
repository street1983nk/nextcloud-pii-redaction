"""DOCX to PDF through the real LibreOffice in the jail of the "soffice" profile (plan 02-08).

Runs only inside the test stage of the image (sandbox.yml, -m container): the
development machine has neither LibreOffice nor Docker. The DOCX is written
here with the standard library, so the test needs no file outside the image.

HaRP run 44015648619 showed the regression: with the jail of 02-08 soffice
ended after 249 ms and every DOCX job failed with render_failed. On failure
this test shows exit code, signal and the cleaned stderr tail, the same
diagnosis the server logs.
"""

import time
import zipfile
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.workers import child, soffice
from tests.conftest import record_measurement

pytestmark = [pytest.mark.container, pytest.mark.linux]

MARKER = "Containerprobe Umwandlung 4711"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
PACKAGE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


def _docx(path: Path) -> Path:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}">'
        f"<w:body><w:p><w:r><w:t>{MARKER}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/document.xml", document)
    return path


async def test_a_docx_becomes_a_pdf_in_the_soffice_jail(tmp_path: Path) -> None:
    source = _docx(tmp_path / "probe.docx")
    outdir = tmp_path / "pdf"
    started = time.monotonic()

    try:
        pdf = await soffice.convert(source, outdir, "990001")
    except child.ChildFailed as failure:
        pytest.fail(
            f"soffice failed: exit {failure.exit_code}, signal {failure.signal}, stderr {failure.stderr_tail!r}"
        )
    record_measurement("soffice_docx_ms", int((time.monotonic() - started) * 1000))

    with pymupdf.open(pdf) as document:
        assert document.page_count == 1
        assert MARKER in document[0].get_text()
    # The profile with its temporary folder is gone, and no socket is left in /tmp.
    assert _leftovers("990001") == []


def _leftovers(job_id: str) -> list[str]:
    root = Path(soffice.PROFILE_ROOT)
    found = [path.name for path in root.glob(soffice.IPC_SOCKET_GLOB)]
    return found + ([f"lo-{job_id}"] if (root / f"lo-{job_id}").exists() else [])
