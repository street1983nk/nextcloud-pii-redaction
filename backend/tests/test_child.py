"""The child process runner: no secret in the environment, a time limit, the whole group killed.

Every child starts through the jail, which needs Linux (rlimits, prctl), so
the behavioural tests run on Linux only (python.yml on Ubuntu); the
environment, argument and profile rules are checked everywhere.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from pii_redaction_backend.workers import child

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


def test_one_malloc_arena_per_child() -> None:
    assert child.SAFE_ENV["MALLOC_ARENA_MAX"] == "1"


def test_the_python_children_are_a_closed_list() -> None:
    assert {"render", "placeholder", "precheck", "sanitize"} == child.PYTHON_CHILDREN


class _Started(Exception):
    """Raised by the fake process start so nothing really runs."""


def _record_start(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    started: list[tuple[str, ...]] = []

    async def fake_exec(*args: str, **_kwargs: object) -> None:
        started.append(args)
        raise _Started

    monkeypatch.setattr(child.asyncio, "create_subprocess_exec", fake_exec)
    return started


async def test_every_child_starts_through_the_jail_of_its_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _record_start(monkeypatch)
    with pytest.raises(_Started):
        await child.run_child(["/bin/true"], profile="precheck", cwd=tmp_path, read=("/in",), write=("/out",))
    (argv,) = started
    assert list(argv[:5]) == [sys.executable, "-I", "-m", "pii_redaction_backend.sandbox.jail", "precheck"]
    assert list(argv[5:]) == ["--read", "/in", "--write", "/out", "--", "/bin/true"]


async def test_an_unknown_profile_starts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started = _record_start(monkeypatch)
    with pytest.raises(ValueError, match="unknown sandbox profile"):
        await child.run_child(["/bin/true"], profile="none", cwd=tmp_path)
    assert started == []


async def test_a_child_without_a_profile_starts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started = _record_start(monkeypatch)
    run: Any = child.run_child
    with pytest.raises(TypeError):
        await run(["/bin/true"], cwd=tmp_path)
    assert started == []


def test_a_python_child_runs_isolated() -> None:
    args = child.python_child("render", "a", "b")
    assert args[:4] == [sys.executable, "-I", "-m", "pii_redaction_backend.workers.render"]
    assert args[4:] == ["a", "b"]
    with pytest.raises(ValueError, match="unknown child"):
        child.python_child("os.system")


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail needs Linux")
async def test_the_child_sees_none_of_the_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in SECRETS.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "env.json"
    script = f"import json, os; open({str(out)!r}, 'w').write(json.dumps(dict(os.environ)))"

    await child.run_child([sys.executable, "-I", "-c", script], **_jailed(tmp_path), timeout_s=20)

    seen = json.loads(out.read_text(encoding="utf-8"))
    assert not set(SECRETS) & set(seen), "APP_SECRET or NEXTCLOUD_URL reached the child"


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail needs Linux")
async def test_a_hanging_child_and_its_grandchild_are_killed(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"open({str(pid_file)!r}, 'w').write(str(p.pid)); time.sleep(60)"
    )

    with pytest.raises(child.ChildTimeout):
        await child.run_child([sys.executable, "-I", "-c", script], **_jailed(tmp_path), timeout_s=2)

    grandchild = int(pid_file.read_text(encoding="utf-8"))
    assert _gone_within(grandchild, seconds=5), "the grandchild survived the group kill"


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail needs Linux")
async def test_a_failing_child_reports_only_its_exit_code(tmp_path: Path) -> None:
    script = "import sys; print('secret document text'); sys.exit(3)"

    with pytest.raises(child.ChildFailed) as failure:
        await child.run_child([sys.executable, "-I", "-c", script], **_jailed(tmp_path), timeout_s=20)

    assert failure.value.exit_code == 3
    assert "secret" not in str(failure.value)


def _jailed(tmp_path: Path) -> dict[str, Any]:
    """Profile and paths for a test child: the interpreter and tmp_path, nothing else."""
    return {
        "profile": "render",
        "cwd": tmp_path,
        "read": (sys.base_prefix, sys.prefix, str(tmp_path)),
        "write": (str(tmp_path),),
    }


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


# -- the diagnosis of a failed child (plan 02-08) ----------------------------------------


def test_the_tail_drops_paths_quotes_urls_and_foreign_bytes() -> None:
    raw = (
        "Error: source file could not be loaded\n"
        "Warning: failed to open /nc_app_pii_redaction_backend_data/work/7/Bescheid Meier.docx here\n"
        "javaldx: 'Frau Erika Mustermann' not found and \"Aktenzeichen 12\" either\n"
        "file:///tmp/lo-7/user/registrymodifications.xcu broken\n"
        "Gr\u00fc\u00dfe aus ~/home\n"
    ).encode()
    tail = child.diagnostic_tail(raw)
    assert "Error: source file could not be loaded" in tail
    for leak in ("nc_app", "Bescheid", "Meier", "Erika", "Mustermann", "Aktenzeichen", "lo-7", "registry", "home"):
        assert leak not in tail, leak
    assert "<path>" in tail
    assert "<q>" in tail
    assert tail.isascii()


def test_positive_control_plain_diagnostic_words_stay() -> None:
    assert child.diagnostic_tail(b"Fatal exception: Signal 6\n\n") == "Fatal exception: Signal 6"


def test_the_tail_keeps_the_last_lines_and_cuts_long_ones() -> None:
    raw = "".join(f"line {n} " + "x" * 400 + "\n" for n in range(20)).encode()
    lines = child.diagnostic_tail(raw).split(" | ")
    assert len(lines) == child.TAIL_LINES
    assert lines[0].startswith("line 15 ")
    assert all(len(line) <= child.TAIL_LINE_CHARS for line in lines)


def test_a_signal_is_reported_apart_from_the_exit_code() -> None:
    killed = child.ChildFailed(-9)
    assert (killed.exit_code, killed.signal, killed.stderr_tail) == (-9, 9, "")
    failed = child.ChildFailed(77, "Fatal exception")
    assert (failed.exit_code, failed.signal, failed.stderr_tail) == (77, None, "Fatal exception")
    assert "Fatal" not in str(failed)


TMP = "/tmp"  # noqa: S108 - the soffice profile root under test, nothing is written there
JOB = f"{TMP}/lo-1"
SOFFICE_ENV_VALUES = {
    "TMPDIR": f"{JOB}/tmp",  # noqa: S108 - inside the profile under test
    "HOME": f"{JOB}/home",
    "XDG_CACHE_HOME": f"{JOB}/cache",
    "XDG_CONFIG_HOME": f"{JOB}/config",
    "XDG_RUNTIME_DIR": f"{JOB}/runtime",
}


def test_the_soffice_variables_are_exactly_tmpdir_home_and_three_xdg_folders() -> None:
    assert set(SOFFICE_ENV_VALUES) == child.SOFFICE_ENV
    assert {"TESSDATA_PREFIX", "SAL_USE_VCLPLUGIN"} == child.EXTRA_ALLOWED


def test_soffice_gets_its_variables_inside_its_job_profile() -> None:
    env = child.child_env(SOFFICE_ENV_VALUES, profile="soffice")
    for key, value in SOFFICE_ENV_VALUES.items():
        assert env[key] == value
    # The profile folder itself is allowed, too.
    assert child.child_env({"HOME": JOB}, profile="soffice")["HOME"] == JOB


@pytest.mark.parametrize("profile", [None, "render", "precheck", "sanitize", "ocr", "detect"])
@pytest.mark.parametrize("key", sorted(SOFFICE_ENV_VALUES))
def test_negative_no_other_child_gets_a_soffice_variable(profile: str | None, key: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        child.child_env({key: SOFFICE_ENV_VALUES[key]}, profile=profile)


@pytest.mark.parametrize(
    "value",
    [
        "/",
        TMP,
        f"{TMP}/lo-",
        f"{TMP}/lo-x",
        f"{TMP}/lo-1/../exapp.sock",
        f"{TMP}/lo-1/..",
        f"{TMP}/lo-1/.cache",
        f"{TMP}/lo-1/",
        f"{TMP}/lo-1//home",
        f"{TMP}/lo-12abc",
        "tmp/lo-1/home",
        f"{TMP}/lo-1/home\n",
        "/nc_app_pii_redaction_backend_data/work/1",
        f"{TMP}/other/lo-1",
    ],
)
@pytest.mark.parametrize("key", sorted(SOFFICE_ENV_VALUES))
def test_negative_a_soffice_value_outside_the_job_profile_is_refused(key: str, value: str) -> None:
    with pytest.raises(ValueError, match="inside the soffice job profile"):
        child.child_env({key: value}, profile="soffice")


def test_positive_control_other_children_keep_home_tmp() -> None:
    assert child.child_env(profile="render")["HOME"] == TMP
    assert "TMPDIR" not in child.child_env(profile="render")
    with pytest.raises(ValueError, match="not allowed"):
        child.child_env({"APP_SECRET": "x"}, profile="soffice")


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail needs Linux")
async def test_a_diagnosed_child_hands_back_its_cleaned_stderr(tmp_path: Path) -> None:
    # \\n: the child script needs the two characters backslash and n inside its
    # string literals, a real line break there is a SyntaxError (exit 1).
    script = (
        "import sys; sys.stderr.write(\"Error: cannot open '/data/Bescheid Meier.docx'\\n\"); "
        "sys.stderr.write('Fatal error at /secret/path\\n'); sys.exit(77)"
    )

    with pytest.raises(child.ChildFailed) as failure:
        await child.run_child([sys.executable, "-I", "-c", script], **_jailed(tmp_path), timeout_s=20, diagnose=True)

    assert failure.value.exit_code == 77
    assert failure.value.stderr_tail == "Error: cannot open <q> | Fatal error at <path>"


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail needs Linux")
async def test_without_diagnose_nothing_of_stderr_comes_back(tmp_path: Path) -> None:
    script = "import sys; sys.stderr.write('Fatal error\\n'); sys.exit(77)"

    with pytest.raises(child.ChildFailed) as failure:
        await child.run_child([sys.executable, "-I", "-c", script], **_jailed(tmp_path), timeout_s=20)

    # 77 proves the script ran to its end; a broken script would end with 1.
    assert failure.value.exit_code == 77
    assert failure.value.stderr_tail == ""


def test_the_soffice_tail_keeps_twelve_lines() -> None:
    raw = "".join(f"Fontconfig warning {n}\n" for n in range(30)).encode()
    lines = child.diagnostic_tail(raw, child.SOFFICE_TAIL_LINES).split(" | ")
    assert len(lines) == child.SOFFICE_TAIL_LINES == 12
    assert lines[-1] == "Fontconfig warning 29"
    # The default stays five lines for every other child.
    assert len(child.diagnostic_tail(raw).split(" | ")) == child.TAIL_LINES == 5
