"""Test-only start program for the LibreOffice diagnosis of plan 02-16; never part of the product.

The product starts every child through sandbox/jail.py with all layers. To
find the layer under which soffice stops working, test_container_soffice.py
starts the same soffice call with only some of them, through this program:

    python -I jail_layers.py layers limits   <jail arguments>   rlimits, no_new_privs
    python -I jail_layers.py layers landlock <jail arguments>   the same plus Landlock

<jail arguments> are exactly what jail.main takes (profile, --read/--write,
--, command). The layers run in the order and with the code of the product
(jail.run with jail.system_ops); only the probe of the left-out layers
answers "not available". The full product jail (plus seccomp) needs no
helper, the test starts it through jail.jail_argv.

    python -I jail_layers.py connect <socket path>

tries to connect a Unix stream socket (secure-phase measurement: may a child
reach the HaRP socket of the server?) and prints ok, refused <errno> or absent.
"""

import errno
import socket
import sys
from dataclasses import replace

from pii_redaction_backend.sandbox import jail

PARTIAL_LAYERS = ("limits", "landlock")


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


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "connect":
        return connect(argv[1])
    if len(argv) > 2 and argv[0] == "layers" and argv[1] in PARTIAL_LAYERS:
        call = jail.parse(argv[2:])
        if call is None:
            return jail.EXIT_USAGE
        return jail.run(call, layered_ops(argv[1]))
    return jail.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
