"""The container routes: exactly the contract, signed only, files by id only.

appinfo/info.xml declares no route (test_store_metadata.py), so HaRP lets no
browser through; this file holds the application side: the list of routes is
exactly the three of 01-SKELETON.md plus the AppAPI lifecycle, every own route
answers 401 without a valid signature, and the file routes hand out nothing
but page 1 and a verified output.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pii_redaction_backend import config
from pii_redaction_backend.store import repo
from tests.conftest import signed_headers

OWN_ROUTES = ("/status", "/jobs/{job_id}/pages/{n}.png", "/jobs/{job_id}/output")
# nc_py_api's set_handlers: the lifecycle and the static l10n folder, both
# behind the same signature check except /heartbeat.
LIFECYCLE_ROUTES = ("/heartbeat", "/init", "/enabled", "/l10n")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture(autouse=True)
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("APP_PERSISTENT_STORAGE", str(tmp_path))
    return tmp_path


def _flatten(routes: list[object]) -> list[str]:
    """Paths of every route, also inside included routers (FastAPI keeps those lazily)."""
    paths: list[str] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            paths += _flatten(list(inner.routes))
        else:
            paths.append(str(getattr(route, "path", "")))
    return paths


def _paths(test_client: TestClient) -> list[str]:
    return _flatten(list(test_client.app.routes))  # pyright: ignore[reportAttributeAccessIssue]


def _page(job_id: int) -> None:
    folder = config.work_dir(job_id)
    folder.mkdir(parents=True)
    (folder / "page-1.png").write_bytes(PNG)


def _output(job_id: int, *, verified: bool) -> None:
    folder = config.work_dir(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "output.pdf").write_bytes(b"%PDF-1.7 placeholder")
    connection = repo.connect(config.state_db_path())
    repo.upsert_job(connection, job_id, task="apply", stage="done", now=1)
    if verified:
        repo.set_output(connection, job_id, sha256="a" * 64, size=20, now=1)
    connection.close()


def test_the_routes_are_exactly_the_contract(client: TestClient) -> None:
    assert sorted(_paths(client)) == sorted(OWN_ROUTES + LIFECYCLE_ROUTES)


@pytest.mark.parametrize("path", ["/status", "/jobs/7/pages/1.png", "/jobs/7/output"])
def test_every_own_route_refuses_an_unsigned_request(client: TestClient, path: str) -> None:
    _page(7)
    _output(7, verified=True)
    assert client.get(path).status_code == 401
    assert client.get(path, headers=signed_headers(secret="wrong")).status_code == 401  # noqa: S106 - a wrong test value


def test_page_one_comes_back_as_png_with_no_store(client: TestClient) -> None:
    _page(7)
    response = client.get("/jobs/7/pages/1.png", headers=signed_headers())

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_any_other_page_is_404(client: TestClient) -> None:
    _page(7)
    assert client.get("/jobs/7/pages/2.png", headers=signed_headers()).status_code == 404
    assert client.get("/jobs/0/pages/1.png", headers=signed_headers()).status_code == 404
    assert client.get("/jobs/8/pages/1.png", headers=signed_headers()).status_code == 404


def test_a_path_like_id_never_reaches_the_file_system(client: TestClient) -> None:
    _page(7)
    for path in ("/jobs/..%2F7/pages/1.png", "/jobs/7a/pages/1.png", "/jobs/7/pages/1a.png"):
        assert client.get(path, headers=signed_headers()).status_code in {404, 422}, path


def test_the_output_is_404_until_the_job_is_verified(client: TestClient) -> None:
    _output(7, verified=False)
    assert client.get("/jobs/7/output", headers=signed_headers()).status_code == 404

    _output(7, verified=True)
    response = client.get("/jobs/7/output", headers=signed_headers())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")


def test_no_route_answers_with_a_name_or_a_path(client: TestClient, storage: Path) -> None:
    body = client.get("/status", headers=signed_headers()).text
    assert str(storage) not in body
    assert "work" not in body
