"""Test-only start program for the LibreOffice diagnosis of plan 02-16; never part of the product.

The product starts every child through sandbox/jail.py with all layers. To
find the layer, and inside Landlock the one path or right, under which
soffice stops working, test_container_soffice.py starts the same soffice call
through this program:

    python -I jail_layers.py layers limits   <jail arguments>   rlimits, no_new_privs
    python -I jail_layers.py layers landlock <jail arguments>   the same plus Landlock

<jail arguments> are exactly what jail.main takes (profile, --read/--write,
--, command). The layers run in the order and with the code of the product
(jail.run with jail.system_ops); only the probe of the left-out layers
answers "not available". The full product jail (plus seccomp) needs no
helper, the test starts it through jail.jail_argv.

    python -I jail_layers.py variant <spec>[,<spec>...] <jail arguments>

runs rlimits, no_new_privs and the Landlock rules of the product with
exactly the changes the specs name (VARIANT_SPECS), then execs the command.
A variant is a measurement in the test run, never a rule of the product:
the product rules live in sandbox/profiles.py and sandbox/landlock.py and
nothing here changes them.

    python -I jail_layers.py deny-connect <jail arguments>

is the full product jail of the profile (all layers, the code of jail.run),
with exactly one change: Profile.deny_connect is True, so seccomp refuses
connect() for every family as the product does for soffice, render, precheck
and sanitize. Risk R2 of plan 02-16: does the work of ocr and detect still
run when the child can reach no socket? (render, precheck and sanitize were
measured in the sandbox run of df2d2e5 and switched by the owner on 17.11.)
The profiles themselves are not touched.

    python -I jail_layers.py abi       prints abi=<Landlock ABI> kernel=<release>
    python -I jail_layers.py connect <socket path>

tries to connect a Unix stream socket (secure-phase measurement: may a child
reach the HaRP socket of the server?) and prints ok, refused <errno> or absent.

    python -I jail_layers.py unlink <path>
    python -I jail_layers.py access <path>

unlink removes one path and prints ok, the errno name (EACCES, EPERM, ...) or
absent (round 3: may a soffice child with REMOVE_FILE on /tmp remove a file of
the server?). The test only ever names a stand-in it made itself, never the
HaRP socket. access asks access(path, W_OK) and prints ok or the errno name
(round 3: does Landlock answer access(2)? sal/osl/unx/pipe.cxx picks the pipe
folder by it).
"""

import ctypes
import errno
import os
import platform
import socket
import sys
from dataclasses import replace
from functools import partial

from pii_redaction_backend.sandbox import jail, landlock, seccomp

PARTIAL_LAYERS = ("limits", "landlock")

# Landlock audit (Linux 6.15, ABI 7): flags of landlock_restrict_self. By
# default a denial is logged only before the next exec; soffice runs after
# the exec of the jail, so the variant "audit" asks for LOG_NEW_EXEC_ON.
AUDIT_ABI = 7
RESTRICT_SELF_LOG_NEW_EXEC_ON = 1 << 1

# What a spec may say. "read=<path>" and "write=<path>" take one absolute path.
#   read=P       P readable (read file, read dir, execute) on top of the product rules
#   write=P      P writable like a job path on top of the product rules
#   refer        the write paths also get REFER (rename/link across folders, ABI 2)
#   ioctl        the read paths also get IOCTL_DEV (ABI 5)
#   nosock       no socket rule (the product grants MAKE_SOCK below /tmp)
#   net-off      the ruleset does not handle TCP bind/connect (ABI 4)
#   scope-off    the ruleset does not scope abstract sockets and signals (ABI 6)
#   fs-all       every file right the ABI knows, granted on / (bisection: is it a file right at all?)
#   audit        product rules, denials logged to the kernel audit (ABI 7, see AUDIT_ABI)
#   no-landlock  no Landlock at all
#   seccomp      the seccomp filter of the product on top
#   deny-connect an extra seccomp filter: connect() fails with EACCES, every family
#   grant=P:R+R  exactly the Landlock rights R (names of GRANT_RIGHTS) on P on top of
#                the product rules, nothing else: write=/tmp split into its rights
FLAG_SPECS = frozenset(
    {"refer", "ioctl", "nosock", "net-off", "scope-off", "fs-all", "audit", "no-landlock", "seccomp", "deny-connect"}
)
PATH_SPECS = ("read", "write")
GRANT_SPEC = "grant"
# The rights a grant= spec may name. READ is the read set of the product
# (READ_FILE, READ_DIR, EXECUTE) in one word.
GRANT_RIGHTS = {
    "READ": landlock.READ_ACCESS,
    "READ_FILE": landlock.ACCESS_FS_READ_FILE,
    "READ_DIR": landlock.ACCESS_FS_READ_DIR,
    "EXECUTE": landlock.ACCESS_FS_EXECUTE,
    "WRITE_FILE": landlock.ACCESS_FS_WRITE_FILE,
    "TRUNCATE": landlock.ACCESS_FS_TRUNCATE,
    "MAKE_DIR": landlock.ACCESS_FS_MAKE_DIR,
    "MAKE_REG": landlock.ACCESS_FS_MAKE_REG,
    "MAKE_SOCK": landlock.ACCESS_FS_MAKE_SOCK,
    "MAKE_FIFO": landlock.ACCESS_FS_MAKE_FIFO,
    "MAKE_SYM": landlock.ACCESS_FS_MAKE_SYM,
    "REMOVE_FILE": landlock.ACCESS_FS_REMOVE_FILE,
    "REMOVE_DIR": landlock.ACCESS_FS_REMOVE_DIR,
    "REFER": landlock.ACCESS_FS_REFER,
}


