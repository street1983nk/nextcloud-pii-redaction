"""The RAM guard reads anon against memory.max, never memory.current (JOB-06).

Copied from Findling (tests/test_memory_guard.py) with the import path of this
package, plus the admission of the two child kinds of phase 1 (render and
soffice) with their provisional needs. Every file is read from a fake tree
under ``tmp_path``; no real /sys is touched.

The fail safe direction: nothing readable means not admitted, so no child
starts on a box whose memory cannot be judged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pii_redaction_backend.resources import hardware, memory_guard
from pii_redaction_backend.resources.memory_guard import admits, anon_bytes, headroom_bytes, memory_events

GIB = 1024**3
MIB = 1024**2
KIB = 1024


def _tree(
    root: Path,
    *,
    memory_max: str | None,
    anon: int | None = None,
    file_cache: int = 10 * GIB,
    events: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if events is not None:
        (root / "memory.events").write_text(events, encoding="ascii")
    if memory_max is not None:
        (root / "memory.max").write_text(memory_max + "\n", encoding="ascii")
    if anon is not None:
        (root / "memory.stat").write_text(
            f"anon {anon}\nfile {file_cache}\nkernel 1048576\nshmem 0\n",
            encoding="ascii",
        )
    # A value no reader may trust. If memory.current were ever read, every
    # result below would be wrong.
    (root / "memory.current").write_text(f"{64 * GIB}\n", encoding="ascii")
    return root


def _meminfo(path: Path, available: int | None) -> Path:
    lines = ["MemTotal:       16000000 kB", "MemFree:         1000000 kB"]
    if available is not None:
        lines.append(f"MemAvailable:   {available // KIB} kB")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def test_the_page_cache_does_not_count_as_used(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(4 * GIB), anon=1 * GIB, file_cache=10 * GIB)
    meminfo = _meminfo(tmp_path / "meminfo", 8 * GIB)

    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 3 * GIB


def test_the_smaller_of_limit_headroom_and_memavailable_wins(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(4 * GIB), anon=1 * GIB)
    meminfo = _meminfo(tmp_path / "meminfo", 2 * GIB)

    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 2 * GIB


def test_no_limit_means_memavailable(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max="max", anon=1 * GIB)
    meminfo = _meminfo(tmp_path / "meminfo", 5 * GIB)

    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 5 * GIB


def test_a_missing_memory_stat_falls_back_to_memavailable(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(4 * GIB))
    meminfo = _meminfo(tmp_path / "meminfo", 3 * GIB)

    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 3 * GIB
    assert headroom_bytes(cgroup_root=root, meminfo=tmp_path / "absent") is None


def test_a_memory_stat_without_an_anon_line_falls_back_to_memavailable(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(4 * GIB))
    (root / "memory.stat").write_text("file 1024\nkernel 2048\n", encoding="ascii")
    meminfo = _meminfo(tmp_path / "meminfo", 3 * GIB)

    assert anon_bytes(root) is None
    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 3 * GIB
    assert headroom_bytes(cgroup_root=root, meminfo=_meminfo(tmp_path / "bare", None)) is None


def test_nothing_readable_is_none(tmp_path: Path) -> None:
    assert headroom_bytes(cgroup_root=tmp_path / "nowhere", meminfo=tmp_path / "nothing") is None


def test_anon_above_the_limit_is_no_headroom_rather_than_negative(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(1 * GIB), anon=2 * GIB)
    meminfo = _meminfo(tmp_path / "meminfo", 8 * GIB)

    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 0


def test_anon_is_read_from_memory_stat(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max="max", anon=123_456)

    assert anon_bytes(root) == 123_456
    assert anon_bytes(tmp_path / "nowhere") is None


def test_admission_needs_a_readable_headroom_of_at_least_the_need() -> None:
    assert admits(None, need=1) is False
    assert admits(10, need=10) is True
    assert admits(9, need=10) is False


def test_the_counters_of_memory_events_are_read(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max="max", events="low 0\nhigh 0\nmax 7\noom 0\noom_kill 1\n")

    assert memory_events(root) == {"low": 0, "high": 0, "max": 7, "oom": 0, "oom_kill": 1}


def test_a_missing_memory_events_is_none(tmp_path: Path) -> None:
    # cgroup v1, or the root cgroup: the file does not exist.
    root = _tree(tmp_path / "cg", memory_max="max")

    assert memory_events(root) is None
    assert memory_events(tmp_path / "nowhere") is None


def test_an_empty_or_broken_memory_events_is_none(tmp_path: Path) -> None:
    empty = _tree(tmp_path / "empty", memory_max="max", events="")
    broken = _tree(tmp_path / "broken", memory_max="max", events="max seven\noom -1\nnonsense\n")
    binary = tmp_path / "binary"
    binary.mkdir()
    (binary / "memory.events").write_bytes(b"max \xff\xfe\n")

    assert memory_events(empty) is None
    assert memory_events(broken) is None
    assert memory_events(binary) is None


def test_a_broken_line_does_not_hide_the_good_ones(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max="max", events="max 3\ngarbage here now\noom_kill 2\n")

    assert memory_events(root) == {"max": 3, "oom_kill": 2}


def test_the_skeleton_example_limit_minus_anon_capped_by_memavailable(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(2 * GIB), anon=1 * GIB)
    meminfo = _meminfo(tmp_path / "meminfo", 3 * GIB)

    assert headroom_bytes(cgroup_root=root, meminfo=meminfo) == 1 * GIB


def test_the_needs_are_the_provisional_skeleton_values() -> None:
    assert memory_guard.NEED == {"render": 512 * MIB, "soffice": 1024 * MIB}
    assert memory_guard.RESERVE == 256 * MIB


@pytest.mark.parametrize(
    ("kind", "headroom", "admitted"),
    [
        ("soffice", 900 * MIB, False),
        ("soffice", 1280 * MIB - 1, False),
        ("soffice", 1280 * MIB, True),
        ("soffice", 1536 * MIB, True),
        ("render", 700 * MIB, False),
        ("render", 768 * MIB, True),
        ("render", None, False),
        ("soffice", None, False),
    ],
)
def test_admit_needs_the_need_of_the_kind_plus_the_reserve(
    monkeypatch: pytest.MonkeyPatch, kind: str, headroom: int | None, admitted: bool
) -> None:
    monkeypatch.setattr(memory_guard, "headroom_bytes", lambda: headroom)

    assert memory_guard.admit(kind) is admitted


def test_an_unknown_kind_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_guard, "headroom_bytes", lambda: 64 * GIB)

    with pytest.raises(KeyError):
        memory_guard.admit("detect")


def test_the_guard_reads_the_real_paths_by_default() -> None:
    assert Path("/sys/fs/cgroup") == hardware.CGROUP_ROOT
    assert Path("/proc/meminfo") == hardware.MEMINFO


def test_hardware_reads_cores_and_memory_from_a_fake_tree(tmp_path: Path) -> None:
    root = _tree(tmp_path / "cg", memory_max=str(2 * GIB), anon=0)
    (root / "cpu.max").write_text("150000 100000\n", encoding="ascii")
    meminfo = _meminfo(tmp_path / "meminfo", 3 * GIB)

    found = hardware.detect(cgroup_root=root, meminfo=meminfo, cpu_count=lambda: 4, machine=lambda: "aarch64")

    assert (found.cgroup, found.cores, found.cores_whole) == ("v2", 1.5, 1)
    assert (found.memory_limit_bytes, found.memory_available_bytes) == (2 * GIB, 3 * GIB)
    assert found.architecture == "aarch64"


def test_hardware_never_raises_on_an_empty_tree(tmp_path: Path) -> None:
    def broken() -> int:
        raise OSError

    found = hardware.detect(cgroup_root=tmp_path / "none", meminfo=tmp_path / "none", cpu_count=broken)

    assert (found.cgroup, found.cores, found.memory_limit_bytes) == ("none", None, None)


# -- the thread count of the detection worker (plan 02-16) ------------------------------------


def _threads(tmp_path: Path, cpu_max: str | None, affinity: int | None, cap: int = hardware.WORKER_THREADS_CAP) -> int:
    root = tmp_path / "cg"
    root.mkdir(exist_ok=True)
    (root / "memory.max").write_text("max\n", encoding="ascii")
    if cpu_max is not None:
        (root / "cpu.max").write_text(f"{cpu_max}\n", encoding="ascii")

    def count() -> int | None:
        return affinity

    found = hardware.detect(cgroup_root=root, meminfo=tmp_path / "none", cpu_count=count)
    return hardware.worker_threads(found, cap)


@pytest.mark.parametrize(
    ("cpu_max", "affinity", "expected"),
    [
        ("max 100000", 4, 2),  # no quota: the affinity, capped at 2
        ("max 100000", 1, 1),  # one core in the cpu set
        ("200000 100000", 8, 2),  # two cores of quota
        ("100000 100000", 8, 1),  # one core of quota
        ("150000 100000", 8, 1),  # 1.5 cores: whole cores only
        ("50000 100000", 8, 1),  # half a core still gets one thread
        ("0 100000", 8, 2),  # garbage quota: as if there were none
        (None, 4, 2),  # no cpu.max at all: the affinity, capped
        (None, None, 1),  # nothing known: one thread
    ],
)
def test_worker_threads_from_cpu_max_and_affinity(
    tmp_path: Path, cpu_max: str | None, affinity: int | None, expected: int
) -> None:
    assert _threads(tmp_path, cpu_max, affinity) == expected


def test_worker_threads_cap(tmp_path: Path) -> None:
    assert hardware.WORKER_THREADS_CAP == 2
    assert _threads(tmp_path, "300000 100000", 8, cap=4) == 3
    assert _threads(tmp_path, "max 100000", 8, cap=4) == 4
    assert _threads(tmp_path, "max 100000", 8, cap=1) == 1


def test_worker_threads_default_reads_this_machine() -> None:
    assert 1 <= hardware.worker_threads() <= hardware.WORKER_THREADS_CAP


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", 1),
        ("2", 2),
        ("256", 256),
        ("257", None),
        ("0", None),
        ("02", None),
        ("", None),
        ("-1", None),
        (" 2", None),
        ("2 ", None),
        ("٢", None),
        ("two", None),
    ],
)
def test_threads_from_env_takes_only_a_plain_small_number(raw: str, expected: int | None) -> None:
    assert hardware.threads_from_env({"OMP_NUM_THREADS": raw}) == expected


def test_threads_from_env_without_the_variable() -> None:
    assert hardware.threads_from_env({}) is None
    assert hardware.threads_from_env({"OMP_THREAD_LIMIT": "1"}) is None


class _FakeTorch:
    def __init__(self, *, interop_started: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.interop_started = interop_started

    def set_num_threads(self, count: int, /) -> None:
        self.calls.append(("intra", count))

    def set_num_interop_threads(self, count: int, /) -> None:
        if self.interop_started:
            msg = "Error: cannot set number of interop threads after parallel work has started"
            raise RuntimeError(msg)
        self.calls.append(("interop", count))


def test_apply_worker_threads_sets_intra_and_interop() -> None:
    torch = _FakeTorch()
    assert hardware.apply_worker_threads(torch, {"OMP_NUM_THREADS": "2"}) == 2
    assert torch.calls == [("intra", 2), ("interop", 2)]


def test_apply_worker_threads_keeps_the_intra_count_when_interop_is_too_late() -> None:
    torch = _FakeTorch(interop_started=True)
    assert hardware.apply_worker_threads(torch, {"OMP_NUM_THREADS": "1"}) == 1
    assert torch.calls == [("intra", 1)]


def test_apply_worker_threads_changes_nothing_without_a_count() -> None:
    torch = _FakeTorch()
    assert hardware.apply_worker_threads(torch, {}) is None
    assert hardware.apply_worker_threads(torch, {"OMP_NUM_THREADS": "many"}) is None
    assert torch.calls == []
