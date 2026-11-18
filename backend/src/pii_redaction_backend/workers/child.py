"""Run work on foreign files in a child process that holds no secret.

Rendering, conversion and the placeholder PDF touch user documents with C
code (MuPDF, LibreOffice). They never run in the server process; each runs as
a child with:

- an empty environment plus a fixed allowlist: no APP_SECRET, APP_ID,
  NEXTCLOUD_URL, AA_VERSION or APP_PERSISTENT_STORAGE reaches it,
- its own process group (start_new_session), so a time limit kills the child
  and everything it started, not just the first process,
- stdin and stdout on DEVNULL; stderr on DEVNULL as well, unless the caller
  asks for a diagnosis (LibreOffice, plan 02-08). Then the last bytes of
  stderr are kept in memory and, only when the child failed, cut down by
  diagnostic_tail() to a few lines without paths, quoted text or anything
  outside printable ASCII, and handed to the log through ChildFailed.

Every child starts through the jail (sandbox/jail.py): the profile of its
kind sets rlimits, NO_NEW_PRIVS, Landlock and seccomp before the real program
runs. After every child, whatever the outcome, sandbox/reaper.py kills and
collects the rest of its group, so no grandchild and no zombie stays behind.

Only the exit code (with the signal of a killed child), that diagnosis and
the files in the work folder come back.
"""

import asyncio
import contextlib
import os
import re
import signal
import sys
from pathlib import Path
from typing import Final

from pii_redaction_backend.resources import hardware
from pii_redaction_backend.sandbox.jail import jail_argv
from pii_redaction_backend.sandbox.profiles import profile_for
from pii_redaction_backend.sandbox.reaper import reap_group

SAFE_ENV: Final[dict[str, str]] = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",  # noqa: S108 - the child's home is a throwaway, its profile lives below the job folder
    "LANG": "C.UTF-8",
    # One OpenMP thread for every child but detect (child_env). Tesseract
    # (ocr) is the OpenMP user it is meant for: one thread per page call is
    # its documented setting and keeps a page from taking every core
    # (research ARCHITECTURE.md). soffice, render, placeholder, precheck and
    # sanitize have no known OpenMP user; there it caps nothing and stays, so
    # their environment does not change (plan 02-16).
    "OMP_THREAD_LIMIT": "1",
    # One malloc arena per process (Pitfall 8); mallopt in the jail would not
    # survive execv, the environment does.
    "MALLOC_ARENA_MAX": "1",
}

# The only extra variables a caller may hand to any child.
EXTRA_ALLOWED: Final = frozenset({"TESSDATA_PREFIX", "SAL_USE_VCLPLUGIN"})

# Variables only the soffice child may get, and only with a folder inside its
# job profile as value (plan 02-08, 02-16): TMPDIR for its temporary files.
# HOME and the XDG folders stay closed: sandbox run of 7e3c909 showed soffice
# fails under Landlock with and without them alike, so nothing proves they are
# needed (owner rule: open only what is proven). Every other child keeps
# HOME=/tmp from SAFE_ENV and gets none of them.
SOFFICE_ENV: Final = frozenset({"TMPDIR"})
# The job profile of soffice is /tmp/lo-<job id> (workers/soffice.py,
# PROFILE_ROOT); a value is that folder or a plain folder below it: no dots,
# so no "..", no hidden name, nothing outside.
SOFFICE_PROFILE_VALUE: Final = re.compile(r"/tmp/lo-[0-9]+(?:/[A-Za-z0-9_-]+)*")  # noqa: S108 - a pattern, no file

# The torch child: its environment carries a thread count instead of OMP_THREAD_LIMIT (child_env).
DETECT_PROFILE: Final = "detect"

# The diagnosis of a failed child: how much stderr is kept while it runs, and
# how much of it may reach the log. soffice prints several harmless warnings
# (fontconfig, dconf) before the line that matters, so its tail is longer.
STDERR_KEEP_BYTES: Final = 8192
TAIL_LINES: Final = 5
SOFFICE_TAIL_LINES: Final = 12
TAIL_LINE_CHARS: Final = 160
_QUOTED: Final = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`\n]*`")
# A path or URL runs to the end of its line: a file name may hold spaces.
_URL: Final = re.compile(r"\b[a-z][a-z0-9.+-]*:/.*$", re.IGNORECASE)
_PATH: Final = re.compile(r"(?<![\w.~-])[/~].*$")
_NOT_PRINTABLE: Final = re.compile(r"[^\x20-\x7e]")


# The Python children of this package; anything else is refused.
PYTHON_CHILDREN: Final = frozenset({"render", "placeholder", "precheck", "sanitize"})


class ChildTimeout(Exception):
    """The child ran past its time limit; its whole process group was killed."""


class ChildFailed(Exception):
    """The child ended with a non-zero exit code: the code, the signal that killed it, the cleaned stderr tail."""

    def __init__(self, exit_code: int, stderr_tail: str = "") -> None:
        super().__init__(f"child exited with code {exit_code}")
        self.exit_code = exit_code
        # asyncio reports a child killed by a signal as minus the signal number.
        self.signal = -exit_code if exit_code < 0 else None
        self.stderr_tail = stderr_tail


