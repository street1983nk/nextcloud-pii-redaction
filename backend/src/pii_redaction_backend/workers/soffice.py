"""DOCX and ODT to PDF with LibreOffice headless, one process and one profile per job.

The profile directory lives at /tmp/lo-<job_id> (instances with a shared
profile block each other and keep state between jobs) and is deleted after
the run. Before the start the server fills it with a fresh copy of the
profile template the image build made (PROFILE_TEMPLATE, plan 02-16): with an
empty profile LibreOffice initialises it and restarts itself once, and in the
jail the second process cannot get past the pipe socket of the first (sandbox
run 44054386548, amd64 and arm64). With a ready profile there is no restart.
There is no init run at run time as a fallback: a missing or unusable
template ends the job (ProfileTemplateMissing). The call goes through
run_child: empty environment, own process group, time limit, nothing read from stdout, inside the jail of the "soffice"
profile: it may read the source, write only the output folder and its own
profile folder (TMPDIR points into it) and create
its single-instance socket in /tmp. stderr is kept only for the diagnosis of
a failure (child.py, diagnostic_tail, 12 lines). No SAL_USE_VCLPLUGIN: with
--headless and no plugin named, LibreOffice 25.2 picks the headless "svp"
plugin itself (vcl/source/app/salplug.cxx, IsHeadlessModeRequested). The
jail execs by absolute path, so the command names /usr/bin/soffice. Full
hardening of the profile (macros, external links, update check) follows in
phase 2 (SAFE-03).
"""

import contextlib
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Final

from pii_redaction_backend.workers.child import SOFFICE_TAIL_LINES, run_child

PROFILE_ROOT: Final = "/tmp"  # noqa: S108 - one throwaway profile per job, deleted in finally
DEFAULT_TIMEOUT_S: Final = 120.0
SOFFICE: Final = "/usr/bin/soffice"
# sal/osl/unx/pipe.cxx: OSL_PIPE_<user ident>_<pipe name>, pipe name SingleOfficeIPC_<md5>.
IPC_SOCKET_GLOB: Final = "OSL_PIPE_*_SingleOfficeIPC_*"
# Each variable of the soffice environment and the folder inside the job profile it names.
# Only TMPDIR: HOME and XDG made no difference in the sandbox run of 7e3c909
# (exit 1 under Landlock with and without them), so they stay closed.
PROFILE_FOLDERS: Final = {"TMPDIR": "tmp"}
# The empty LibreOffice profile the image build made (Dockerfile, runtime
# stage): root-owned, read only, no user data. LibreOffice keeps a profile in
# <UserInstallation>/user, so that folder is what each job gets a copy of.
PROFILE_TEMPLATE: Final = "/opt/pii/soffice-profile-template"
PROFILE_USER: Final = "user"
# Proof that the template was initialised: LibreOffice writes this file on its first start.
TEMPLATE_MARKER: Final = "registrymodifications.xcu"
COPY_CHUNK: Final = 1 << 16


class ConversionFailed(Exception):
    """LibreOffice ran, but did not leave exactly one PDF behind."""


class ProfileTemplateMissing(ConversionFailed):
    """The profile template of the image is missing, unreadable or holds something other than folders and files.

    reason is a fixed word for the log (missing, unreadable, unsafe_entry);
    the message names no path.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"soffice profile template unusable: {reason}")
        self.reason = reason


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


def job_profile(job_id: str) -> Path:
    """The throwaway profile folder of one job: /tmp/lo-<job id>."""
    return Path(PROFILE_ROOT) / f"lo-{_checked(job_id)}"


def _drop(path: Path) -> None:
    """Remove path whatever it is (a symlink as a link, never its target)."""
    with contextlib.suppress(FileNotFoundError):
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)


def prepare_profile(job_id: str) -> tuple[Path, dict[str, str]]:
    """Make a fresh job profile with its folders (0700) and return it with the environment that points into it.

    Whatever an earlier run of the same job id left there goes first, so no
    state crosses from one start to the next. Landlock grants paths that
    exist, so the profile folder is made here and the jail hands it to
    LibreOffice as writable. Its temporary files go to a folder inside it
    (TMPDIR), not to /tmp, where the child may not write. The value passes
    the allowlist of child.child_env only for the soffice profile.
    """
    profile = job_profile(job_id)
    _drop(profile)
    profile.mkdir(mode=0o700)
    env: dict[str, str] = {}
    for key, name in PROFILE_FOLDERS.items():
        folder = profile / name
        folder.mkdir(mode=0o700, exist_ok=True)
        env[key] = str(folder)
    return profile, env


def _copy_file(source: Path, target: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(target, flags, 0o600)
    with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
        shutil.copyfileobj(reader, writer, COPY_CHUNK)


def _copy_tree(source: Path, target: Path) -> None:
    """Copy folders (0700) and plain files (0600) of source; anything else ends the copy."""
    target.mkdir(mode=0o700)
    for entry in sorted(source.iterdir()):
        info = entry.lstat()
        if stat.S_ISDIR(info.st_mode):
            _copy_tree(entry, target / entry.name)
        elif stat.S_ISREG(info.st_mode):
            _copy_file(entry, target / entry.name)
        else:
            raise ProfileTemplateMissing("unsafe_entry")


def seed_profile(profile: Path, template: Path | None = None) -> None:
    """Copy the user folder of the profile template into the job profile, fresh and owned by this process.

    The server copies before the jail starts, so the child needs no rule for
    the template: it never sees it, it gets only its own copy in its own job
    profile. Files arrive 0600 and folders 0700 whatever the template says, so
    LibreOffice may write its copy and no other job shares it. Fail-closed:
    a missing or unreadable template, one without its marker file, or an
    entry that is no plain folder or file raises ProfileTemplateMissing.
    """
    root = Path(PROFILE_TEMPLATE) if template is None else template
    source = root / PROFILE_USER
    try:
        if not source.is_dir() or source.is_symlink():
            raise ProfileTemplateMissing("missing")
        marker = (source / TEMPLATE_MARKER).lstat()
        if not stat.S_ISREG(marker.st_mode):
            raise ProfileTemplateMissing("missing")
        _copy_tree(source, profile / PROFILE_USER)
    except FileNotFoundError:
        raise ProfileTemplateMissing("missing") from None
    except PermissionError:
        raise ProfileTemplateMissing("unreadable") from None


async def convert(src: Path, outdir: Path, job_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Path:
    """Convert src into outdir and return the one PDF it produced."""
    _prepare(outdir)
    profile, env = prepare_profile(job_id)
    _remove_ipc_sockets(Path(PROFILE_ROOT))
    try:
        seed_profile(profile)
        await run_child(
            command(src, outdir, job_id),
            profile="soffice",
            cwd=outdir,
            read=(str(src),),
            write=(str(outdir), str(profile)),
            timeout_s=timeout_s,
            extra_env=env,
            diagnose=True,
            tail_lines=SOFFICE_TAIL_LINES,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        _remove_ipc_sockets(Path(PROFILE_ROOT))
    return _single_pdf(outdir)
