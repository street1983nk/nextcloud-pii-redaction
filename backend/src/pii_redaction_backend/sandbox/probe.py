"""What the sandbox can do on this host, asked once at the start (RESEARCH Pitfall 3, D-02-05, D-02-11).

Podman, gVisor, old kernels or a custom Docker profile may lack seccomp or
Landlock. The server starts anyway, but the state must be visible instead of
silent: the probe asks both layers and runs the jail once with /bin/true, and
/status carries the answer as fixed words and one number.

Exit 71 of a child later means "a layer was offered but could not be loaded"
(sandbox/jail.py). The job ends as render_failed and nothing in the job says
why; mark_jail_failed() turns the state to jail failed for good, so the admin
sees it in /status and in the admin notice of plan 02-20. The runner calls it
on ChildFailed(71) (plan 02-19). The log line names the word, never a path or
a job.
"""

import dataclasses
import logging
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pii_redaction_backend import APP_ID, config
from pii_redaction_backend.sandbox import landlock, seccomp
from pii_redaction_backend.workers.child import ChildFailed, ChildTimeout, run_child

LOGGER = logging.getLogger(APP_ID)

ACTIVE: Final = "active"
UNAVAILABLE: Final = "unavailable"
JAIL_OK: Final = "ok"
JAIL_FAILED: Final = "failed"
PROBE_COMMAND: Final = ("/bin/true",)
PROBE_PROFILE: Final = "precheck"


@dataclass(frozen=True, slots=True)
class SandboxState:
    """The protection layers of this host, in fixed words."""

    seccomp: str
    landlock: str
    landlock_abi: int
    jail: str


_STATE: dict[str, SandboxState] = {}


def current() -> SandboxState | None:
    """The last probe result, or None before the first probe."""
    return _STATE.get("state")


def _probe_folder() -> Path:
    # Below work/: the jail refuses any other write path on the volume.
    root = config.storage_root() / "work"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="probe-", dir=root))


async def run(
    *,
    seccomp_available: Callable[[], bool] = seccomp.available,
    landlock_abi: Callable[[], int] = landlock.abi_version,
    runner: Callable[..., Awaitable[None]] = run_child,
) -> SandboxState:
    """Ask both layers and run the jail once; never raises for a missing layer."""
    try:
        abi = max(0, int(landlock_abi()))
    except OSError:
        abi = 0
    folder = _probe_folder()
    try:
        await runner(list(PROBE_COMMAND), profile=PROBE_PROFILE, cwd=folder, write=(str(folder),))
        jail = JAIL_OK
    except (ChildFailed, ChildTimeout, OSError, ValueError):
        jail = JAIL_FAILED
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    state = SandboxState(
        seccomp=ACTIVE if seccomp_available() else UNAVAILABLE,
        landlock=ACTIVE if abi > 0 else UNAVAILABLE,
        landlock_abi=abi,
        jail=jail,
    )
    _STATE["state"] = state
    return state


def mark_jail_failed() -> None:
    """A child ended with exit 71: the jail stays failed in /status from now on."""
    before = current()
    if before is None:
        _STATE["state"] = SandboxState(seccomp=UNAVAILABLE, landlock=UNAVAILABLE, landlock_abi=0, jail=JAIL_FAILED)
    elif before.jail == JAIL_FAILED:
        return
    else:
        _STATE["state"] = dataclasses.replace(before, jail=JAIL_FAILED)
    LOGGER.error("jail layer failed", extra={"jail": JAIL_FAILED})