def diagnostic_tail(raw: bytes, lines_kept: int = TAIL_LINES) -> str:
    """The last lines of stderr, safe for the log: no path, no quoted text, printable ASCII, short.

    A path can name a user file, a quoted string can quote the document, so
    both are replaced before anything is kept; a path takes the rest of its
    line with it. Lines are cut after the replacement, so a cut never leaves
    half a path behind.
    """
    text = raw.decode("utf-8", errors="replace")
    lines = []
    for line in text.splitlines():
        line = _QUOTED.sub("<q>", line)
        line = _URL.sub("<path>", line)
        line = _PATH.sub("<path>", line)
        line = _NOT_PRINTABLE.sub("?", line).strip()
        if line:
            lines.append(line[:TAIL_LINE_CHARS])
    return " | ".join(lines[-lines_kept:])


async def _keep_tail(stream: asyncio.StreamReader | None, kept: bytearray) -> None:
    """Read the stream to its end and keep only its last STDERR_KEEP_BYTES."""
    if stream is None:
        return
    while chunk := await stream.read(STDERR_KEEP_BYTES):
        kept += chunk
        del kept[: max(0, len(kept) - STDERR_KEEP_BYTES)]


def child_env(
    extra: dict[str, str] | None = None, *, profile: str | None = None, threads: int | None = None
) -> dict[str, str]:
    """SAFE_ENV plus allowlisted extras; any other key or value is a programming error.

    The SOFFICE_ENV keys pass only for the soffice profile and only with a
    value inside its job profile (SOFFICE_PROFILE_VALUE).

    detect gets no OMP_THREAD_LIMIT and instead hardware.THREADS_ENV with its
    thread count: threads, or else hardware.worker_threads() read here in the
    parent, since the jailed child cannot read cpu.max. With OMP_THREAD_LIMIT=1
    torch still planned with every core and detect never finished on arm64
    (sandbox run 44221141543, deferred-items 02-16). No caller can set the
    variable through extra, and no other profile takes a thread count.
    """
    env = dict(SAFE_ENV)
    if profile == DETECT_PROFILE:
        count = hardware.worker_threads() if threads is None else threads
        if not 1 <= count <= hardware.WORKER_THREADS_CAP:
            msg = f"the detect child takes 1 to {hardware.WORKER_THREADS_CAP} threads"
            raise ValueError(msg)
        del env["OMP_THREAD_LIMIT"]
        env[hardware.THREADS_ENV] = str(count)
    elif threads is not None:
        msg = "only the detect child takes a thread count"
        raise ValueError(msg)
    for key, value in (extra or {}).items():
        if key in SOFFICE_ENV and profile == "soffice":
            if not SOFFICE_PROFILE_VALUE.fullmatch(value):
                msg = f"environment variable {key} must name a folder inside the soffice job profile"
                raise ValueError(msg)
        elif key not in EXTRA_ALLOWED:
            msg = f"environment variable {key} is not allowed for a child"
            raise ValueError(msg)
        env[key] = value
    return env


def python_child(name: str, *args: str) -> list[str]:
    """The argument list of a Python child of this package, isolated with -I."""
    if name not in PYTHON_CHILDREN:
        msg = f"unknown child {name}"
        raise ValueError(msg)
    return [sys.executable, "-I", "-m", f"pii_redaction_backend.workers.{name}", *args]


async def run_child(
    args: list[str],
    *,
    profile: str,
    cwd: Path,
    read: tuple[str, ...] = (),
    write: tuple[str, ...] = (),
    timeout_s: float | None = None,
    extra_env: dict[str, str] | None = None,
    diagnose: bool = False,
    tail_lines: int = TAIL_LINES,
) -> None:
    """Run one child in the jail of its profile to its end, or kill its group at the time limit.

    The time limit is the wall clock of the profile unless the caller names one.
    The group is killed and collected on every way out, success included. With
    diagnose, a failure carries the cleaned tail of stderr (diagnostic_tail),
    at most tail_lines lines.
    """
    limit = profile_for(profile).wall_s if timeout_s is None else timeout_s
    process = await asyncio.create_subprocess_exec(
        *jail_argv(profile, args, read=read, write=write),
        cwd=cwd,
        env=child_env(extra_env, profile=profile),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE if diagnose else asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    kept = bytearray()
    reader = asyncio.ensure_future(_keep_tail(process.stderr, kept))
    try:
        try:
            code = await asyncio.wait_for(process.wait(), timeout=limit)
        except TimeoutError:
            _kill_group(process.pid)
            await process.wait()
            raise ChildTimeout from None
        except asyncio.CancelledError:
            _kill_group(process.pid)
            await process.wait()
            raise
    finally:
        reap_group(process.pid)
        # The group is gone, so the pipe is closed; the wait is only a guard.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(reader), timeout=2)
        reader.cancel()
    if code != 0:
        raise ChildFailed(code, diagnostic_tail(bytes(kept), tail_lines) if diagnose else "")


def _kill_group(pid: int) -> None:
    """SIGKILL to the whole group the child leads; it may already be gone."""
    if sys.platform == "win32":
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def peak_child_rss_kb() -> int:
    """The highest resident set of any finished child so far, in KiB (Linux ru_maxrss unit)."""
    if sys.platform == "win32":
        return 0
    import resource

    return int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
