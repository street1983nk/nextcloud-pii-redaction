"""The child process runner: no secret in the environment, a time limit, the whole group killed.

The runner relies on POSIX process groups (start_new_session, killpg), so the
behavioural tests run on Linux only (python.yml on Ubuntu); the environment
and argument rules are checked everywhere.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

from pii_redaction_backend.workers import child

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX only")
SECRETS = {
    "APP_SECRET": "test-secret-not-real",
    "APP_ID": "pii_redaction_backend",
    "NEXTCLOUD_URL": "http://nextcloud.invalid",
    "AA_VERSION": "33.0.0",
    "APP_PERSISTENT_STORAGE": "/nc_app_pii_redaction_backend_data",
}


def test_the_safe_environment_carries_no_appapi_variable() -> None:
    assert not set(SECRETS) & set(child.SAFE_ENV)
    assert child.SAFE_ENV["PATH"] == "/usr/bin:/bin"


def test_extra_values_pass_only_through_the_allowlist() -> None:
    env = child.child_env({"TESSDATA_PREFIX": "/usr/share/tesseract-ocr/5/tessdata"})
    assert env["TESSDATA_PREFIX"] == "/usr/share/tesseract-ocr/5/tessdata"
    with pytest.raises(ValueError, match="not allowed"):
        child.child_env({"APP_SECRET": "x"})


def test_a_python_child_runs_isolated() -> None:
    args = child.python_child("render", "a", "b")
    assert args[:4] == [sys.executable, "-I", "-m", "pii_redaction_backend.workers.render"]
    assert args[4:] == ["a", "b"]
    with pytest.raises(ValueError, match="unknown child"):
        child.python_child("os.system")


@POSIX_ONLY
async def test_the_child_sees_none_of_the_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in SECRETS.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "env.json"
    script = f"import json, os; open({str(out)!r}, 'w').write(json.dumps(dict(os.environ)))"

    await child.run_child([sys.executable, "-I", "-c", script], timeout_s=20, cwd=tmp_path)

    seen = json.loads(out.read_text(encoding="utf-8"))
    assert not set(SECRETS) & set(seen), "APP_SECRET or NEXTCLOUD_URL reached the child"


@POSIX_ONLY
async def test_a_hanging_child_and_its_grandchild_are_killed(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"open({str(pid_file)!r}, 'w').write(str(p.pid)); time.sleep(60)"
    )

    with pytest.raises(child.ChildTimeout):
        await child.run_child([sys.executable, "-I", "-c", script], timeout_s=2, cwd=tmp_path)

    grandchild = int(pid_file.read_text(encoding="utf-8"))
    assert _gone_within(grandchild, seconds=5), "the grandchild survived the group kill"


@POSIX_ONLY
async def test_a_failing_child_reports_only_its_exit_code(tmp_path: Path) -> None:
    script = "import sys; print('secret document text'); sys.exit(3)"

    with pytest.raises(child.ChildFailed) as failure:
        await child.run_child([sys.executable, "-I", "-c", script], timeout_s=20, cwd=tmp_path)

    assert failure.value.exit_code == 3
    assert "secret" not in str(failure.value)


def _gone_within(pid: int, *, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill 0; its state in /proc says it is gone.
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.is_file() and stat.read_text(encoding="utf-8").split()[2] == "Z")
