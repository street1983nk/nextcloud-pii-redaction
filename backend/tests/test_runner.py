"""The runner: admission, one task at a time, the three tasks and their reports.

The queue, the gateway and LibreOffice are doubled; PyMuPDF renders for real
(one test even through the real child process). Every report the runner sends
lands in one list, so the tests read the exact order of stages and acks.
"""

import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from pii_redaction_backend import nc
from pii_redaction_backend.model import AckResult, Reason, Stage, Task
from pii_redaction_backend.runner import runner
from pii_redaction_backend.store import repo
from pii_redaction_backend.workers import child

TOKEN = "0123456789abcdef0123456789abcdef"  # noqa: S105 - a test value in the shape of a claim token
ETAG = "6a1f3c0e9b2d4"


def _pdf_bytes(pages: int = 2) -> bytes:
    document = pymupdf.open()
    for number in range(1, pages + 1):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Testseite {number}")
    data = document.tobytes()
    document.close()
    return data


def _docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _is_dir(path: Path) -> bool:
    return path.is_dir()


def _converted(outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    pdf = outdir / "src.pdf"
    pdf.write_bytes(_pdf_bytes(3))
    return pdf


def _claim(task: Task = Task.ANALYZE, job_id: int = 7) -> nc.Claim:
    return nc.Claim(job_id=job_id, task=task, token=TOKEN, file_id=42, user_id="alice", etag=ETAG, lease_seconds=120)


class Fake:
    """The outside world of the runner, recording every call in order."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.events: list[tuple[Any, ...]] = []
        self.claims: list[nc.Claim] = []
        self.claim_calls = 0
        self.claim_gone: int | None = None
        self.rechecks = 0
        self.source = _pdf_bytes()
        self.fetch_status: int | None = 200
        self.fetch_stale = False
        self.progress_outcome = nc.Outcome.OK
        self.ack_outcomes: list[nc.Outcome] = []
        self.companion = True
        self.memory = True
        self.converted: list[str] = []
        self.child_gate: asyncio.Event | None = None
        self.child_error: Exception | None = None
        self.sleeps: list[float] = []
        self.beats = asyncio.Event()

    def work_dir(self, job_id: int) -> Path:
        return self.root / "work" / str(job_id)

    def state_db(self) -> Path:
        return self.root / "state.db"

    async def claim(self, _client: object) -> nc.Claim | None:
        self.claim_calls += 1
        if self.claim_gone is not None:
            raise nc.CompanionGone(self.claim_gone)
        return self.claims.pop(0) if self.claims else None

    async def recheck(self) -> None:
        # What companion.check_once would learn from the handshake: gone.
        self.rechecks += 1
        self.companion = False

    async def progress(
        self, _client: object, _job: nc.Claim, stage: Stage, done: int | None, total: int | None
    ) -> nc.Outcome:
        self.events.append(("progress", stage.value, done, total))
        return self.progress_outcome

    async def ack(self, _client: object, _job: nc.Claim, result: AckResult, **fields: Any) -> nc.Outcome:
        self.events.append(("ack", result.value, fields))
        return self.ack_outcomes.pop(0) if self.ack_outcomes else nc.Outcome.OK

    async def fetch(self, _client: object, _job: nc.Claim, target: Path, *, max_bytes: int) -> nc.FetchResult:
        assert max_bytes > 0
        if self.fetch_stale:
            return nc.FetchResult(ok=False, stale=True, sha256=None, size=0, etag=None, http_status=409)
        if self.fetch_status != 200:
            return nc.FetchResult(ok=False, stale=False, sha256=None, size=0, etag=None, http_status=self.fetch_status)
        _write(target, self.source)
        digest = hashlib.sha256(self.source).hexdigest()
        return nc.FetchResult(ok=True, stale=False, sha256=digest, size=len(self.source), etag=ETAG, http_status=200)

    async def run_child(self, args: list[str], *, timeout_s: float, cwd: Path) -> None:
        assert timeout_s > 0
        self.events.append(("child", args[3].rsplit(".", 1)[-1]))
        if self.child_gate is not None:
            await self.child_gate.wait()
        if self.child_error is not None:
            raise self.child_error
        name = args[3].rsplit(".", 1)[-1]
        if name == "render":
            from pii_redaction_backend.workers import render

            assert render.main(args[4:]) == 0
        else:
            from pii_redaction_backend.workers import placeholder

            assert placeholder.main(args[4:]) == 0
        assert _is_dir(cwd)

    async def convert(self, src: Path, outdir: Path, job_id: str, _timeout: float) -> Path:
        self.converted.append(job_id)
        assert src.suffix == ".docx"
        return _converted(outdir)

    async def sleep(self, seconds: float) -> None:
        # The fake clock: a heartbeat pause lasts until a test lets beats through.
        self.sleeps.append(seconds)
        if seconds == runner.HEARTBEAT_SECONDS:
            await self.beats.wait()
        await asyncio.sleep(0)

    def runner(self, **overrides: Any) -> runner.Runner:
        seams: dict[str, Any] = {
            "client_factory": object,
            "claim": self.claim,
            "progress": self.progress,
            "ack": self.ack,
            "fetch_source": self.fetch,
            "may_work": lambda: self.companion,
            "recheck_companion": self.recheck,
            "admit": lambda _kind: self.memory,
            "run_child": self.run_child,
            "convert": self.convert,
            "sleep": self.sleep,
            "now": lambda: 1_800_000_000,
            "state_db": self.state_db,
            "work_dir": self.work_dir,
        }
        seams.update(overrides)
        return runner.Runner(**seams)

    def progress_events(self) -> list[tuple[Any, ...]]:
        return [event for event in self.events if event[0] == "progress"]

    def acks(self) -> list[tuple[Any, ...]]:
        return [event for event in self.events if event[0] == "ack"]


async def _until(condition: Any, seconds: float = 5.0) -> None:
    """Let the loop run until condition() holds; fail after a deadline."""
    for _ in range(int(seconds / 0.005)):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


@pytest.fixture
def fake(tmp_path: Path) -> Fake:
    return Fake(tmp_path)


# -- admission --------------------------------------------------------------------


async def test_without_the_companion_no_claim_is_asked(fake: Fake) -> None:
    fake.companion = False
    assert await fake.runner().run_once() is False
    assert fake.claim_calls == 0


async def test_a_gone_queue_route_asks_the_handshake_at_once_and_claims_no_more(fake: Fake) -> None:
    # The PHP app was disabled: its queue route answers 404. The runner does
    # not wait for the five minute round of companion.py; it asks now, and the
    # next round claims nothing while the answer is missing.
    fake.claim_gone = 404
    worker = fake.runner()

    assert await worker.run_once() is False
    assert fake.rechecks == 1
    assert await worker.run_once() is False
    assert fake.claim_calls == 1
    assert fake.rechecks == 1
    assert fake.events == []


async def test_an_empty_queue_asks_no_handshake(fake: Fake) -> None:
    # Positive control of the rule above: an ordinary empty answer is no reason.
    assert await fake.runner().run_once() is False
    assert fake.claim_calls == 1
    assert fake.rechecks == 0


async def test_without_memory_no_claim_is_asked(fake: Fake) -> None:
    fake.memory = False
    assert await fake.runner().run_once() is False
    assert fake.claim_calls == 0


def test_the_idle_pause_doubles_up_to_ten_seconds() -> None:
    delay = runner.IDLE_MIN_SECONDS
    seen = []
    for _ in range(6):
        delay = runner.next_delay(False, delay)
        seen.append(delay)
    assert seen == [2.0, 4.0, 8.0, 10.0, 10.0, 10.0]
    assert runner.next_delay(True, 10.0) == 1.0


async def test_the_loop_ends_when_stop_is_set(fake: Fake) -> None:
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(fake.runner().run(stop), timeout=2)


async def test_two_rounds_never_work_at_the_same_time(fake: Fake) -> None:
    fake.claims = [_claim(Task.PURGE, 1), _claim(Task.PURGE, 2)]
    gate = asyncio.Event()
    inside: list[int] = []
    overlap: list[bool] = []

    async def slow_ack(_client: object, job: nc.Claim, _result: AckResult, **_fields: Any) -> nc.Outcome:
        overlap.append(bool(inside))
        inside.append(job.job_id)
        await gate.wait()
        inside.remove(job.job_id)
        return nc.Outcome.OK

    worker = fake.runner(ack=slow_ack)
    first = asyncio.ensure_future(worker.run_once())
    second = asyncio.ensure_future(worker.run_once())
    for _ in range(200):
        await asyncio.sleep(0.01)
        if inside:
            break
    for _ in range(10):
        await asyncio.sleep(0.01)
    assert inside == [1], "the second round must wait for the first"
    gate.set()
    assert await first is True
    assert await second is True
    assert overlap == [False, False]


# -- analyze ------------------------------------------------------------------------


async def test_analyze_pdf_reports_its_stages_and_acks_review(fake: Fake) -> None:
    fake.claims = [_claim()]
    assert await fake.runner().run_once() is True

    assert fake.progress_events() == [
        ("progress", "fetching", None, None),
        ("progress", "rendering", 0, None),
        ("progress", "rendering", 1, 2),
    ]
    (ack,) = fake.acks()
    assert ack[1] == "review"
    assert ack[2]["pages_total"] == 2
    assert ack[2]["etag_seen"] == ETAG
    width, height = ack[2]["image"]
    assert 985 <= width <= 1000
    assert height > width
    folder = fake.work_dir(7)
    assert (folder / "page-1.png").read_bytes().startswith(b"\x89PNG")
    assert not list(folder.glob("src*")), "the source is deleted after rendering"
    db = repo.connect(fake.state_db())
    row = repo.get_job(db, 7)
    db.close()
    assert row is not None
    assert row["stage"] == "done"
    assert row["src_sha256"] == hashlib.sha256(fake.source).hexdigest()


async def test_analyze_docx_converts_first(fake: Fake) -> None:
    fake.source = _docx_bytes()
    fake.claims = [_claim()]
    await fake.runner().run_once()

    stages = [event[1] for event in fake.progress_events()]
    assert stages == ["fetching", "converting", "rendering", "rendering"]
    assert fake.converted == ["7"]
    assert fake.acks()[0][2]["pages_total"] == 3


async def test_a_stale_source_sends_no_ack_and_clears_the_folder(fake: Fake) -> None:
    fake.fetch_stale = True
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == []
    assert not fake.work_dir(7).exists()


async def test_a_refused_download_fails_as_not_readable(fake: Fake) -> None:
    fake.fetch_status = 404
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.NOT_READABLE})]


async def test_an_unreachable_gateway_sends_no_ack(fake: Fake) -> None:
    fake.fetch_status = None
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == []


async def test_an_unknown_format_fails_as_unsupported(fake: Fake) -> None:
    fake.source = b"GIF89a not a document"
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.UNSUPPORTED_FORMAT})]
    assert not list(fake.work_dir(7).glob("src*"))


async def test_a_child_timeout_fails_as_render_failed(fake: Fake) -> None:
    fake.child_error = child.ChildTimeout()
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]
    assert runner.last_child() is not None


async def test_the_heartbeat_repeats_the_stage_while_a_child_runs(fake: Fake) -> None:
    fake.child_gate = asyncio.Event()
    fake.claims = [_claim()]
    round_ = asyncio.ensure_future(fake.runner().run_once())
    await _until(lambda: ("child", "render") in fake.events)
    fake.beats.set()
    await _until(lambda: len(fake.progress_events()) >= 5)
    fake.child_gate.set()
    await round_

    beats = [event for event in fake.progress_events() if event == ("progress", "rendering", 0, None)]
    assert len(beats) >= 3, "the stage of the running child is repeated"
    assert runner.HEARTBEAT_SECONDS in fake.sleeps
    assert fake.acks()[0][1] == "review"


async def test_a_refused_heartbeat_stops_the_task_without_ack(fake: Fake) -> None:
    fake.child_gate = asyncio.Event()  # never set: only the abort ends the child
    fake.claims = [_claim()]
    worker = fake.runner()
    round_ = asyncio.ensure_future(worker.run_once())
    await _until(lambda: ("child", "render") in fake.events)
    fake.progress_outcome = nc.Outcome.REFUSED
    fake.beats.set()
    assert await asyncio.wait_for(round_, timeout=2) is True
    assert fake.acks() == []
    assert not fake.work_dir(7).exists()


async def test_an_unreachable_ack_is_repeated(fake: Fake) -> None:
    fake.ack_outcomes = [nc.Outcome.UNREACHABLE, nc.Outcome.OK]
    fake.claims = [_claim(Task.PURGE)]
    await fake.runner().run_once()
    assert len(fake.acks()) == 2
    assert runner.ACK_RETRY_SECONDS in fake.sleeps


async def test_a_refused_ack_is_not_repeated(fake: Fake) -> None:
    fake.ack_outcomes = [nc.Outcome.REFUSED]
    fake.claims = [_claim(Task.PURGE)]
    await fake.runner().run_once()
    assert len(fake.acks()) == 1


# -- apply and purge ----------------------------------------------------------------


async def test_apply_acks_verified_with_hash_and_size_of_the_output(fake: Fake) -> None:
    fake.claims = [_claim(Task.APPLY)]
    await fake.runner().run_once()

    output = fake.work_dir(7) / "output.pdf"
    data = output.read_bytes()
    assert data.startswith(b"%PDF-")
    assert fake.acks() == [("ack", "verified", {"output": (hashlib.sha256(data).hexdigest(), len(data))})]
    db = repo.connect(fake.state_db())
    row = repo.get_job(db, 7)
    db.close()
    assert row is not None
    assert row["output_sha256"] == hashlib.sha256(data).hexdigest()


async def test_purge_removes_folder_and_row(fake: Fake) -> None:
    fake.claims = [_claim(Task.APPLY), _claim(Task.PURGE)]
    worker = fake.runner()
    await worker.run_once()
    assert fake.work_dir(7).exists()

    await worker.run_once()

    assert not fake.work_dir(7).exists()
    db = repo.connect(fake.state_db())
    assert repo.get_job(db, 7) is None
    db.close()
    assert fake.acks()[-1] == ("ack", "purged", {})


# -- the real child ------------------------------------------------------------------


async def test_analyze_through_the_real_render_child(fake: Fake) -> None:
    fake.claims = [_claim(job_id=9)]
    await fake.runner(run_child=child.run_child).run_once()

    (ack,) = fake.acks()
    assert ack[1] == "review", ack
    meta = json.loads((fake.work_dir(9) / "meta.json").read_text(encoding="utf-8"))
    assert meta["pages"] == 2
