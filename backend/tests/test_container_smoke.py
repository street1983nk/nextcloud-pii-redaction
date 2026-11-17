"""The first container test: the real image, the server as PID 1, /heartbeat and the sandbox state in /status.

Runs only inside the test stage of the image (sandbox.yml sets
PII_IN_CONTAINER=1) and is skipped everywhere else by the marker hook of
conftest.py. Behind HaRP (HP_SHARED_KEY set) the server listens on its unix
socket, otherwise on APP_PORT; nothing here leaves 127.0.0.1. It is also the
fallback of the bridge step until test_lo_network.py exists (plan 02-22).
"""

import os

import httpx
import pytest

from tests.conftest import record_measurement, signed_headers

pytestmark = [pytest.mark.container, pytest.mark.linux]

STATES = {"active", "unavailable"}


def _client() -> httpx.Client:
    if os.environ.get("HP_SHARED_KEY"):
        socket = os.environ.get("HP_EXAPP_SOCK", "/tmp/exapp.sock")  # noqa: S108 - the HaRP socket path
        return httpx.Client(transport=httpx.HTTPTransport(uds=socket), base_url="http://localhost", timeout=10)
    return httpx.Client(base_url=f"http://127.0.0.1:{os.environ['APP_PORT']}", timeout=10)


def test_the_heartbeat_answers() -> None:
    with _client() as client:
        response = client.get("/heartbeat")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_shows_the_sandbox_state() -> None:
    headers = signed_headers(secret=os.environ["PII_CANARY_SECRET"])
    with _client() as client:
        response = client.get("/status", headers=headers)
    assert response.status_code == 200
    sandbox = response.json()["sandbox"]
    assert sandbox is not None
    assert sandbox["seccomp"] in STATES
    assert sandbox["landlock"] in STATES
    assert isinstance(sandbox["landlockAbi"], int)
    assert sandbox["jail"] in {"ok", "failed"}
    record_measurement("sandbox_seccomp", sandbox["seccomp"])
    record_measurement("sandbox_landlock", sandbox["landlock"])
    record_measurement("sandbox_landlock_abi", sandbox["landlockAbi"])
    record_measurement("sandbox_jail", sandbox["jail"])


def test_positive_control_a_wrong_secret_is_refused() -> None:
    with _client() as client:
        response = client.get("/status", headers=signed_headers(secret="not-the-canary"))  # noqa: S106 - a wrong value
    assert response.status_code == 401
