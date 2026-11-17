"""The group reaper: kill, collect only the group, never waitpid(-1); on Linux no grandchild and no zombie stays."""

import errno
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from pii_redaction_backend.sandbox import reaper
from pii_redaction_backend.workers import child

LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")


class FakeOs:
    """killpg and waitpid stand-ins that record every call."""

    def __init__(self, results: list[Any], *, killpg_error: type[Exception] | None = None) -> None:
        self.results = list(results)
        self.killpg_error = killpg_error
        self.calls: list[tuple[str, int, int]] = []

    def killpg(self, pgid: int, sig: int) -> None:
        self.calls.append(("killpg", pgid, sig))
        if self.killpg_error is not None:
            raise self.killpg_error

    def waitpid(self, pid: int, options: int) -> tuple[int, int]:
        self.calls.append(("waitpid", pid, options))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def fake_os(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(results: list[Any], **kwargs: Any) -> FakeOs:
        fake = FakeOs(results, **kwargs)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(os, "killpg", fake.killpg, raising=False)
        monkeypatch.setattr(os, "waitpid", fake.waitpid)
        monkeypatch.setattr(os, "WNOHANG", 1, raising=False)
        monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
        monkeypatch.setattr(reaper.time, "sleep", lambda _s: None)
        return fake

    return install


def test_the_group_is_killed_then_collected_until_empty(fake_os: Any) -> None:
    fake = fake_os([(501, 9), (502, 9), ChildProcessError(errno.ECHILD, "none")])
    reaper.reap_group(500)
    assert fake.calls[0] == ("killpg", 500, 9)
    assert fake.calls[1:] == [("waitpid", -500, 1)] * 3


def test_a_group_that_is_already_gone_is_not_an_error(fake_os: Any) -> None:
    fake = fake_os([ChildProcessError(errno.ECHILD, "none")], killpg_error=ProcessLookupError)
    reaper.reap_group(500)
    assert [call[0] for call in fake.calls] == ["killpg", "waitpid"]


def test_a_member_still_dying_is_waited_for_a_bounded_time(fake_os: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 0.0, 0.5, 2.0])
    monkeypatch.setattr(reaper.time, "monotonic", lambda: next(ticks))
    fake = fake_os([(0, 0), (0, 0), (0, 0)])
    reaper.reap_group(500)
    assert len([call for call in fake.calls if call[0] == "waitpid"]) == 3


def test_the_reaper_never_waits_for_any_child(fake_os: Any) -> None:
    fake = fake_os([ChildProcessError(errno.ECHILD, "none")])
    reaper.reap_group(42)
    assert all(call[1] == -42 for call in fake.calls if call[0] == "waitpid")


@pytest.mark.skipif(sys.platform != "win32", reason="the no-op is the Windows branch")
def test_on_windows_the_reaper_does_nothing() -> None:
    reaper.reap_group(1)
    assert reaper.become_subreaper() is False


@pytest.mark.linux
@LINUX
def test_the_server_can_become_the_subreaper() -> None:
    assert reaper.become_subreaper() is True


# -- the real group on Linux ---------------------------------------------------------


def _jailed(tmp_path: Path) -> dict[str, Any]:
    return {
        "profile": "render",
        "cwd": tmp_path,
        "read": (sys.base_prefix, sys.prefix, str(tmp_path)),
        "write": (str(tmp_path),),
    }


def _group_members(pgid: int) -> list[tuple[int, str]]:
    """(pid, state) of every process in /proc whose process group is pgid."""
    members = []
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            text = stat.read_text(encoding="utf-8")
        except OSError:
            continue
        fields = text[text.rindex(")") + 2 :].split()
        if int(fields[2]) == pgid:
            members.append((int(stat.parent.name), fields[0]))
    return members


def _empty_within(pgid: int, seconds: float) -> list[tuple[int, str]]:
    deadline = time.monotonic() + seconds
    members = _group_members(pgid)
    while members and time.monotonic() < deadline:
        time.sleep(0.1)
        members = _group_members(pgid)
    return members


def _script(tmp_path: Path, *, hang: bool) -> str:
    pid_file = tmp_path / "grandchild.pid"
    tail = "time.sleep(60)" if hang else "sys.exit(0)"
    return (
        "import os, subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)']); "
        f"open({str(pid_file)!r}, 'w').write(f'{{p.pid}} {{os.getpgid(0)}}'); {tail}"
    )


@pytest.mark.linux
@LINUX
async def test_after_a_timeout_no_member_of_the_group_is_left(tmp_path: Path) -> None:
    reaper.become_subreaper()
    with pytest.raises(child.ChildTimeout):
        await child.run_child(
            [sys.executable, "-I", "-c", _script(tmp_path, hang=True)], **_jailed(tmp_path), timeout_s=3
        )

    grandchild, pgid = map(int, (tmp_path / "grandchild.pid").read_text(encoding="utf-8").split())
    left = _empty_within(pgid, 5)
    assert left == [], f"group {pgid} still has {left} (grandchild {grandchild})"


@pytest.mark.linux
@LINUX
async def test_a_successful_child_leaves_no_grandchild_behind(tmp_path: Path) -> None:
    reaper.become_subreaper()
    await child.run_child(
        [sys.executable, "-I", "-c", _script(tmp_path, hang=False)], **_jailed(tmp_path), timeout_s=30
    )

    grandchild, pgid = map(int, (tmp_path / "grandchild.pid").read_text(encoding="utf-8").split())
    left = _empty_within(pgid, 5)
    assert left == [], f"the grandchild {grandchild} outlived a successful child"


@pytest.mark.linux
@LINUX
def test_positive_control_a_grandchild_outside_the_reaper_is_seen(tmp_path: Path) -> None:
    import subprocess

    leader = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        assert _group_members(leader.pid), "the probe must see a live group before the reaper runs"
    finally:
        reaper.reap_group(leader.pid)
        leader.wait()
    assert _empty_within(leader.pid, 5) == []
