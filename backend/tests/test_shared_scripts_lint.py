"""ruff over ../scripts and ../ci, the step "Lint and format check of the shared scripts" of python.yml.

`uv run ruff check .` in backend/ does not reach the scripts beside it, so
seven findings in ci/make_corpus.py surfaced only in CI (run 44015648663).
Here the same two commands run on every local test run, with the rule set of
pyproject.toml; the self test makes sure a finding in that tree does fail.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from tests.conftest import BACKEND_ROOT, REPO_ROOT

SHARED = ("scripts", "ci")


def _ruff(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - this interpreter's ruff with fixed arguments
        [sys.executable, "-m", "ruff", *arguments, "--no-cache"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_the_workflow_step_names_the_same_trees() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "python.yml").read_text(encoding="utf-8")
    assert "uv run ruff check ../scripts ../ci\n" in workflow
    assert "uv run ruff format --check ../scripts ../ci\n" in workflow


def test_the_shared_scripts_pass_ruff_check() -> None:
    paths = [str(REPO_ROOT / name) for name in SHARED]
    assert all(Path(path).is_dir() for path in paths)
    result = _ruff("check", *paths)
    assert result.returncode == 0, result.stdout[-4000:]


def test_the_shared_scripts_pass_ruff_format() -> None:
    result = _ruff("format", "--check", *(str(REPO_ROOT / name) for name in SHARED))
    assert result.returncode == 0, result.stdout[-4000:]


def test_positive_control_a_finding_in_ci_fails(tmp_path: Path) -> None:
    # A copy beside a copy of pyproject.toml, so the same rule set applies.
    shutil.copy2(BACKEND_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    sample = tmp_path / "ci" / "sample.py"
    sample.parent.mkdir()
    sample.write_text('VALUE = f"no placeholder"\n', encoding="utf-8")

    result = _ruff("check", str(sample), "--config", str(tmp_path / "pyproject.toml"))

    assert result.returncode == 1
    assert "F541" in result.stdout
