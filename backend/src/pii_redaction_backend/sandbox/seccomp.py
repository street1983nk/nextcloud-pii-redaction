"""A seccomp filter that takes the network away from a child (D-02-05, T-02-04).

The filter goes through libseccomp (ctypes, no hand written BPF): the library
resolves the system call numbers for amd64 and arm64 itself, and a foreign
architecture (x32, i386 on amd64) gets its default action for a bad
architecture, which kills the process.

Default action ALLOW; ERRNO(EACCES) for socket() in the IPv4, IPv6, packet and
netlink domains and for ten calls a parser never needs but an attacker would
(reading other processes, io_uring, BPF, kernel keys). AF_UNIX stays open,
LibreOffice talks to itself through a Unix socket.

A profile may also refuse connect() itself with EACCES, for every address
family (deny_connect). LibreOffice gets this (owner decision 17.11., secure-phase
finding SOCKET-CONNECT): without it soffice could reach any Unix socket it can
see, the HaRP socket of the server included. soffice still converts, because it
binds its own single-instance pipe and only tries connect() to find an earlier
instance (sandbox run of 11fb9f9: no-landlock,seccomp,deny-connect converts on
amd64 and arm64).

available() is the probe: no Linux, no libseccomp or a context that cannot be
created means "unavailable", reported as False, never raised. Once the probe
said yes, every non-zero return of libseccomp raises OSError: a filter that
was meant to load and did not must stop the child (fail closed).
"""

import ctypes
import errno
import os
import sys
from typing import Any, Final

SCMP_ACT_ALLOW: Final = 0x7FFF0000
_SCMP_ACT_ERRNO: Final = 0x00050000
SCMP_CMP_EQ: Final = 4
# What seccomp_syscall_resolve_name answers for a name it does not know.
_NR_SCMP_ERROR: Final = -1

AF_INET: Final = 2
AF_INET6: Final = 10
AF_NETLINK: Final = 16
AF_PACKET: Final = 17

# socket() is refused for these domains; AF_UNIX (1) is deliberately absent.
DENIED_DOMAINS: Final[tuple[int, ...]] = (AF_INET, AF_INET6, AF_PACKET, AF_NETLINK)

# Refused without any argument condition.
DENIED_SYSCALLS: Final[tuple[str, ...]] = (
    "ptrace",
    "process_vm_readv",
    "process_vm_writev",
    "io_uring_setup",
    "bpf",
    "perf_event_open",
    "userfaultfd",
    "keyctl",
    "add_key",
    "request_key",
)


class ScmpArgCmp(ctypes.Structure):
    """struct scmp_arg_cmp of seccomp.h."""

    _fields_ = (
        ("arg", ctypes.c_uint),
        ("op", ctypes.c_int),
        ("datum_a", ctypes.c_uint64),
        ("datum_b", ctypes.c_uint64),
    )


def errno_action(code: int) -> int:
    """SCMP_ACT_ERRNO(code): the call fails with this errno instead of running."""
    return _SCMP_ACT_ERRNO | (code & 0xFFFF)


def _load() -> Any:
    """libseccomp with typed entry points, or None off Linux or without the library."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError:
        return None
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_init.argtypes = (ctypes.c_uint32,)
    lib.seccomp_release.restype = None
    lib.seccomp_release.argtypes = (ctypes.c_void_p,)
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_syscall_resolve_name.argtypes = (ctypes.c_char_p,)
    lib.seccomp_rule_add_exact_array.restype = ctypes.c_int
    lib.seccomp_rule_add_exact_array.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(ScmpArgCmp),
    )
    lib.seccomp_load.restype = ctypes.c_int
    lib.seccomp_load.argtypes = (ctypes.c_void_p,)
    return lib


def available(lib: Any = None) -> bool:
    """Whether a filter can be built here; never raises."""
    if lib is None:
        lib = _load()
    if lib is None:
        return False
    try:
        context = lib.seccomp_init(SCMP_ACT_ALLOW)
    except OSError:
        return False
    if not context:
        return False
    lib.seccomp_release(context)
    return True


def _check(code: int) -> None:
    if code != 0:
        number = -code if code < 0 else errno.EINVAL
        raise OSError(number, os.strerror(number))


def _resolve(lib: Any, name: str) -> int:
    number = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
    if number == _NR_SCMP_ERROR:
        raise OSError(errno.ENOSYS, f"system call {name} unknown to libseccomp")
    return number


def install_network_denylist(lib: Any = None, *, deny_connect: bool = False) -> None:
    """Load the filter into this process; it holds for every later exec. Raises on any failure.

    deny_connect adds connect() -> EACCES without any argument condition, so
    every address family (Unix, IPv4, IPv6, ...) is refused.
    """
    if lib is None:
        lib = _load()
    if lib is None:
        raise OSError(errno.ENOSYS, "libseccomp not available")
    context = lib.seccomp_init(SCMP_ACT_ALLOW)
    if not context:
        raise OSError(errno.ENOMEM, "seccomp_init failed")
    try:
        refuse = errno_action(errno.EACCES)
        socket_nr = _resolve(lib, "socket")
        for domain in DENIED_DOMAINS:
            condition = (ScmpArgCmp * 1)(ScmpArgCmp(0, SCMP_CMP_EQ, domain, 0))
            _check(lib.seccomp_rule_add_exact_array(context, refuse, socket_nr, 1, condition))
        for name in DENIED_SYSCALLS:
            _check(lib.seccomp_rule_add_exact_array(context, refuse, _resolve(lib, name), 0, None))
        if deny_connect:
            _check(lib.seccomp_rule_add_exact_array(context, refuse, _resolve(lib, "connect"), 0, None))
        _check(lib.seccomp_load(context))
    finally:
        lib.seccomp_release(context)
