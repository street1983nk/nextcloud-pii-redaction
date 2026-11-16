"""Landlock file rules for a child, through the three system calls (D-02-05, T-02-01, T-02-02).

No PyPI package: the only one is a development release with one maintainer
(RESEARCH, alternatives). The calls are 444 (create_ruleset), 445 (add_rule)
and 446 (restrict_self), the same number on amd64 and arm64.

The ruleset handles every file right the running kernel knows (its ABI), so a
right that is not granted below a listed path is denied everywhere else. From
ABI 4 on, TCP bind and connect are handled without any port rule, so both are
denied. From ABI 6 on, abstract Unix sockets and signals to processes outside
the domain are scoped away. A Landlock domain also blocks ptrace on processes
outside it, which closes the /proc/1/environ way to APP_SECRET.

abi_version() is the probe: ENOSYS, EOPNOTSUPP or EINVAL (no Landlock in this
kernel or switched off at boot), or no Linux at all, answer 0 instead of
raising. restrict() runs after a positive probe and raises on any failure
(fail closed). It does not set no_new_privs; the jail does that before
(plan 02-08), as landlock_restrict_self requires.
"""

import ctypes
import errno
import os
import stat
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

SYS_CREATE_RULESET: Final = 444
SYS_ADD_RULE: Final = 445
SYS_RESTRICT_SELF: Final = 446
CREATE_RULESET_VERSION: Final = 1
RULE_PATH_BENEATH: Final = 1

ACCESS_FS_EXECUTE: Final = 1 << 0
ACCESS_FS_WRITE_FILE: Final = 1 << 1
ACCESS_FS_READ_FILE: Final = 1 << 2
ACCESS_FS_READ_DIR: Final = 1 << 3
ACCESS_FS_REMOVE_DIR: Final = 1 << 4
ACCESS_FS_REMOVE_FILE: Final = 1 << 5
ACCESS_FS_MAKE_CHAR: Final = 1 << 6
ACCESS_FS_MAKE_DIR: Final = 1 << 7
ACCESS_FS_MAKE_REG: Final = 1 << 8
ACCESS_FS_MAKE_SOCK: Final = 1 << 9
ACCESS_FS_MAKE_FIFO: Final = 1 << 10
ACCESS_FS_MAKE_BLOCK: Final = 1 << 11
ACCESS_FS_MAKE_SYM: Final = 1 << 12
ACCESS_FS_REFER: Final = 1 << 13  # ABI 2
ACCESS_FS_TRUNCATE: Final = 1 << 14  # ABI 3
ACCESS_FS_IOCTL_DEV: Final = 1 << 15  # ABI 5

ACCESS_NET_BIND_TCP: Final = 1 << 0  # ABI 4
ACCESS_NET_CONNECT_TCP: Final = 1 << 1  # ABI 4

SCOPE_ABSTRACT_UNIX_SOCKET: Final = 1 << 0  # ABI 6
SCOPE_SIGNAL: Final = 1 << 1  # ABI 6

_FS_ABI_1: Final = (1 << 13) - 1

READ_ACCESS: Final = ACCESS_FS_READ_FILE | ACCESS_FS_READ_DIR | ACCESS_FS_EXECUTE
WRITE_ACCESS: Final = (
    READ_ACCESS
    | ACCESS_FS_WRITE_FILE
    | ACCESS_FS_REMOVE_DIR
    | ACCESS_FS_REMOVE_FILE
    | ACCESS_FS_MAKE_DIR
    | ACCESS_FS_MAKE_REG
    | ACCESS_FS_MAKE_SOCK
    | ACCESS_FS_MAKE_FIFO
    | ACCESS_FS_MAKE_SYM
    | ACCESS_FS_TRUNCATE
)
# The only rights the kernel accepts on a rule for a file (not a directory).
FILE_ACCESS: Final = (
    ACCESS_FS_EXECUTE | ACCESS_FS_WRITE_FILE | ACCESS_FS_READ_FILE | ACCESS_FS_TRUNCATE | ACCESS_FS_IOCTL_DEV
)

# Linux values; os.O_PATH exists on Linux only, the fallback keeps the module importable elsewhere.
_O_PATH: Final[int] = getattr(os, "O_PATH", 0o10000000)
_O_CLOEXEC: Final[int] = getattr(os, "O_CLOEXEC", 0o2000000)

_UNAVAILABLE: Final = frozenset({errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL})

