"""Shared fixtures: the environment AppAPI would set, and signed request headers."""

import base64
import functools
import importlib.util
import json
import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from pii_redaction_backend import APP_ID

# backend/ holds the ExApp (package, Dockerfile, appinfo, l10n, pyproject);
# the repository root holds what both halves share (workflows, docs, READMEs).
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET = "test-secret-not-real"  # noqa: S105 - a test value, never a real secret
VERSION = "0.1.0"


@pytest.fixture(autouse=True)
def appapi_environment(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """What AppAPI hands every container, with values that are clearly not real.

    A container test (marker container) talks to the server that runs as PID 1
    in the same container and must see the environment that server got:
    HP_SHARED_KEY (so it uses the HaRP socket /tmp/exapp.sock), APP_PORT and
    APP_SECRET as sandbox.yml set them. It keeps that environment untouched.
    """
    if keeps_real_environment(frozenset(mark.name for mark in request.node.iter_markers())):
        return
    monkeypatch.setenv("APP_ID", APP_ID)
    monkeypatch.setenv("APP_SECRET", SECRET)
    monkeypatch.setenv("APP_VERSION", VERSION)
    monkeypatch.setenv("APP_PORT", "23000")
    monkeypatch.setenv("NEXTCLOUD_URL", "http://nextcloud.invalid")
    monkeypatch.delenv("HP_SHARED_KEY", raising=False)


def keeps_real_environment(markers: frozenset[str]) -> bool:
    """A test with these markers runs against the real container environment."""
    return "container" in markers


def signed_headers(user: str = "admin", secret: str = SECRET, app_id: str = APP_ID) -> dict[str, str]:
    """The three headers AppAPIAuthMiddleware checks."""
    token = base64.b64encode(f"{user}:{secret}".encode()).decode()
    return {"EX-APP-ID": app_id, "EX-APP-VERSION": VERSION, "AUTHORIZATION-APP-API": token, "AA-VERSION": "32.0.0"}


# -- repository files, read on first use --------------------------------------------------
#
# The test stage of the image carries tests/, pyproject.toml, appinfo/ and
# l10n/, but not ci/, the Dockerfile, uv.lock or the workflows. sandbox.yml
# collects every module there and keeps only -m container, so a module that
# reads such a file at import breaks the collection (exit 2) for tests it would
# never run. Read them inside the tests, through these two; a test that needs a
# missing file then fails loudly where it runs, nothing is skipped
# (tests/test_collection_reads_no_files.py holds the rule).


@functools.cache
def repo_text(path: Path) -> str:
    """The text of a repository file, read once per session."""
    return path.read_text(encoding="utf-8")


@functools.cache
def ci_module(name: str) -> ModuleType:
    """ci/<name>.py as a module, loaded once per session."""
    spec = importlib.util.spec_from_file_location(f"ci_{name}", REPO_ROOT / "ci" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The application with its lifespan entered."""
    from pii_redaction_backend.main import APP

    with TestClient(APP) as test_client:
        yield test_client


# -- the attack corpus (plan 02-07) ---------------------------------------------------


@pytest.fixture(scope="session")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, dict[str, object]]]:
    """ci/make_corpus.py once per session: the folder and its manifest."""
    spec = importlib.util.spec_from_file_location("ci_make_corpus", REPO_ROOT / "ci" / "make_corpus.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path_factory.mktemp("corpus")
    return folder, module.build(folder)


# The test stage of the image carries no ci/ (see repo_text above), so in the
# container the corpus is made on the runner by ci/make_corpus.py and mounted
# read only; sandbox.yml names the folder in this variable (plan 02-21).
CORPUS_ENV = "PII_CORPUS"


@pytest.fixture(scope="session")
def mounted_corpus() -> tuple[Path, dict[str, dict[str, object]]]:
    """The corpus sandbox.yml mounted into the container: the folder and its manifest."""
    return load_mounted_corpus(os.environ)


def load_mounted_corpus(env: Mapping[str, str]) -> tuple[Path, dict[str, dict[str, object]]]:
    """The corpus the variable names; fails loudly (never skips) when it names none."""
    root = env.get(CORPUS_ENV, "")
    manifest = Path(root) / "manifest.json"
    if not root or not manifest.is_file():
        pytest.fail(f"{CORPUS_ENV} names no corpus with manifest.json (sandbox.yml makes and mounts it)")
    return Path(root), json.loads(manifest.read_text(encoding="utf-8"))


# -- container and linux markers ---------------------------------------------------------
#
# Container tests (pytest -m container) run only inside the test stage of the
# image, where sandbox.yml sets PII_IN_CONTAINER=1 (plan 02-12); Linux tests
# need the kernel (seccomp, Landlock, /proc). Without this hook the full suite
# would fail on the Windows development machine, which has no Docker. A hook
# and not addopts: addopts would filter the container run in sandbox.yml as
# well. python.yml keeps -m "not container" (plan 02-02) and runs the Linux
# tests, because sys.platform is "linux" there.


def skip_reason(markers: frozenset[str], platform: str, env: Mapping[str, str]) -> str | None:
    """Why a test with these markers cannot run here, or None."""
    if "container" in markers and env.get("PII_IN_CONTAINER") != "1":
        return "container only"
    if "linux" in markers and platform != "linux":
        return "linux only"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        reason = skip_reason(frozenset(mark.name for mark in item.iter_markers()), sys.platform, os.environ)
        if reason is not None:
            item.add_marker(pytest.mark.skip(reason=reason))


# -- measurements of the container runs ---------------------------------------------------

OUT_DIR = Path(__file__).resolve().parent / "out"


def record_measurement(key: str, value: object, out_dir: Path = OUT_DIR) -> None:
    """Set one key in out/measurements.json, written atomically (sandbox.yml uploads it, plan 02-24 reads it)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "measurements.json"
    data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    data[key] = value
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
