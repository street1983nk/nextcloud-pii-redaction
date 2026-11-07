"""How much memory a child process could still take, and whether it may start (JOB-06).

Copied from Findling 1.6.x (findling/memory_guard.py, PAR-04) with the import
path of this package; ``NEED``, ``RESERVE`` and ``admit`` are new. Same house
rules as resources/hardware.py, whose readers it reuses so that memory.max and
MemAvailable have one spelling each: standard library only, every path
injectable so tests run against fake trees, never raises, logs nothing.

Why ``anon`` of memory.stat and not ``memory.current``: page cache (the source
file, the rendered page, LibreOffice's own files) is charged to the cgroup and
shows in memory.current, but the kernel reclaims it under pressure. Counting
it as used would refuse a child on exactly the boxes that have room for one.

memory.events (low, high, max, oom, oom_kill) is handed over as counters; a
rising ``oom_kill`` across a child is how the runner tells out_of_memory from
a plain failure.

Fail safe: a headroom that cannot be read admits nothing. Known limit: only
cgroup v2 carries memory.max, an anon line and memory.events. On a v1 host the
limit is not read and the answer is MemAvailable, the same as a box without
any limit, and the event reader answers None.
"""

from pathlib import Path
from typing import Final

from pii_redaction_backend.resources.hardware import CGROUP_ROOT, MEMINFO, meminfo_bytes, memory_limit

_STAT_FIELDS = 2  # "<name> <bytes>"
MiB: Final = 1024 * 1024

# What one child of each kind needs on top of the running container.
# vorläufig, nach Messung Phase 1/2 festschreiben (provisional: the CI legs of
# plan 17 measure peak_child_rss_kb per kind; no threshold without measurement).
NEED: Final[dict[str, int]] = {"render": 512 * MiB, "soffice": 1024 * MiB}
# Kept free besides the need, for the container itself and the kernel.
# vorläufig, nach Messung Phase 1/2 festschreiben.
RESERVE: Final = 256 * MiB


def anon_bytes(root: Path = CGROUP_ROOT) -> int | None:
    """The ``anon`` bytes of memory.stat, or None when the file or the line is unusable."""
    try:
        raw = (root / "memory.stat").read_text(encoding="ascii")
    except (OSError, ValueError):
        return None
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != _STAT_FIELDS or fields[0] != "anon":
            continue
        try:
            value = int(fields[1])
        except ValueError:
            return None
        return value if value >= 0 else None
    return None


def memory_events(root: Path = CGROUP_ROOT) -> dict[str, int] | None:
    """The counters of memory.events, or None on cgroup v1, at the root or when unreadable.

    Lines that are not "<name> <non negative integer>" are skipped; a file
    without a single usable line is None, never an empty mapping.
    """
    try:
        raw = (root / "memory.events").read_text(encoding="ascii")
    except (OSError, ValueError):
        return None
    counters: dict[str, int] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) == _STAT_FIELDS and fields[1].isdigit():
            counters[fields[0]] = int(fields[1])
    return counters or None


def headroom_bytes(*, cgroup_root: Path = CGROUP_ROOT, meminfo: Path = MEMINFO) -> int | None:
    """Bytes a further child could take, or None when nothing usable is readable.

    With a limit and a readable anon: the limit minus anon, capped by
    MemAvailable when that is readable, because a limit above what the host
    still has is room that does not exist. Without a limit, or without a usable
    anon line, MemAvailable alone. Never negative.
    """
    available = meminfo_bytes(meminfo, "MemAvailable")
    limit = memory_limit(cgroup_root)
    if limit is None:
        return available
    # anon, not memory.current: page cache is reclaimable and must not count
    # as used (see the module docstring).
    anon = anon_bytes(cgroup_root)
    if anon is None:
        return available
    within_limit = max(0, limit - anon)
    return within_limit if available is None else min(within_limit, available)


def admits(headroom: int | None, *, need: int) -> bool:
    """True when a readable headroom covers ``need``; unreadable is never admitted."""
    return headroom is not None and headroom >= need


def admit(kind: str) -> bool:
    """May a child of this kind start now? Its need plus the reserve against the headroom.

    An unknown kind raises KeyError: a child without a declared need must not
    start by accident.
    """
    need = NEED[kind] + RESERVE
    return admits(headroom_bytes(), need=need)
