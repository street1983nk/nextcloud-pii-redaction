"""Test-only probe for the container proof of plan 02-21: what can a child in a jail read?

    python -I read_secrets.py <out.json> <canaries.txt> <frpc_pid> <foreign_dir> <path...>

Standard library only, no import of the package: the probe stands for a parser
that was taken over, and such a parser knows nothing of the app. It tries to
open each path and read 4096 bytes, /proc/<frpc_pid>/environ and the folder of
another job included, and writes only words:

    paths            path -> "read" | "denied" | "missing" | "error <errno name>"
    foreign_listing  listing <foreign_dir>: the same words
    control          reading canaries.txt in its own work folder (positive control: "read")
    env_keys         the names of its environment variables, never the values
    canary_seen      True when a canary value (one per line of canaries.txt, handed
                     in through a file, never through the environment) shows up in
                     any byte it read or in any value of its environment
    limits           name -> [soft, hard] of CPU, FSIZE, NOFILE, AS, CORE (getrlimit)
    proc_self_limits reading /proc/self/limits: "read" | "denied" | ...
    socket_inet      socket(AF_INET): "ok" | "refused <errno name>"
    socket_unix      socket(AF_UNIX): the same words

The answer is written as <out.json>.tmp and renamed, so a half answer is never read.
Exit 2 on wrong arguments, otherwise 0: the words are the result.
"""

import errno
import json
import os
import socket
import sys

READ_BYTES = 4096
LIMITS = ("CPU", "FSIZE", "NOFILE", "AS", "CORE")


def _limits() -> dict[str, list[int]]:
    if sys.platform == "win32":
        return {}
    import resource

    return {name: list(resource.getrlimit(getattr(resource, f"RLIMIT_{name}"))) for name in LIMITS}


def _word(exc: OSError) -> str:
    if exc.errno in {errno.EACCES, errno.EPERM}:
        return "denied"
    if exc.errno == errno.ENOENT:
        return "missing"
    return f"error {errno.errorcode.get(exc.errno or 0, 'unknown')}"


def _read(path: str, seen: list[bytes]) -> str:
    try:
        with open(path, "rb") as handle:
            seen.append(handle.read(READ_BYTES))
    except OSError as exc:
        return _word(exc)
    return "read"


def _listing(path: str, seen: list[bytes]) -> str:
    try:
        names = os.listdir(path)
    except OSError as exc:
        return _word(exc)
    seen.append("\n".join(names).encode())
    return "read"


def _socket(family: int) -> str:
    try:
        probe = socket.socket(family, socket.SOCK_STREAM)
    except OSError as exc:
        return f"refused {errno.errorcode.get(exc.errno or 0, 'unknown')}"
    probe.close()
    return "ok"


def _unix_socket() -> str:
    if sys.platform == "win32":
        return "absent"
    return _socket(socket.AF_UNIX)


def main(argv: list[str]) -> int:
    if len(argv) < 4 or not argv[2].isdigit():
        return 2
    out, canary_file, frpc_pid, foreign_dir, *paths = argv
    try:
        with open(canary_file, encoding="utf-8") as handle:
            canaries = [line.strip().encode() for line in handle if line.strip()]
        control = "read"
    except OSError as exc:
        canaries = []
        control = _word(exc)
    seen: list[bytes] = []
    results = {path: _read(path, seen) for path in [f"/proc/{frpc_pid}/environ", *paths]}
    foreign = _listing(foreign_dir, seen)
    seen.extend(value.encode(errors="replace") for value in os.environ.values())
    proc_limits = _read("/proc/self/limits", [])
    answer = {
        "paths": results,
        "foreign_listing": foreign,
        "control": control,
        "env_keys": sorted(os.environ),
        "canary_seen": any(canary in blob for canary in canaries for blob in seen),
        "limits": _limits(),
        "proc_self_limits": proc_limits,
        "socket_inet": _socket(socket.AF_INET),
        "socket_unix": _unix_socket(),
    }
    temporary = f"{out}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(answer, handle, sort_keys=True)
    os.replace(temporary, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
