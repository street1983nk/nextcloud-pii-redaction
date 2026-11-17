"""Kill and collect the whole process group of a finished child (RESEARCH Pattern 2).

The server is PID 1 in the container (HaRP starts no init), so every grandchild
a child leaves behind becomes a child of the server when its parent dies. If
nobody collects it, it stays as a zombie; LibreOffice does that with
soffice.bin when oosplash ends first.

After every child, success or not, run_child calls reap_group: SIGKILL to the
whole group, then waitpid(-pgid, WNOHANG) until the group has no child of ours
left. A wait for any child (pid -1) is never used: it could take the status of a child that
asyncio is waiting for. become_subreaper makes the server the collector of
orphans also outside the container (tests, a host with an init).
"""

import contextlib
import os
import signal
import sys
import time
from typing import Final

PR_SET_CHILD_SUBREAPER: Final = 36
# A killed process needs a moment to become collectable; the wait is bounded.
SETTLE_S: Final = 1.0
POLL_S: Final = 0.01


def reap_group(pgid: int) -> None:
    """SIGKILL to the group, then collect every member that is our child."""
    if sys.platform == "win32":
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)
    deadline = time.monotonic() + SETTLE_S
    while True:
        try:
            pid, _ = os.waitpid(-pgid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            if time.monotonic() >= deadline:
                return
            time.sleep(POLL_S)


def become_subreaper() -> bool:
    """Make this process the collector of orphaned descendants (Linux only)."""
    if not sys.platform.startswith("linux"):
        return False
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    return libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
