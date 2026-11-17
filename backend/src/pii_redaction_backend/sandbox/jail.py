"""The start program of every child: limits and locks first, then the real program.

A child never starts directly. run_child starts

    python -I -m pii_redaction_backend.sandbox.jail <profile> [--read P] [--write P] -- <command...>

as a fresh, single-threaded process in its own session. The jail sets the
budget of the profile and the protection layers, in this order, and then
replaces itself with the command through os.execv:

1. rlimits of the profile: CPU seconds, largest file, open files, address
   space (when the profile has one) and always a core size of 0, so a crashing
   parser leaves no memory image with document content behind;
2. PR_SET_NO_NEW_PRIVS, so no set-uid program can gain rights later;
3. Landlock: read only the system paths of the profile plus the job paths,
   write only the job paths, and create a Unix socket only in the socket
   paths of the profile (LibreOffice: /tmp, nothing else);
4. seccomp: no INET, INET6, PACKET or NETLINK socket, no ptrace and friends.

Why not preexec_fn: the server runs asyncio plus worker threads, and CPython
documents preexec_fn as unsafe in the presence of threads. A ctypes call into
libseccomp after fork can hang on a malloc lock another thread held at the
moment of the fork. A separate start program has only one thread.

Why no RLIMIT_NPROC: the kernel counts it for the real uid across the whole
host, and Findling, AV and this app all run as uid 10001; a limit for one
child would make children of the other apps fail at random. A fork flood ends
at the group kill and the wall clock in the server.

A layer the kernel does not offer (no Landlock ABI, no libseccomp) is skipped
(D-02-05, D-02-11; the probe of plan 02-14 makes that visible). A layer that
is offered but fails to load ends the jail with exit 71 and the command does
not start: fail closed. Exit 2 is a call error. The jail prints nothing and
logs nothing; the environment it hands on is the empty one run_child gave it.
"""

import os
import posixpath
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from pii_redaction_backend.sandbox import landlock, seccomp
from pii_redaction_backend.sandbox.profiles import PROFILES, Profile, profile_for

MODULE: Final = "pii_redaction_backend.sandbox.jail"
EXIT_USAGE: Final = 2
EXIT_LAYER_FAILED: Final = 71
PR_SET_NO_NEW_PRIVS: Final = 38

# The persistent volume holds state.db and the files of other jobs; a child
# may only write below its work folder.
DATA_ROOT: Final = "/nc_app_pii_redaction_backend_data"
WORK_ROOT: Final = f"{DATA_ROOT}/work"


@dataclass(frozen=True, slots=True)
class Ops:
    """Every system call the jail makes, replaceable for the tests."""

    setrlimit: Callable[[str, tuple[int, int]], None]
    prctl: Callable[[int, int], None]
    landlock_abi: Callable[[], int]
    landlock_restrict: Callable[[tuple[str, ...], tuple[str, ...], tuple[str, ...]], object]
    seccomp_available: Callable[[], bool]
    seccomp_install: Callable[[], None]
    execv: Callable[[str, list[str]], object]


@dataclass(frozen=True, slots=True)
class Call:
    """One parsed jail call."""

    profile: Profile
    read: tuple[str, ...]
    write: tuple[str, ...]
    command: list[str]


def jail_argv(profile: str, args: list[str], *, read: tuple[str, ...] = (), write: tuple[str, ...] = ()) -> list[str]:
    """The argument list that starts args inside the jail of this profile."""
    profile_for(profile)
    paths: list[str] = []
    for path in read:
        paths += ["--read", path]
    for path in write:
        paths += ["--write", path]
    return [sys.executable, "-I", "-m", MODULE, profile, *paths, "--", *args]


def _outside_work(path: str) -> bool:
    """A write path on the persistent volume that is not below work/."""
    normal = posixpath.normpath(path)
    on_volume = normal == DATA_ROOT or normal.startswith(f"{DATA_ROOT}/")
    below_work = normal.startswith(f"{WORK_ROOT}/")
    return on_volume and not below_work


def parse(argv: list[str]) -> Call | None:
    """The call, or None for any malformed argument list."""
    if not argv or argv[0] not in PROFILES or "--" not in argv:
        return None
    split = argv.index("--")
    options, command = argv[1:split], argv[split + 1 :]
    read: list[str] = []
    write: list[str] = []
    if len(options) % 2:
        return None
    for flag, path in zip(options[::2], options[1::2], strict=True):
        if not path.startswith("/"):
            return None
        if flag == "--read":
            read.append(path)
        elif flag == "--write":
            if _outside_work(path):
                return None
            write.append(path)
        else:
            return None
    if not command or not command[0].startswith("/"):
        return None
    return Call(profile=profile_for(argv[0]), read=tuple(read), write=tuple(write), command=command)


def limits(profile: Profile) -> list[tuple[str, tuple[int, int]]]:
    """The rlimits of a profile, by resource name; never RLIMIT_NPROC."""
    plan: list[tuple[str, tuple[int, int]]] = [
        ("RLIMIT_CPU", (profile.cpu_s, profile.cpu_s)),
        ("RLIMIT_FSIZE", (profile.file_size, profile.file_size)),
        ("RLIMIT_NOFILE", (profile.open_files, profile.open_files)),
    ]
    if profile.address_space is not None:
        plan.append(("RLIMIT_AS", (profile.address_space, profile.address_space)))
    plan.append(("RLIMIT_CORE", (profile.core, profile.core)))
    return plan


def run(call: Call, ops: Ops) -> int:
    """Apply every layer in order and exec the command; returns only on failure."""
    try:
        for name, value in limits(call.profile):
            ops.setrlimit(name, value)
        ops.prctl(PR_SET_NO_NEW_PRIVS, 1)
        if ops.landlock_abi() > 0:
            ops.landlock_restrict(
                (*call.profile.read_paths, *call.read),
                (*call.profile.write_paths, *call.write),
                call.profile.socket_paths,
            )
        if ops.seccomp_available():
            ops.seccomp_install()
    except (OSError, ValueError):
        return EXIT_LAYER_FAILED
    try:
        ops.execv(call.command[0], call.command)
    except OSError:
        return EXIT_LAYER_FAILED
    return EXIT_LAYER_FAILED


def _setrlimit(name: str, value: tuple[int, int]) -> None:
    if sys.platform == "win32":
        raise OSError(0, "no rlimits on Windows")
    import resource

    resource.setrlimit(getattr(resource, name), value)


def _prctl(option: int, value: int) -> None:
    import ctypes

    libc: Any = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(option, value, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl failed")


def _landlock_abi() -> int:
    return landlock.abi_version()


def _landlock_restrict(read: tuple[str, ...], write: tuple[str, ...], sockets: tuple[str, ...]) -> object:
    return landlock.restrict(read, write, socket_paths=sockets)


def _seccomp_available() -> bool:
    return seccomp.available()


def _seccomp_install() -> None:
    seccomp.install_network_denylist()


def system_ops() -> Ops:
    """The real system calls (Linux)."""
    return Ops(
        setrlimit=_setrlimit,
        prctl=_prctl,
        landlock_abi=_landlock_abi,
        landlock_restrict=_landlock_restrict,
        seccomp_available=_seccomp_available,
        seccomp_install=_seccomp_install,
        execv=os.execv,
    )


def main(argv: list[str], ops: Ops | None = None) -> int:
    call = parse(argv)
    if call is None:
        return EXIT_USAGE
    if ops is None:
        if not sys.platform.startswith("linux"):
            # No rlimits, no prctl: a child without its budget never starts.
            return EXIT_LAYER_FAILED
        ops = system_ops()
    return run(call, ops)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
