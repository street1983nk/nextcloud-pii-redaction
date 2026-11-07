"""nc.py: the queue client and the job bound source download, against a fake transport.

No request leaves the process: every test hands in an ``httpx.AsyncClient`` on
an ``httpx.MockTransport`` that records what the container sent and answers
like the PHP app would (OCS envelope, ``X-Pii-Etag``, 409 for a changed file).
"""

import base64
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from pii_redaction_backend import nc
from pii_redaction_backend.model import AckResult, Reason, Stage, Task
from tests.conftest import SECRET

TOKEN = "0123456789abcdef0123456789abcdef"  # noqa: S105 - a test value in the shape of a claim token
ETAG = "6a1f3c0e9b2d4"
CONTENT = b"%PDF-1.7 fake source bytes " * 200
CLAIM_ANSWER = {
    "jobId": 7,
    "task": "analyze",
    "token": TOKEN,
    "fileId": 42,
    "userId": "alice",
    "etag": ETAG,
    "leaseSeconds": 120,
}


def _ocs(data: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"ocs": {"meta": {"status": "ok"}, "data": data}})


class Recorder:
    """A fake PHP app: records each request and answers through a handler."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self), follow_redirects=False)

    def body(self, index: int = -1) -> dict[str, object]:
        return json.loads(self.requests[index].content)


def _entries(directory: Path) -> list[Path]:
    """What a directory holds, synchronous on purpose (no blocking call inside a coroutine)."""
    return sorted(directory.iterdir())


def _claim() -> nc.Claim:
    return nc.Claim(job_id=7, task=Task.ANALYZE, token=TOKEN, file_id=42, user_id="alice", etag=ETAG, lease_seconds=120)


# -- signed headers --------------------------------------------------------------


def test_queue_calls_carry_the_app_id_and_an_empty_user() -> None:
    headers = nc.app_api_headers()

    assert headers["EX-APP-ID"] == "pii_redaction_backend"
    assert base64.b64decode(headers["AUTHORIZATION-APP-API"]).decode() == f":{SECRET}"
    assert headers["OCS-APIRequest"] == "true"


def test_the_client_never_follows_a_redirect() -> None:
    client = nc.new_client()

    assert client.follow_redirects is False


# -- claim -----------------------------------------------------------------------


async def test_a_full_answer_is_a_claim() -> None:
    php = Recorder(lambda _request: _ocs(CLAIM_ANSWER))

    async with php.client() as client:
        claim = await nc.claim(client)

    assert claim == _claim()
    request = php.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/ocs/v2.php/apps/pii_redaction/api/v1/queue/claim"
    assert request.url.params["format"] == "json"
    assert request.headers["EX-APP-ID"] == "pii_redaction_backend"


@pytest.mark.parametrize("data", [{}, [], None, "no"])
async def test_an_empty_answer_is_no_claim(data: object) -> None:
    async with Recorder(lambda _request: _ocs(data)).client() as client:
        assert await nc.claim(client) is None


@pytest.mark.parametrize(
    "change",
    [
        {"task": "delete"},
        {"jobId": -3},
        {"jobId": True},
        {"jobId": "7x"},
        {"token": None},
        {"token": "not hex!"},
        {"etag": "e" * 41},
        {"etag": ""},
        {"fileId": 0},
        {"userId": ""},
        {"userId": "a" * 65},
        {"userId": "alice\nbob"},
        {"leaseSeconds": 0},
    ],
)
async def test_a_field_outside_its_shape_discards_the_claim(change: dict[str, object]) -> None:
    answer = CLAIM_ANSWER | change

    async with Recorder(lambda _request: _ocs(answer)).client() as client:
        assert await nc.claim(client) is None


async def test_a_missing_field_discards_the_claim() -> None:
    answer = {key: value for key, value in CLAIM_ANSWER.items() if key != "token"}

    async with Recorder(lambda _request: _ocs(answer)).client() as client:
        assert await nc.claim(client) is None


async def test_numbers_as_strings_are_accepted_like_ocs_may_send_them() -> None:
    answer = CLAIM_ANSWER | {"jobId": "7", "fileId": "42", "leaseSeconds": "120"}

    async with Recorder(lambda _request: _ocs(answer)).client() as client:
        assert await nc.claim(client) == _claim()


@pytest.mark.parametrize("status", [401, 403, 412, 500])
async def test_an_error_status_is_no_claim(status: int) -> None:
    async with Recorder(lambda _request: _ocs(CLAIM_ANSWER, status)).client() as client:
        assert await nc.claim(client) is None


async def test_a_network_error_is_no_claim() -> None:
    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async with Recorder(broken).client() as client:
        assert await nc.claim(client) is None


async def test_an_answer_that_is_not_json_is_no_claim() -> None:
    async with Recorder(lambda _request: httpx.Response(200, text="<html>")).client() as client:
        assert await nc.claim(client) is None


# -- progress and ack ------------------------------------------------------------


async def test_progress_sends_the_stage_and_the_pages() -> None:
    php = Recorder(lambda _request: _ocs({"ok": True}))

    async with php.client() as client:
        assert await nc.progress(client, _claim(), Stage.RENDERING, 0, 3) is True

    assert php.requests[0].url.path == "/ocs/v2.php/apps/pii_redaction/api/v1/queue/7/progress"
    assert php.body() == {"token": TOKEN, "stage": "rendering", "pagesDone": 0, "pagesTotal": 3}


async def test_progress_with_a_409_is_false() -> None:
    async with Recorder(lambda _request: _ocs(None, 409)).client() as client:
        assert await nc.progress(client, _claim(), Stage.FETCHING, None, None) is False


async def test_progress_refuses_a_word_outside_the_list_before_sending() -> None:
    php = Recorder(lambda _request: _ocs({"ok": True}))

    async with php.client() as client:
        with pytest.raises(ValueError, match="is not a valid"):
            await nc.progress(client, _claim(), "uploading", None, None)  # pyright: ignore[reportArgumentType]

    assert php.requests == []


async def test_ack_review_sends_the_closed_fields() -> None:
    php = Recorder(lambda _request: _ocs({"ok": True}))

    async with php.client() as client:
        done = await nc.ack(client, _claim(), AckResult.REVIEW, pages_total=3, etag_seen=ETAG, image=(992, 1403))

    assert done is True
    assert php.requests[0].url.path == "/ocs/v2.php/apps/pii_redaction/api/v1/queue/7/ack"
    assert php.body() == {
        "token": TOKEN,
        "result": "review",
        "pagesTotal": 3,
        "etagSeen": ETAG,
        "image": {"width": 992, "height": 1403},
    }


async def test_ack_failed_carries_the_reason_and_verified_the_output() -> None:
    php = Recorder(lambda _request: _ocs({"ok": True}))
    digest = hashlib.sha256(b"x").hexdigest()

    async with php.client() as client:
        assert await nc.ack(client, _claim(), AckResult.FAILED, reason=Reason.RENDER_FAILED)
        assert await nc.ack(client, _claim(), AckResult.VERIFIED, output=(digest, 1234))

    assert php.body(0) == {"token": TOKEN, "result": "failed", "reason": "render_failed"}
    assert php.body(1) == {"token": TOKEN, "result": "verified", "output": {"sha256": digest, "size": 1234}}


async def test_ack_with_a_409_is_false() -> None:
    async with Recorder(lambda _request: _ocs(None, 409)).client() as client:
        assert await nc.ack(client, _claim(), AckResult.PURGED) is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reason": "file.pdf"},
        {"output": ("not a hash", 3)},
        {"output": ("a" * 64, -1)},
        {"image": (0, 10)},
        {"pages_total": -1},
    ],
)
async def test_ack_refuses_values_outside_their_shape(kwargs: dict[str, object]) -> None:
    php = Recorder(lambda _request: _ocs({"ok": True}))

    async with php.client() as client:
        with pytest.raises(ValueError):  # noqa: PT011 - each shape has its own message
            await nc.ack(client, _claim(), AckResult.FAILED, **kwargs)  # pyright: ignore[reportArgumentType]

    assert php.requests == []


async def test_a_network_error_in_ack_is_false() -> None:
    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    async with Recorder(broken).client() as client:
        assert await nc.ack(client, _claim(), AckResult.PURGED) is False


# -- fetch_source ----------------------------------------------------------------


def _source(status: int = 200, *, content: bytes = CONTENT, etag: str | None = ETAG) -> Recorder:
    def answer(_request: httpx.Request) -> httpx.Response:
        headers = {"X-Pii-Etag": etag} if etag is not None else {}
        return httpx.Response(status, content=content, headers=headers)

    return Recorder(answer)


async def test_the_source_is_written_and_hashed_in_the_stream(tmp_path: Path) -> None:
    php = _source()
    target = tmp_path / "src"

    async with php.client() as client:
        result = await nc.fetch_source(client, _claim(), target, max_bytes=1 << 20)

    assert result == nc.FetchResult(
        ok=True,
        stale=False,
        sha256=hashlib.sha256(CONTENT).hexdigest(),
        size=len(CONTENT),
        etag=ETAG,
        http_status=200,
    )
    assert target.read_bytes() == CONTENT
    assert _entries(tmp_path) == [target]
    request = php.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/ocs/v2.php/apps/pii_redaction/api/v1/files/7"
    assert request.url.params["token"] == TOKEN


async def test_a_409_is_stale(tmp_path: Path) -> None:
    async with _source(409, content=b"").client() as client:
        result = await nc.fetch_source(client, _claim(), tmp_path / "src", max_bytes=1 << 20)

    assert (result.ok, result.stale, result.http_status) == (False, True, 409)
    assert _entries(tmp_path) == []


@pytest.mark.parametrize("status", [403, 404, 500])
async def test_a_refusal_is_not_ok_and_writes_nothing(tmp_path: Path, status: int) -> None:
    async with _source(status, content=b"<ocs/>").client() as client:
        result = await nc.fetch_source(client, _claim(), tmp_path / "src", max_bytes=1 << 20)

    assert (result.ok, result.stale, result.sha256, result.http_status) == (False, False, None, status)
    assert _entries(tmp_path) == []


async def test_more_than_max_bytes_is_not_ok_and_leaves_no_part_file(tmp_path: Path) -> None:
    async with _source().client() as client:
        result = await nc.fetch_source(client, _claim(), tmp_path / "src", max_bytes=len(CONTENT) - 1)

    assert result.ok is False
    assert _entries(tmp_path) == []


async def test_a_redirect_is_not_followed(tmp_path: Path) -> None:
    php = Recorder(lambda _request: httpx.Response(302, headers={"Location": "http://elsewhere.invalid/x"}))

    async with php.client() as client:
        result = await nc.fetch_source(client, _claim(), tmp_path / "src", max_bytes=1 << 20)

    assert (result.ok, result.http_status) == (False, 302)
    assert len(php.requests) == 1
    assert _entries(tmp_path) == []


@pytest.mark.parametrize("etag", [None, "", "e" * 41])
async def test_a_missing_or_broken_etag_header_is_not_ok(tmp_path: Path, etag: str | None) -> None:
    async with _source(etag=etag).client() as client:
        result = await nc.fetch_source(client, _claim(), tmp_path / "src", max_bytes=1 << 20)

    assert (result.ok, result.etag) == (False, None)
    assert _entries(tmp_path) == []


async def test_a_stream_that_breaks_off_is_not_ok(tmp_path: Path) -> None:
    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("peer closed")

    async with Recorder(broken).client() as client:
        result = await nc.fetch_source(client, _claim(), tmp_path / "src", max_bytes=1 << 20)

    assert (result.ok, result.http_status) == (False, None)
    assert _entries(tmp_path) == []


async def test_an_existing_target_is_replaced_only_on_success(tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.write_bytes(b"old")

    async with _source(409, content=b"").client() as client:
        await nc.fetch_source(client, _claim(), target, max_bytes=1 << 20)

    assert target.read_bytes() == b"old"
