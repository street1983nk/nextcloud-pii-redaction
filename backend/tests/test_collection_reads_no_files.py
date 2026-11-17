"""The collection of the container run needs no repository file outside the image (plan 02-12).

sandbox.yml runs `pytest -m container /app/tests` in the test stage of the
image, which holds tests/ and pyproject.toml but not ci/, the Dockerfile,
uv.lock or the workflows. pytest imports every module before -m deselects, so
one module that reads such a file at import ends the run with exit 2 before a
single container test ran (run 44015648807).

The check rebuilds that layout in a temporary folder, the image's /app with
nothing beside it, and collects there exactly as sandbox.yml does. A different
pattern from the fix (conftest.repo_text/ci_module): it does not look at how a
module reads, only whether the collection survives without the files.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from tests.conftest import BACKEND_ROOT

BAD_MODULE = """from tests.conftest import REPO_ROOT

SCRIPT = (REPO_ROOT / "ci" / "make_corpus.py").read_text(encoding="utf-8")


def test_uses_the_script() -> None:
    assert SCRIPT
"""


def _image_layout(root: Path) -> Path:
    """<root>/app with tests/ and pyproject.toml, as the test stage of the Dockerfile copies them."""
    app = root / "app"
    shutil.copytree(
        BACKEND_ROOT / "tests", app / "tests", ignore=shutil.ignore_patterns("__pycache__", "out", ".pytest_cache")
    )
    shutil.copy2(BACKEND_ROOT / "pyproject.toml", app / "pyproject.toml")
    return app


def _collect(app: Path, *marker: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - this interpreter with fixed arguments
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *marker, str(app / "tests")],
        cwd=app,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _selected(output: str) -> int:
    match = re.search(r"^(\d+)(?:/\d+)? tests? collected", output, re.MULTILINE)
    assert match is not None, output[-2000:]
    return int(match.group(1))


def test_the_container_collection_needs_no_file_outside_the_image(tmp_path: Path) -> None:
    app = _image_layout(tmp_path)
    assert not (tmp_path / "ci").exists()
    assert not (app / "Dockerfile").exists()
    assert not (app / "uv.lock").exists()

    result = _collect(app, "-m", "container")

    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    # The same container tests as in the full tree: none got lost on the way.
    full = _collect(BACKEND_ROOT, "-m", "container")
    assert full.returncode == 0, full.stdout[-3000:]
    assert _selected(result.stdout) == _selected(full.stdout) > 0


def test_positive_control_a_module_level_read_breaks_the_collection(tmp_path: Path) -> None:
    app = _image_layout(tmp_path)
    (app / "tests" / "test_reads_at_import.py").write_text(BAD_MODULE, encoding="utf-8")

    result = _collect(app, "-m", "container")

    assert result.returncode == 2
    assert "test_reads_at_import.py" in result.stdout
    assert "FileNotFoundError" in result.stdout