def parse_grant(value: str) -> tuple[str, int] | None:
    """The path and the rights of a grant= value "P:R+R", or None when malformed."""
    path, has_rights, names = value.rpartition(":")
    if not has_rights or not path.startswith("/") or not names:
        return None
    rights = 0
    for name in names.split("+"):
        if name not in GRANT_RIGHTS:
            return None
        rights |= GRANT_RIGHTS[name]
    return path, rights


def _no_landlock() -> int:
    return 0


def _no_seccomp() -> bool:
    return False


def layered_ops(layer: str) -> jail.Ops:
    """The system calls of the product jail with the layers above `layer` switched off."""
    ops = jail.system_ops()
    if layer == "limits":
        return replace(ops, landlock_abi=_no_landlock, seccomp_available=_no_seccomp)
    if layer == "landlock":
        return replace(ops, seccomp_available=_no_seccomp)
    msg = f"unknown layer {layer!r}"
    raise ValueError(msg)


def parse_specs(text: str) -> tuple[str, ...] | None:
    """The specs of one variant, or None for an unknown or malformed one."""
    specs = tuple(part for part in text.split(",") if part)
    for spec in specs:
        key, has_value, value = spec.partition("=")
        if has_value and key == GRANT_SPEC:
            if parse_grant(value) is None:
                return None
        elif has_value:
            if key not in PATH_SPECS or not value.startswith("/"):
                return None
        elif spec not in FLAG_SPECS:
            return None
    return specs or None


def _paths(specs: tuple[str, ...], key: str) -> tuple[str, ...]:
    return tuple(spec.split("=", 1)[1] for spec in specs if spec.startswith(f"{key}="))


def _grants(specs: tuple[str, ...]) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for spec in specs:
        if spec.startswith(f"{GRANT_SPEC}="):
            grant = parse_grant(spec.split("=", 1)[1])
            if grant is None:
                msg = f"malformed grant spec {spec!r}"
                raise ValueError(msg)
            found.append(grant)
    return found


def restrict_variant(
    specs: tuple[str, ...],
    read: tuple[str, ...],
    write: tuple[str, ...],
    sockets: tuple[str, ...],
    syscall: landlock.Syscall | None = None,
) -> int:
    """landlock.restrict with the product rules plus exactly the changes of specs; returns the ABI."""
    if syscall is None:
        syscall = landlock._libc_syscall()
    if syscall is None:
        raise OSError(errno.ENOSYS, "Landlock needs Linux")
    abi = landlock.abi_version(syscall)
    if abi == 0:
        raise OSError(errno.ENOSYS, "Landlock not available")
    handled = landlock.handled_access(abi)
    net = 0 if "net-off" in specs else handled.net
    scoped = 0 if "scope-off" in specs else handled.scoped
    read_access = landlock.READ_ACCESS & handled.fs
    write_access = landlock.WRITE_ACCESS & handled.fs
    if "refer" in specs:
        write_access |= landlock.ACCESS_FS_REFER & handled.fs
    if "ioctl" in specs:
        read_access |= landlock.ACCESS_FS_IOCTL_DEV & handled.fs
    flags = 0
    if "audit" in specs:
        if abi < AUDIT_ABI:
            raise OSError(errno.EOPNOTSUPP, f"Landlock audit needs ABI {AUDIT_ABI}, this kernel has {abi}")
        flags = RESTRICT_SELF_LOG_NEW_EXEC_ON
    attr = landlock.RulesetAttr(handled.fs, net, scoped)
    ruleset = syscall(landlock.SYS_CREATE_RULESET, ctypes.pointer(attr), landlock._attr_size(abi), 0)
    if ruleset < 0:
        raise landlock._fail(ruleset, "landlock_create_ruleset")
    try:
        landlock._add_paths(syscall, ruleset, (*read, *_paths(specs, "read")), read_access)
        landlock._add_paths(syscall, ruleset, (*write, *_paths(specs, "write")), write_access)
        if "nosock" not in specs:
            landlock._add_paths(syscall, ruleset, sockets, landlock.SOCKET_ACCESS & handled.fs)
        for path, rights in _grants(specs):
            landlock._add_paths(syscall, ruleset, (path,), rights & handled.fs)
        if "fs-all" in specs:
            landlock._add_paths(syscall, ruleset, ("/",), handled.fs)
        result = syscall(landlock.SYS_RESTRICT_SELF, ruleset, flags)
        if result < 0:
            raise landlock._fail(result, "landlock_restrict_self")
    finally:
        os.close(ruleset)
    return abi