# A system call: number and arguments in, result or minus errno out (kernel convention).
Syscall = Callable[..., int]


class RulesetAttr(ctypes.Structure):
    """struct landlock_ruleset_attr; the size handed to the kernel shrinks with the ABI."""

    _fields_ = (
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    )


class PathBeneathAttr(ctypes.Structure):
    """struct landlock_path_beneath_attr (packed)."""

    _pack_ = 1
    _fields_ = (("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32))


@dataclass(frozen=True, slots=True)
class Handled:
    """What a ruleset of one ABI handles: file rights, network rights, scopes."""

    fs: int
    net: int
    scoped: int


def handled_access(abi: int) -> Handled:
    """Everything this ABI can restrict, cumulative."""
    fs = _FS_ABI_1
    if abi >= 2:
        fs |= ACCESS_FS_REFER
    if abi >= 3:
        fs |= ACCESS_FS_TRUNCATE
    if abi >= 5:
        fs |= ACCESS_FS_IOCTL_DEV
    net = ACCESS_NET_BIND_TCP | ACCESS_NET_CONNECT_TCP if abi >= 4 else 0
    scoped = SCOPE_ABSTRACT_UNIX_SOCKET | SCOPE_SIGNAL if abi >= 6 else 0
    return Handled(fs=fs, net=net, scoped=scoped)


def _attr_size(abi: int) -> int:
    if abi >= 6:
        return 24
    if abi >= 4:
        return 16
    return 8


def _libc_syscall() -> Syscall | None:
    if not sys.platform.startswith("linux"):
        return None
    libc = ctypes.CDLL(None, use_errno=True)
    raw = libc.syscall
    raw.restype = ctypes.c_long

    def call(number: int, *args: object) -> int:
        wrapped = [ctypes.c_long(arg) if isinstance(arg, int) else arg for arg in args]
        result = raw(ctypes.c_long(number), *wrapped)
        return -ctypes.get_errno() if result == -1 else result

    return call


def abi_version(syscall: Syscall | None = None) -> int:
    """The Landlock ABI of this kernel, 0 when there is none; never raises for a missing Landlock."""
    if syscall is None:
        syscall = _libc_syscall()
    if syscall is None:
        return 0
    result = syscall(SYS_CREATE_RULESET, None, 0, CREATE_RULESET_VERSION)
    if result < 0:
        if -result in _UNAVAILABLE:
            return 0
        raise OSError(-result, os.strerror(-result))
    return result


def _fail(result: int, what: str) -> OSError:
    return OSError(-result, f"{what}: {os.strerror(-result)}")


def _add_paths(syscall: Syscall, ruleset: int, paths: Iterable[str], access: int) -> None:
    for path in paths:
        try:
            fd = os.open(path, _O_PATH | _O_CLOEXEC)
        except FileNotFoundError:
            continue
        try:
            allowed = access if stat.S_ISDIR(os.fstat(fd).st_mode) else access & FILE_ACCESS
            rule = PathBeneathAttr(allowed, fd)
            result = syscall(SYS_ADD_RULE, ruleset, RULE_PATH_BENEATH, ctypes.pointer(rule), 0)
            if result < 0:
                raise _fail(result, "landlock_add_rule")
        finally:
            os.close(fd)


def restrict(read_paths: Iterable[str], write_paths: Iterable[str], syscall: Syscall | None = None) -> int:
    """Confine this process and every later exec to the given paths; returns the ABI used."""
    if syscall is None:
        syscall = _libc_syscall()
    if syscall is None:
        raise OSError(errno.ENOSYS, "Landlock needs Linux")
    abi = abi_version(syscall)
    if abi == 0:
        raise OSError(errno.ENOSYS, "Landlock not available")
    handled = handled_access(abi)
    attr = RulesetAttr(handled.fs, handled.net, handled.scoped)
    ruleset = syscall(SYS_CREATE_RULESET, ctypes.pointer(attr), _attr_size(abi), 0)
    if ruleset < 0:
        raise _fail(ruleset, "landlock_create_ruleset")
    try:
        _add_paths(syscall, ruleset, read_paths, READ_ACCESS & handled.fs)
        _add_paths(syscall, ruleset, write_paths, WRITE_ACCESS & handled.fs)
        result = syscall(SYS_RESTRICT_SELF, ruleset, 0)
        if result < 0:
            raise _fail(result, "landlock_restrict_self")
    finally:
        os.close(ruleset)
    return abi
