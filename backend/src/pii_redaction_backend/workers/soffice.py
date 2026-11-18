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
jail execs by absolute path, so the command names /usr/bin/soffice. The
profile is hardened before each start (plan 02-17, SAFE-03): the entries of
lo_profile/registrymodifications.xcu (macros off, no external links or fields
updated, no active content, no exotic formats, no update check) go into the
copy of the template, second layer behind the sanitizer.
"""

import contextlib
import os
import re
import shutil
import stat
import sys
from importlib import resources
from pathlib import Path
from typing import Final

from pii_redaction_backend.workers.child import SOFFICE_TAIL_LINES, run_child

PROFILE_ROOT: Final = "/tmp"  # noqa: S108 - one throwaway profile per job, deleted in finally
DEFAULT_TIMEOUT_S: Final = 120.0
SOFFICE: Final = "/usr/bin/soffice"
# sal/osl/unx/pipe.cxx: OSL_PIPE_<user ident>_<pipe name>, pipe name SingleOfficeIPC_<md5>.
IPC_SOCKET_GLOB: Final = "OSL_PIPE_*_SingleOfficeIPC_*"
# The exact name (LibreOffice 25.2): the user ident is the uid in decimal
# (sal/osl/unx/security.cxx, osl_psz_getUserIdent); the hash is the MD5 of the
# UserInstallation URL, each of its 16 bytes in lower case hex without a
# leading zero (desktop/source/app/officeipcthread.cxx, CreateMD5FromString),
# so 16 to 32 hex digits. Nothing else in /tmp has this name.
IPC_SOCKET_NAME: Final = re.compile(r"OSL_PIPE_(?P<uid>[0-9]+)_SingleOfficeIPC_[0-9a-f]{16,32}")
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
# Every file the server writes into a job profile is new, private and never followed through a link.
NEW_FILE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
# The hardening of every job profile (plan 02-17, SAFE-03): a package file of
# the wheel, its entries go into the registrymodifications.xcu of the template copy.
HARDENING_PACKAGE: Final = "pii_redaction_backend.workers"
HARDENING_RESOURCE: Final = "lo_profile/registrymodifications.xcu"
REGISTRY_NAMESPACE: Final = "http://openoffice.org/2001/registry"
REGISTRY_DECLARATION: Final = b'xmlns:oor="http://openoffice.org/2001/registry"'
ITEMS_OPEN: Final = b"<oor:items"
ITEMS_CLOSE: Final = b"</oor:items>"


class ConversionFailed(Exception):
    """LibreOffice ran, but did not leave exactly one PDF behind."""


class ProfileTemplateMissing(ConversionFailed):
    """The profile template is missing, unreadable, holds more than folders and files, or cannot take the hardening.

    reason is a fixed word for the log (missing, unreadable, unsafe_entry;
    malformed and conflict for its registrymodifications.xcu, plan 02-17);
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


def is_own_ipc_socket(name: str, info: os.stat_result, uid: int) -> bool:
    """A LibreOffice single-instance socket of this uid: exact name with this uid, a socket, owned by uid.

    Anything else stays, the HaRP socket /tmp/exapp.sock (same uid, also a
    socket) and a file that only borrows the name included.
    """
    match = IPC_SOCKET_NAME.fullmatch(name)
    return match is not None and match["uid"] == str(uid) and stat.S_ISSOCK(info.st_mode) and info.st_uid == uid


def _remove_ipc_sockets(root: Path) -> None:
    """Remove the single-instance sockets LibreOffice leaves in root.

    soffice binds /tmp/OSL_PIPE_<uid>_SingleOfficeIPC_<hash> (profiles.SOFFICE_SOCKETS)
    but may not remove it again (Landlock grants no removal in /tmp). The
    server removes it, before a run (a socket left by an earlier child must not
    stand in the way) and after it. Only what is_own_ipc_socket accepts.
    """
    if sys.platform == "win32":
        return
    uid = os.getuid()
    for entry in root.glob(IPC_SOCKET_GLOB):
        with contextlib.suppress(OSError):
            if is_own_ipc_socket(entry.name, entry.lstat(), uid):
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
    descriptor = os.open(target, NEW_FILE_FLAGS, 0o600)
    with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
        shutil.copyfileobj(reader, writer, COPY_CHUNK)


def _write_new(target: Path, data: bytes) -> None:
    descriptor = os.open(target, NEW_FILE_FLAGS, 0o600)
    with os.fdopen(descriptor, "wb") as writer:
        writer.write(data)


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


def hardening() -> bytes:
    """The hardening entries of the package (lo_profile/registrymodifications.xcu), read from the installed wheel."""
    return resources.files(HARDENING_PACKAGE).joinpath(HARDENING_RESOURCE).read_bytes()


def _registry_keys(data: bytes) -> set[tuple[str, str]]:
    """(item path, property name) of every property of a registrymodifications.xcu; malformed if it is none."""
    from pii_redaction_backend.intake import xmlcheck
    from pii_redaction_backend.intake.verdict import Rejected

    try:
        root = xmlcheck.parse_part(data)
    except Rejected:
        raise ProfileTemplateMissing("malformed") from None
    if root.tag != f"{{{REGISTRY_NAMESPACE}}}items":
        raise ProfileTemplateMissing("malformed")
    path_key, name_key = f"{{{REGISTRY_NAMESPACE}}}path", f"{{{REGISTRY_NAMESPACE}}}name"
    return {
        (str(item.get(path_key)), str(prop.get(name_key)))
        for item in root.iterchildren(tag="item")
        for prop in item.iterchildren(tag="prop")
    }


def _body(data: bytes) -> tuple[int, int]:
    """Where the content of the oor:items root starts and ends; malformed without the oor namespace or a closing tag."""
    opening = data.find(ITEMS_OPEN)
    start = data.find(b">", opening) + 1
    end = data.rfind(ITEMS_CLOSE)
    if opening < 0 or start <= opening or end < start or REGISTRY_DECLARATION not in data[opening:start]:
        raise ProfileTemplateMissing("malformed")
    return start, end


def harden_profile(profile: Path) -> None:
    """Add the hardening entries to the registrymodifications.xcu of the job profile, before LibreOffice starts.

    The template copy keeps what LibreOffice wrote into it at the image build
    (ooSetupInstCompleted among it: without it the start would count as a new
    user installation, plan 02-16 R1), so the file is not replaced: the
    entries of the package go in front of its closing tag, byte for byte.
    Fail-closed: a file that is no registry (malformed) or one that already
    sets a key of the hardening (conflict) ends the job before soffice starts;
    which of two values LibreOffice would take is not left to chance. The
    template file is parsed with the one XML parser of the package
    (intake.xmlcheck): no DOCTYPE, no entities, no network.
    """
    target = profile / PROFILE_USER / TEMPLATE_MARKER
    ours = hardening()
    try:
        current = target.read_bytes()
    except OSError:
        raise ProfileTemplateMissing("missing") from None
    _, close = _body(current)
    if _registry_keys(current) & _registry_keys(ours):
        raise ProfileTemplateMissing("conflict")
    start, end = _body(ours)
    temp = target.with_name(f"{target.name}.tmp")
    _write_new(temp, current[:close] + ours[start:end] + current[close:])
    os.replace(temp, target)


async def convert(src: Path, outdir: Path, job_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Path:
    """Convert src into outdir and return the one PDF it produced.

    An invalid job id ends the call before any file is touched.
    """
    _checked(job_id)
    _prepare(outdir)
    profile, env = prepare_profile(job_id)
    _remove_ipc_sockets(Path(PROFILE_ROOT))
    try:
        seed_profile(profile)
        harden_profile(profile)
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