def install_variant_filters(specs: tuple[str, ...], deny_connect: bool = False) -> None:
    """The product seccomp filter (as the profile has it) and/or the extra deny-connect filter, as the specs say.

    deny_connect is what the jail hands on: Profile.deny_connect of the
    profile (soffice: True since the owner decision of 17.11.).
    """
    if "seccomp" in specs:
        seccomp.install_network_denylist(deny_connect=deny_connect)
    if "deny-connect" in specs:
        lib = seccomp._load()
        if lib is None:
            raise OSError(errno.ENOSYS, "libseccomp not available")
        context = lib.seccomp_init(seccomp.SCMP_ACT_ALLOW)
        if not context:
            raise OSError(errno.ENOMEM, "seccomp_init failed")
        try:
            refuse = seccomp.errno_action(errno.EACCES)
            seccomp._check(lib.seccomp_rule_add_exact_array(context, refuse, seccomp._resolve(lib, "connect"), 0, None))
            seccomp._check(lib.seccomp_load(context))
        finally:
            lib.seccomp_release(context)


def variant_ops(specs: tuple[str, ...]) -> jail.Ops:
    """The product jail with the Landlock rules and seccomp filters of one variant."""
    ops = jail.system_ops()
    uses_seccomp = "seccomp" in specs or "deny-connect" in specs
    return replace(
        ops,
        landlock_abi=_no_landlock if "no-landlock" in specs else ops.landlock_abi,
        landlock_restrict=partial(restrict_variant, specs),
        seccomp_available=(lambda: True) if uses_seccomp else _no_seccomp,
        seccomp_install=partial(install_variant_filters, specs),
    )


def with_deny_connect(call: jail.Call) -> jail.Call:
    """The same call with deny_connect switched on in a copy of its profile; nothing else differs."""
    return replace(call, profile=replace(call.profile, deny_connect=True))


def deny_connect_main(argv: list[str], ops: jail.Ops | None = None) -> int:
    """The product jail of argv with deny_connect, then the command."""
    call = jail.parse(argv)
    if call is None:
        return jail.EXIT_USAGE
    return jail.run(with_deny_connect(call), jail.system_ops() if ops is None else ops)


def connect(path: str) -> int:
    """0 and "ok" when a connection to the socket at path succeeds."""
    family = getattr(socket, "AF_UNIX", None)
    if family is None:
        print("refused no-af-unix")
        return 1
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.connect(path)
        except FileNotFoundError:
            print("absent")
            return 3
        except OSError as exc:
            print(f"refused {errno.errorcode.get(exc.errno or 0, exc.errno)}")
            return 1
    print("ok")
    return 0


def _errno_name(exc: OSError) -> str:
    return errno.errorcode.get(exc.errno or 0, str(exc.errno))


def unlink(path: str) -> int:
    """0 and "ok" when path could be removed; otherwise the errno name, or "absent"."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        print("absent")
        return 3
    except OSError as exc:
        print(_errno_name(exc))
        return 1
    print("ok")
    return 0


def access(path: str) -> int:
    """0 and "ok" when access(path, W_OK) says writable; otherwise the errno name.

    The libc call itself, as LibreOffice makes it (os.access hides errno).
    """
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except (OSError, TypeError):
        print("no-libc")
        return 1
    if libc.access(os.fsencode(path), os.W_OK) == 0:
        print("ok")
        return 0
    print(errno.errorcode.get(ctypes.get_errno(), str(ctypes.get_errno())))
    return 1


def abi() -> int:
    """Prints the Landlock ABI of this kernel and the kernel release."""
    print(f"abi={landlock.abi_version()} kernel={platform.release() or 'none'}")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["abi"]:
        return abi()
    if len(argv) == 2 and argv[0] == "connect":
        return connect(argv[1])
    if len(argv) == 2 and argv[0] == "unlink":
        return unlink(argv[1])
    if len(argv) == 2 and argv[0] == "access":
        return access(argv[1])
    if len(argv) > 1 and argv[0] == "deny-connect":
        return deny_connect_main(argv[1:])
    if len(argv) > 2 and argv[0] == "layers" and argv[1] in PARTIAL_LAYERS:
        call = jail.parse(argv[2:])
        if call is None:
            return jail.EXIT_USAGE
        return jail.run(call, layered_ops(argv[1]))
    if len(argv) > 2 and argv[0] == "variant":
        specs = parse_specs(argv[1])
        call = jail.parse(argv[2:])
        if specs is None or call is None:
            return jail.EXIT_USAGE
        return jail.run(call, variant_ops(specs))
    return jail.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
