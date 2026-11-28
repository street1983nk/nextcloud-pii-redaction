"""Exec a command under a fixed RLIMIT_AS, test only (plan 02-24, step 5).

usage: python -I as_cap.py <bytes> <absolute command> [args ...]

The soffice profile has no address space limit until plan 02-24 has measured
one, and the jail reads its profile in its own process, so a test cannot
patch a value into it. The negative test of test_container_corpus.py instead
puts this probe in front of soffice inside the product jail: it sets soft and
hard limit to <bytes> and replaces itself with the command, so soffice and
everything it starts inherit exactly that cap. Exit 2 for wrong arguments;
otherwise it does not return.
"""

import os
import sys


def parse(argv: list[str]) -> tuple[int, list[str]] | None:
    """The cap and the command, or None for anything else."""
    if len(argv) < 2 or not argv[0].isdigit() or not argv[0].isascii() or not argv[1].startswith("/"):
        return None
    cap = int(argv[0])
    if cap <= 0:
        return None
    return cap, argv[1:]


def main(argv: list[str]) -> int:
    parsed = parse(argv)
    if parsed is None or sys.platform == "win32":
        return 2
    import resource

    cap, command = parsed
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    os.execv(command[0], command)  # noqa: S606 - test probe, the command comes from the test
    return 2  # pragma: no cover - execv does not return


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
