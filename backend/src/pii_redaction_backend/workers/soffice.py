"""DOCX and ODT to PDF with LibreOffice headless, one process and one profile per job.

The profile directory lives at /tmp/lo-<job_id> (instances with a shared
profile block each other and keep state between jobs) and is deleted after
the run. The call goes through run_child: empty environment, own process
group, time limit, nothing read from stdout or stderr. Full hardening of the
profile (macros, external links, update check) is phase 2 (SAFE-01 to
SAFE-04); see the threat model of plan 01-05.
"""

import shutil
from pathlib import Path
from typing import Final

from pii_redaction_backend.workers.child import run_child

PROFILE_ROOT: Final = "/tmp"  # noqa: S108 - one throwaway profile per job, deleted in finally
DEFAULT_TIMEOUT_S: Final = 120.0


class ConversionFailed(Exception):
    """LibreOffice ran, but did not leave exactly one PDF behind."""


def _checked(job_id: str) -> str:
    if not job_id.isdigit() or not job_id.isascii():
        msg = "job id must be digits only"
        raise ValueError(msg)
    return job_id


def command(src: Path, outdir: Path, job_id: str) -> list[str]:
    """The exact command line of one conversion."""
    profile = f"file://{PROFILE_ROOT}/lo-{_checked(job_id)}"
    return [
        "soffice",
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nologo",
        f"-env:UserInstallation={profile}",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(outdir),
        str(src),
    ]


def _prepare(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)


def _single_pdf(outdir: Path) -> Path:
    pdfs = sorted(outdir.glob("*.pdf"))
    if len(pdfs) != 1:
        raise ConversionFailed
    return pdfs[0]


async def convert(src: Path, outdir: Path, job_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Path:
    """Convert src into outdir and return the one PDF it produced."""
    profile = Path(PROFILE_ROOT) / f"lo-{_checked(job_id)}"
    _prepare(outdir)
    try:
        await run_child(command(src, outdir, job_id), timeout_s=timeout_s, cwd=outdir)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return _single_pdf(outdir)
