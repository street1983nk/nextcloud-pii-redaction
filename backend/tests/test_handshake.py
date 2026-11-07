"""nc.fetch_handshake: the container asks the PHP app whether it is there.

The PHP app answers ``{version}`` in an OCS envelope (HandshakeController);
404 means not installed or not enabled, 403 a foreign caller, 412 that AppAPI
has not enabled this container yet. Fake transport, no network.
"""

import httpx
import pytest

from pii_redaction_backend import nc


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, follow_redirects=False)


async def test_a_200_returns_the_version_and_asks_the_right_path() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ocs": {"meta": {}, "data": {"version": "0.1.0"}}})

    async with _client(httpx.MockTransport(answer)) as client:
        assert await nc.fetch_handshake(client) == (200, "0.1.0")

    assert seen[0].method == "GET"
    assert seen[0].url.path == "/ocs/v2.php/apps/pii_redaction/api/v1/handshake"
    assert seen[0].headers["EX-APP-ID"] == "pii_redaction_backend"


@pytest.mark.parametrize("data", [{}, {"version": 3}, [], None])
async def test_a_200_without_a_string_version_has_no_version(data: object) -> None:
    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ocs": {"data": data}})

    async with _client(httpx.MockTransport(answer)) as client:
        assert await nc.fetch_handshake(client) == (200, None)


@pytest.mark.parametrize("status", [403, 404, 412, 500])
async def test_an_error_status_is_returned_as_it_came(status: int) -> None:
    async with _client(httpx.MockTransport(lambda _request: httpx.Response(status))) as client:
        assert await nc.fetch_handshake(client) == (status, None)


async def test_an_unreachable_instance_is_none() -> None:
    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async with _client(httpx.MockTransport(broken)) as client:
        assert await nc.fetch_handshake(client) == (None, None)


async def test_an_answer_that_is_not_json_has_no_version() -> None:
    async with _client(httpx.MockTransport(lambda _request: httpx.Response(200, text="<html>"))) as client:
        assert await nc.fetch_handshake(client) == (200, None)
