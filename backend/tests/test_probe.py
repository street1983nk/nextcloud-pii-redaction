"""The sandbox probe, the permanent jail failure and the process hardening of the server."""

import json
import logging
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pii_redaction_backend import main
from pii_redaction_backend.sandbox import probe
from pii_redaction_backend.workers.child import ChildFailed, ChildTimeout


@pytest.fixture(autouse=True)
def fresh_state() -> Iterator[None]:
    probe._STATE.clear()
    yield
    probe._STATE.clear()


class Runner:
    """A run_child stand-in that records its calls and fails on request."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, args: list[str], **kwargs: Any) -> None:
        self.calls.append({"args": args, **kwargs})
        if self.error is not None:
            raise self.error


def _exists(folder: Path) -> bool:
    return folder.exists()


async def test_both_layers_and_a_good_jail_run() -> None:
    runner = Runner()
    state = await probe.run(seccomp_available=lambda: True, landlock_abi=lambda: 6, runner=runner)
    assert state == probe.SandboxState(seccomp="active", landlock="active", landlock_abi=6, jail="ok")
    assert probe.current() == state
    (call,) = runner.calls
    assert call["args"] == ["/bin/true"]
    assert call["profile"] == "precheck"
    assert call["write"] == (str(call["cwd"]),)
    assert Path(call["cwd"]).parent.name == "work"
    assert not _exists(call["cwd"])


async def test_missing_layers_are_named_not_hidden() -> None:
    state = await probe.run(seccomp_available=lambda: False, landlock_abi=lambda: 0, runner=Runner())
    assert (state.seccomp, state.landlock, state.landlock_abi, state.jail) == ("unavailable", "unavailable", 0, "ok")


@pytest.mark.parametrize("error", [ChildFailed(71), ChildTimeout(), OSError(2, "gone")])
async def test_a_failing_jail_run_is_failed(error: Exception) -> None:
    state = await probe.run(seccomp_available=lambda: True, landlock_abi=lambda: 3, runner=Runner(error))
    assert state.jail == "failed"
    assert state.landlock_abi == 3


def test_before_the_probe_there_is_no_state() -> None:
    assert probe.current() is None


async def test_mark_jail_failed_turns_the_jail_and_logs_once(caplog: pytest.LogCaptureFixture) -> None:
    await probe.run(seccomp_available=lambda: True, landlock_abi=lambda: 6, runner=Runner())
    caplog.set_level(logging.INFO, logger="pii_redaction_backend")

    probe.mark_jail_failed()
    probe.mark_jail_failed()

    state = probe.current()
    assert state is not None
    assert (state.seccomp, state.landlock, state.landlock_abi, state.jail) == ("active", "active", 6, "failed")
    lines = [record for record in caplog.records if record.getMessage() == "jail layer failed"]
    assert len(lines) == 1
    assert lines[0].__dict__["jail"] == "failed"
    assert lines[0].levelno == logging.ERROR


def test_mark_jail_failed_before_the_probe_still_records_it(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="pii_redaction_backend")
    probe.mark_jail_failed()
    expected = probe.SandboxState(seccomp="unavailable", landlock="unavailable", landlock_abi=0, jail="failed")
    assert probe.current() == expected
    assert [record.getMessage() for record in caplog.records] == ["jail layer failed"]


# -- process hardening ------------------------------------------------------------------


def test_main_hardens_the_process_before_anything_else(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []

    def unusable() -> list[str]:
        order.append("check")
        return []

    monkeypatch.setattr(main, "harden_process", lambda: order.append("harden"))
    monkeypatch.setattr(main.config, "unusable_startup_variables", unusable)
    monkeypatch.setattr(main, "run_app", lambda *_args, **_kwargs: order.append("run"))
    main.main()
    assert order == ["harden", "check", "run"]


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="the no-op is the branch off Linux")
def test_off_linux_the_hardening_does_nothing() -> None:
    main.harden_process()


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")
def test_after_hardening_the_process_is_not_dumpable(tmp_path: Path) -> None:
    out = tmp_path / "dumpable.json"
    script = tmp_path / "harden_probe.py"
    script.write_text(
        "import ctypes, json\n"
        "libc = ctypes.CDLL(None)\n"
        "before = libc.prctl(3, 0, 0, 0, 0)\n"
        "from pii_redaction_backend import main\n"
        "main.harden_process()\n"
        "after = libc.prctl(3, 0, 0, 0, 0)\n"
        f"open({str(out)!r}, 'w').write(json.dumps([before, after]))\n",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, "-I", str(script)], check=False, timeout=60)  # noqa: S603
    assert result.returncode == 0
    # Positive control: a fresh process is dumpable, the hardened one is not.
    assert json.loads(out.read_text(encoding="utf-8")) == [1, 0]
