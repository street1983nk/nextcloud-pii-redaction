"""The other direction of the counterpart state: is the PHP app there?

``nc.fetch_handshake`` is replaced by a script of answers; the HTTP side of it
is tested in test_handshake.py.
"""

import asyncio
import io
import json
import logging
from collections.abc import Iterator

import pytest

from pii_redaction_backend import companion, logs, nc

CANARY = "PIIKANARIE7Q4XZ9"


class Handshakes:
    """A scripted fetch_handshake; the last answer repeats."""

    def __init__(self, *answers: tuple[int | None, str | None]) -> None:
        self.answers = list(answers)
        self.calls = 0

    async def __call__(self, _client: object = None) -> tuple[int | None, str | None]:
        self.calls += 1
        if len(self.answers) > 1:
            return self.answers.pop(0)
        return self.answers[0]


@pytest.fixture(autouse=True)
def fresh_state() -> Iterator[None]:
    companion.reset()
    yield
    companion.reset()


def _script(monkeypatch: pytest.MonkeyPatch, *answers: tuple[int | None, str | None]) -> Handshakes:
    script = Handshakes(*answers)
    monkeypatch.setattr(nc, "fetch_handshake", script)
    return script


def test_nothing_asked_yet_is_unknown_and_no_work() -> None:
    assert companion.current().state == "unknown"
    assert companion.may_work() is False


async def test_a_200_with_the_same_version_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _script(monkeypatch, (200, "0.1.0"))

    state = await companion.check_once()

    assert (state.state, state.version) == ("ok", "0.1.0")
    assert state.checked_at is not None
    assert companion.may_work() is True


@pytest.mark.parametrize("status", [403, 404])
async def test_a_404_or_403_is_missing_at_once(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    _script(monkeypatch, (status, None))

    state = await companion.check_once()

    assert (state.state, state.version) == ("missing", None)
    assert companion.may_work() is False


async def test_a_412_before_the_enable_call_is_unknown_and_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _script(monkeypatch, (412, None))

    seen = [(await companion.check_once()).state for _ in range(5)]

    assert seen == ["unknown"] * 5


async def test_a_network_failure_is_unknown_and_missing_after_three_in_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    _script(monkeypatch, (None, None))

    seen = [(await companion.check_once()).state for _ in range(4)]

    assert seen == ["unknown", "unknown", "missing", "missing"]


async def test_a_success_in_between_resets_the_failure_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _script(monkeypatch, (None, None), (None, None), (200, "0.1.0"), (500, None), (None, None))

    seen = [(await companion.check_once()).state for _ in range(5)]

    assert seen == ["unknown", "unknown", "ok", "unknown", "unknown"]


@pytest.mark.parametrize("version", [None, "", "latest", CANARY, "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0"])
async def test_a_200_without_a_valid_version_is_unknown(monkeypatch: pytest.MonkeyPatch, version: str | None) -> None:
    _script(monkeypatch, (200, version))

    state = await companion.check_once()

    assert (state.state, state.version) == ("unknown", None)


async def test_a_change_to_missing_is_logged_once_without_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    logs.configure("info")
    _script(monkeypatch, (404, None))

    await companion.check_once()
    await companion.check_once()

    lines = [json.loads(text) for text in buffer.getvalue().strip().splitlines()]
    changes = [line for line in lines if line["msg"] == "companion state changed"]
    assert len(changes) == 1
    assert changes[0]["level"] == "warning"
    assert (changes[0]["companion"], changes[0]["reason"], changes[0]["http_status"]) == ("missing", "not_found", 404)


async def test_refresh_asks_again_while_unknown_and_not_while_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script(monkeypatch, (412, None), (200, "0.1.0"))

    await companion.refresh_if_stale()
    await companion.refresh_if_stale()
    await companion.refresh_if_stale()

    assert script.calls == 2
    assert companion.current().state == "ok"


async def test_the_periodic_check_survives_a_failing_round(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rounds = 0

    async def broken() -> companion.CompanionState:
        nonlocal rounds
        rounds += 1
        if rounds >= 2:
            raise asyncio.CancelledError
        raise RuntimeError(CANARY)

    monkeypatch.setattr(companion, "check_once", broken)

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await companion.run_periodic(interval_s=0, retry_s=0)

    assert rounds == 2
    record = next(record for record in caplog.records if record.getMessage() == "companion check failed")
    assert getattr(record, "exc_type", None) == "RuntimeError"
    assert record.exc_info is None
