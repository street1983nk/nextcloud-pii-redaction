"""DOCX and ODT to PDF with LibreOffice headless, one process and one profile per job.

The profile directory lives at /tmp/lo-<job_id> (instances with a shared
profile block each other and keep state between jobs) and is deleted after
the run. The call goes through run_child: empty environment, own process
group, time limit, nothing read from stdout, inside the jail of the "soffice"
profile: it may read the source, write only the output folder and its own
profile folder (TMPDIR points into it) and create its single-instance socket
in /tmp. stderr is kept only for the diagnosis of a failure (child.py,
diagnostic_tail). The jail execs by absolute path, so the command names
/usr/bin/soffice. Full hardening of the profile (macros, external links,
update check) follows in phase 2 (SAFE-03).
"""

import contextlib
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Final

from pii_redaction_backend.workers.child import run_child

PROFILE_ROOT: Final = "/tmp"  # noqa: S108 - one throwaway profile per job, deleted in finally
DEFAULT_TIMEOUT_S: Final = 120.0
SOFFICE: Final = "/usr/bin/soffice"
# sal/osl/unx/pipe.cxx: OSL_PIPE_<user ident>_<pipe name>, pipe name SingleOfficeIPC_<md5>.
IPC_SOCKET_GLOB: Final = "OSL_PIPE_*_SingleOfficeIPC_*"


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
        SOFFICE,
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


def _remove_ipc_sockets(root: Path) -> None:
    """Remove the single-instance sockets LibreOffice leaves in root.

    soffice binds /tmp/OSL_PIPE_<user>_SingleOfficeIPC_<hash> (profiles.SOFFICE_SOCKETS)
    but may not remove it again (Landlock grants no removal in /tmp). The
    server removes it, before a run (a socket left by an earlier child must not
    stand in the way) and after it. Only sockets of this uid with this name.
    """
    if sys.platform == "win32":
        return
    for entry in root.glob(IPC_SOCKET_GLOB):
        with contextlib.suppress(OSError):
            info = entry.lstat()
            if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
                entry.unlink()


async def convert(src: Path, outdir: Path, job_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Path:
    """Convert src into outdir and return the one PDF it produced."""
    profile = Path(PROFILE_ROOT) / f"lo-{_checked(job_id)}"
    _prepare(outdir)
    # Landlock grants paths that exist; the profile folder is made here so the
    # jail can hand it to LibreOffice as writable. Its temporary files go to a
    # folder inside it (TMPDIR), not to /tmp, where the child may not write.
    profile.mkdir(mode=0o700, exist_ok=True)
    temporary = profile / "tmp"
    temporary.mkdir(mode=0o700, exist_ok=True)
    _remove_ipc_sockets(Path(PROFILE_ROOT))
    try:
        await run_child(
            command(src, outdir, job_id),
            profile="soffice",
            cwd=outdir,
            read=(str(src),),
            write=(str(outdir), str(profile)),
            timeout_s=timeout_s,
            extra_env={"TMPDIR": str(temporary)},
            diagnose=True,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        _remove_ipc_sockets(Path(PROFILE_ROOT))
    return _single_pdf(outdir)
