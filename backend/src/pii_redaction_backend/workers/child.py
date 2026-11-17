"""Run work on foreign files in a child process that holds no secret.

Rendering, conversion and the placeholder PDF touch user documents with C
code (MuPDF, LibreOffice). They never run in the server process; each runs as
a child with:

- an empty environment plus a fixed allowlist: no APP_SECRET, APP_ID,
  NEXTCLOUD_URL, AA_VERSION or APP_PERSISTENT_STORAGE reaches it,
- its own process group (start_new_session), so a time limit kills the child
  and everything it started, not just the first process,
- stdin, stdout and stderr on DEVNULL: nothing a parser prints can reach a log.

Every child starts through the jail (sandbox/jail.py): the profile of its
kind sets rlimits, NO_NEW_PRIVS, Landlock and seccomp before the real program
runs. After every child, whatever the outcome, sandbox/reaper.py kills and
collects the rest of its group, so no grandchild and no zombie stays behind.

Only the exit code and the files in the work folder come back.
"""

import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Final

from pii_redaction_backend.sandbox.jail import jail_argv
from pii_redaction_backend.sandbox.profiles import profile_for
from pii_redaction_backend.sandbox.reaper import reap_group

SAFE_ENV: Final[dict[str, str]] = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",  # noqa: S108 - the child's home is a throwaway, its profile lives below the job folder
    "LANG": "C.UTF-8",
    "OMP_THREAD_LIMIT": "1",
    # One malloc arena per process (Pitfall 8); mallopt in the jail would not
    # survive execv, the environment does.
    "MALLOC_ARENA_MAX": "1",
}

# The only extra variables a caller may hand to a child.
EXTRA_ALLOWED: Final = frozenset({"TESSDATA_PREFIX", "SAL_USE_VCLPLUGIN"})

# The Python children of this package; anything else is refused.
PYTHON_CHILDREN: Final = frozenset({"render", "placeholder", "precheck", "sanitize"})


class ChildTimeout(Exception):
    """The child ran past its time limit; its whole process group was killed."""


class ChildFailed(Exception):
    """The child ended with a non-zero exit code. Carries the code and nothing else."""

    def __init__(self, exit_code: int) -> None:
        super().__init__(f"child exited with code {exit_code}")
        self.exit_code = exit_code


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """SAFE_ENV plus allowlisted extras; any other key is a programming error."""
    env = dict(SAFE_ENV)
    for key, value in (extra or {}).items():
        if key not in EXTRA_ALLOWED:
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
) -> None:
    """Run one child in the jail of its profile to its end, or kill its group at the time limit.

    The time limit is the wall clock of the profile unless the caller names one.
    The group is killed and collected on every way out, success included.
    """
    limit = profile_for(profile).wall_s if timeout_s is None else timeout_s
    process = await asyncio.create_subprocess_exec(
        *jail_argv(profile, args, read=read, write=write),
        cwd=cwd,
        env=child_env(extra_env),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
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
    if code != 0:
        raise ChildFailed(code)


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
