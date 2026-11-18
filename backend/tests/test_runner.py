"""The runner: admission, one task at a time, the three tasks and their reports.

The queue, the gateway and LibreOffice are doubled; PyMuPDF renders for real
(one test even through the real child process), and the pre-check runs its
real code on a PDF unless a test hands in the answer of a child. Every report
the runner sends lands in one list, so the tests read the exact order of
stages and acks.
"""

import ast
import asyncio
import hashlib
import io
import json
import logging
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from pii_redaction_backend import nc
from pii_redaction_backend.intake import limits
from pii_redaction_backend.model import AckResult, Reason, Stage, Task
from pii_redaction_backend.runner import runner
from pii_redaction_backend.store import repo
from pii_redaction_backend.workers import child, soffice

TOKEN = "0123456789abcdef0123456789abcdef"  # noqa: S105 - a test value in the shape of a claim token
ETAG = "6a1f3c0e9b2d4"
# Linux numbers of the two rlimit signals (x86_64 and arm64 alike).
SIGXCPU = 24
SIGXFSZ = 25


def _verdict(**change: object) -> dict[str, object]:
    """A pre-check answer as the child writes it; ok for a two page PDF unless changed."""
    return {"verdict": "ok", "format": "pdf", "pages": 2, "signed": False, "ownerProtected": False} | change


def _docx_verdict(**change: object) -> dict[str, object]:
    return _verdict(format="docx", pages=None) | change


def _cleaned(**change: object) -> dict[str, object]:
    """A sanitize answer as the child writes it."""
    return {"verdict": "ok", "macrosRemoved": False, "externalLinksRemoved": 0} | change


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


def _is_file(path: Path) -> bool:
    return path.is_file()


def _is_dir(path: Path) -> bool:
    return path.is_dir()


def _converted(outdir: Path, src: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    pdf = outdir / f"{src.stem}.pdf"
    pdf.write_bytes(_pdf_bytes(3))
    return pdf


def _claim(
    task: Task = Task.ANALYZE,
    job_id: int = 7,
    *,
    expected: Any = "pdf",
    confirmed: bool = False,
) -> nc.Claim:
    return nc.Claim(
        job_id=job_id,
        task=task,
        token=TOKEN,
        file_id=42,
        user_id="alice",
        etag=ETAG,
        lease_seconds=120,
        expected=expected if task is Task.ANALYZE else None,
        confirmed=confirmed,
    )


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


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
        self.converted_sources: list[Path] = []
        self.fetches = 0
        self.child_gate: asyncio.Event | None = None
        # The error a child of this kind (render, precheck, sanitize, placeholder) raises.
        self.child_errors: dict[str, Exception] = {}
        self.convert_error: Exception | None = None
        # The answers of the children: None runs the real code, a dict is
        # written as JSON, a str as it is, and "missing" writes no file.
        self.verdict: object = None
        self.cleaned: object = None
        self.meta: dict[str, object] | None = None
        self.jail_marks = 0
        self.sleeps: list[float] = []
        self.beats = asyncio.Event()

    def mark_jail_failed(self) -> None:
        self.jail_marks += 1

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
        self.fetches += 1
        if self.fetch_stale:
            return nc.FetchResult(ok=False, stale=True, sha256=None, size=0, etag=None, http_status=409)
        if self.fetch_status != 200:
            return nc.FetchResult(ok=False, stale=False, sha256=None, size=0, etag=None, http_status=self.fetch_status)
        _write(target, self.source)
        digest = hashlib.sha256(self.source).hexdigest()
        return nc.FetchResult(ok=True, stale=False, sha256=digest, size=len(self.source), etag=ETAG, http_status=200)

    async def run_child(
        self,
        args: list[str],
        *,
        profile: str,
        cwd: Path,
        read: tuple[str, ...] = (),
        write: tuple[str, ...] = (),
        timeout_s: float | None = None,
    ) -> None:
        assert timeout_s is None or timeout_s > 0
        name = args[3].rsplit(".", 1)[-1]
        # Every Python child runs in the jail profile of its own kind; the
        # placeholder is a render of no source.
        assert profile == ("render" if name == "placeholder" else name)
        assert write == (str(cwd),)
        assert all(Path(path).is_relative_to(cwd) for path in read)
        self.events.append(("child", name, *args[4:]))
        if self.child_gate is not None and name == "render":
            await self.child_gate.wait()
        if name in self.child_errors:
            raise self.child_errors[name]
        if name == "precheck":
            self._precheck(args[4:])
        elif name == "sanitize":
            self._sanitize(args[4:])
        elif name == "render" and self.meta is not None:
            _write_json(Path(args[5]).with_name("meta.json"), self.meta)
        elif name == "render":
            from pii_redaction_backend.workers import render

            assert render.main(args[4:]) == 0
        else:
            from pii_redaction_backend.workers import placeholder

            assert placeholder.main(args[4:]) == 0
        assert _is_dir(cwd)

    def _answer(self, path: Path, answer: object) -> None:
        if answer == "missing":
            return
        if isinstance(answer, str):
            path.write_text(answer, encoding="utf-8")
        else:
            _write_json(path, answer)

    def _precheck(self, argv: list[str]) -> None:
        if self.verdict is None:
            from pii_redaction_backend.workers import precheck

            assert precheck.main(argv) == 0
            return
        self._answer(Path(argv[2]), self.verdict)

    def _sanitize(self, argv: list[str]) -> None:
        if self.cleaned is None:
            from pii_redaction_backend.workers import sanitize

            assert sanitize.main(argv) == 0
            return
        if isinstance(self.cleaned, dict) and self.cleaned.get("verdict") == "ok":
            shutil.copyfile(argv[0], argv[2])
        self._answer(Path(argv[3]), self.cleaned)

    async def convert(self, src: Path, outdir: Path, job_id: str, *_args: Any) -> Path:
        self.converted.append(job_id)
        self.converted_sources.append(src)
        assert src.suffix in {".docx", ".odt"}
        assert _is_file(src)
        if self.convert_error is not None:
            raise self.convert_error
        return _converted(outdir, src)

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
            "mark_jail_failed": self.mark_jail_failed,
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

    def children(self) -> list[str]:
        return [event[1] for event in self.events if event[0] == "child"]

    def stages(self) -> list[str]:
        return [event[1] for event in self.progress_events()]


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
        ("progress", "checking", None, None),
        ("progress", "rendering", 0, None),
        ("progress", "rendering", 1, 2),
    ]
    assert fake.children() == ["precheck", "render"]
    (ack,) = fake.acks()
    assert ack[1] == "review"
    assert ack[2]["pages_total"] == 2
    assert ack[2]["etag_seen"] == ETAG
    assert ack[2]["owner_protection_dropped"] is False
    assert "macros_removed" not in ack[2]
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


async def test_the_precheck_child_gets_the_source_the_expected_format_and_its_answer_file(fake: Fake) -> None:
    fake.claims = [_claim()]
    await fake.runner().run_once()

    (precheck,) = [event for event in fake.events if event[:2] == ("child", "precheck")]
    folder = fake.work_dir(7)
    assert precheck[2:] == (str(folder / "src"), "pdf", str(folder / "verdict.json"))


async def test_analyze_docx_cleans_then_converts_the_clean_copy(fake: Fake) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned(macrosRemoved=True, externalLinksRemoved=4)
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.stages() == ["fetching", "checking", "converting", "rendering", "rendering"]
    assert fake.children() == ["precheck", "sanitize", "render"]
    (sanitize,) = [event for event in fake.events if event[:2] == ("child", "sanitize")]
    folder = fake.work_dir(7)
    source, fmt, clean = sanitize[2:5]
    assert fmt == "docx"
    assert fake.converted == ["7"]
    # LibreOffice gets the cleaned copy, never the source (T-02-13).
    assert fake.converted_sources == [Path(clean)]
    assert Path(clean) != Path(source)
    assert Path(clean).parent == folder
    (ack,) = fake.acks()
    assert ack[1] == "review"
    assert ack[2]["pages_total"] == 3
    assert ack[2]["macros_removed"] is True
    assert ack[2]["external_links_removed"] == 4
    assert "owner_protection_dropped" not in ack[2]
    assert not list(folder.glob("src*")), "source and cleaned copy are deleted after rendering"


async def test_analyze_odt_runs_the_same_way(fake: Fake) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _verdict(format="odt", pages=None)
    fake.cleaned = _cleaned()
    fake.claims = [_claim(expected="odt")]
    await fake.runner().run_once()

    assert fake.children() == ["precheck", "sanitize", "render"]
    assert fake.converted_sources[0].suffix == ".odt"
    assert fake.acks()[0][2]["macros_removed"] is False


@pytest.mark.parametrize(
    "verdict",
    [
        "unsafe_content",
        "encrypted_pdf",
        "encrypted_document",
        "wrong_type",
        "damaged",
        "too_large",
        "too_many_pages",
        "unsupported_format",
    ],
)
async def test_a_refusal_of_the_precheck_fails_with_its_word_and_renders_nothing(fake: Fake, verdict: str) -> None:
    fake.verdict = _verdict(verdict=verdict, format=None, pages=None)
    fake.claims = [_claim()]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason(verdict)})]
    assert fake.children() == ["precheck"]
    assert fake.converted == []
    assert not list(fake.work_dir(7).glob("src*"))


async def test_a_real_precheck_refuses_bytes_that_are_no_pdf(fake: Fake) -> None:
    # The real pre-check code, not a written answer: a GIF claimed as PDF.
    fake.source = b"GIF89a not a document"
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.UNSUPPORTED_FORMAT})]
    assert not list(fake.work_dir(7).glob("src*"))


async def test_a_claim_without_a_format_fails_as_unsupported_before_any_download(fake: Fake) -> None:
    fake.claims = [_claim(expected=None)]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.UNSUPPORTED_FORMAT})]
    assert fake.fetches == 0
    assert fake.children() == []


@pytest.mark.parametrize(
    "answer",
    [
        _verdict(verdict="rocket"),
        _verdict(verdict="OK"),
        _verdict(verdict="signature_declined", format=None, pages=None),
        _verdict(verdict="render_failed", format=None, pages=None),
        _verdict(pages=0),
        _verdict(pages=-1),
        _verdict(pages=limits.MAX_PAGES + 1),
        _verdict(pages=True),
        _verdict(pages="2"),
        _verdict(pages=None),
        _verdict(signed="yes"),
        _verdict(signed=1),
        _verdict(ownerProtected=None),
        _verdict(format="docx"),
        _verdict(format="exe"),
        _verdict(format=None),
        _docx_verdict(pages=2),
        _docx_verdict(signed=True),
        _verdict(extra="x"),
        {key: value for key, value in _verdict().items() if key != "signed"},
        _verdict(verdict="damaged", format="pdf", pages=None),
        _verdict(verdict="damaged", format=None, pages=None, signed=True),
        ["ok"],
        "not json",
        "",
        "missing",
    ],
)
async def test_an_answer_outside_the_closed_list_is_damaged(fake: Fake, answer: object) -> None:
    fake.verdict = answer
    fake.claims = [_claim()]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.DAMAGED})]
    assert fake.children() == ["precheck"]


async def test_a_signed_pdf_without_confirmation_asks_first(fake: Fake) -> None:
    fake.verdict = _verdict(signed=True)
    fake.claims = [_claim()]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "confirm", {})]
    assert fake.children() == ["precheck"]
    assert fake.converted == []
    assert fake.stages() == ["fetching", "checking"]
    assert not list(fake.work_dir(7).glob("src*"))


async def test_a_signed_pdf_after_confirmation_takes_the_normal_way(fake: Fake) -> None:
    fake.verdict = _verdict(signed=True)
    fake.claims = [_claim(confirmed=True)]
    await fake.runner().run_once()

    assert fake.children() == ["precheck", "render"]
    assert fake.acks()[0][1] == "review"


async def test_an_owner_protected_pdf_is_reported_with_the_review(fake: Fake) -> None:
    fake.verdict = _verdict(ownerProtected=True)
    fake.claims = [_claim()]
    await fake.runner().run_once()

    (ack,) = fake.acks()
    assert ack[1] == "review"
    assert ack[2]["owner_protection_dropped"] is True


@pytest.mark.parametrize(
    "answer",
    [
        _cleaned(verdict="rocket"),
        _cleaned(macrosRemoved="yes"),
        _cleaned(externalLinksRemoved=-1),
        _cleaned(externalLinksRemoved=10_001),
        _cleaned(externalLinksRemoved=True),
        _cleaned(extra=1),
        "not json",
        "missing",
    ],
)
async def test_a_sanitize_answer_outside_the_closed_list_is_damaged(fake: Fake, answer: object) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = answer
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.DAMAGED})]
    assert fake.converted == []


async def test_a_sanitize_ok_without_the_clean_copy_is_damaged(fake: Fake) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = "missing"
    fake.claims = [_claim(expected="docx")]

    async def answer_only(args: list[str], **kwargs: Any) -> None:
        if args[3].endswith(".sanitize"):
            _write_json(Path(args[7]), _cleaned())
            return
        await fake.run_child(args, **kwargs)

    await fake.runner(run_child=answer_only).run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.DAMAGED})]
    assert fake.converted == []


async def test_a_refusal_of_the_cleaner_fails_with_its_word(fake: Fake) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned(verdict="unsafe_content")
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.UNSAFE_CONTENT})]
    assert fake.converted == []


@pytest.mark.parametrize("expected", ["pdf", "docx"])
async def test_more_than_the_page_cap_after_rendering_is_too_many_pages(fake: Fake, expected: str) -> None:
    if expected == "docx":
        fake.source = _docx_bytes()
        fake.verdict = _docx_verdict()
        fake.cleaned = _cleaned()
    else:
        fake.verdict = _verdict(pages=limits.MAX_PAGES)
    fake.meta = {"pages": limits.MAX_PAGES + 1, "width": 992, "height": 1403}
    fake.claims = [_claim(expected=expected)]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.TOO_MANY_PAGES})]


@pytest.mark.parametrize("expected", ["pdf", "docx"])
async def test_exactly_the_page_cap_goes_to_review(fake: Fake, expected: str) -> None:
    if expected == "docx":
        fake.source = _docx_bytes()
        fake.verdict = _docx_verdict()
        fake.cleaned = _cleaned()
    else:
        fake.verdict = _verdict(pages=limits.MAX_PAGES)
    fake.meta = {"pages": limits.MAX_PAGES, "width": 992, "height": 1403}
    fake.claims = [_claim(expected=expected)]
    await fake.runner().run_once()

    (ack,) = fake.acks()
    assert ack[1] == "review"
    assert ack[2]["pages_total"] == limits.MAX_PAGES


@pytest.mark.parametrize("kind", ["precheck", "sanitize"])
@pytest.mark.parametrize(
    "error",
    [child.ChildTimeout(), child.ChildFailed(-SIGXFSZ), child.ChildFailed(-SIGXCPU)],
    ids=["timeout", "sigxfsz", "sigxcpu"],
)
async def test_a_limit_hit_in_precheck_or_sanitize_is_too_large(fake: Fake, kind: str, error: Exception) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.child_errors = {kind: error}
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.TOO_LARGE})]
    assert fake.jail_marks == 0


@pytest.mark.parametrize("kind", ["precheck", "sanitize"])
async def test_another_crash_in_precheck_or_sanitize_is_damaged(fake: Fake, kind: str) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.child_errors = {kind: child.ChildFailed(-11)}
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.DAMAGED})]
    assert fake.jail_marks == 0


@pytest.mark.parametrize("kind", ["precheck", "sanitize", "render"])
async def test_exit_71_is_render_failed_and_marks_the_jail_once(fake: Fake, kind: str) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.child_errors = {kind: child.ChildFailed(71)}
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]
    assert fake.jail_marks == 1


async def test_exit_71_of_soffice_marks_the_jail_too(fake: Fake) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.convert_error = child.ChildFailed(71)
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()

    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]
    assert fake.jail_marks == 1


@pytest.mark.parametrize(
    "error",
    [child.ChildTimeout(), child.ChildFailed(-SIGXFSZ), child.ChildFailed(-SIGXCPU), child.ChildFailed(2)],
    ids=["timeout", "sigxfsz", "sigxcpu", "exit2"],
)
async def test_failures_of_render_or_soffice_stay_render_failed(fake: Fake, error: Exception) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.convert_error = error
    fake.claims = [_claim(expected="docx")]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]

    second = Fake(fake.root / "second")
    second.child_errors = {"render": error}
    second.claims = [_claim()]
    await second.runner().run_once()
    assert second.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]
    assert fake.jail_marks == second.jail_marks == 0


async def test_exit_71_of_the_placeholder_marks_the_jail(fake: Fake) -> None:
    fake.child_errors = {"placeholder": child.ChildFailed(71)}
    fake.claims = [_claim(Task.APPLY)]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]
    assert fake.jail_marks == 1


def test_the_child_failure_words() -> None:
    reason = runner._child_failure_reason
    assert reason("precheck", child.ChildTimeout()) is Reason.TOO_LARGE
    assert reason("sanitize", child.ChildFailed(-SIGXFSZ)) is Reason.TOO_LARGE
    assert reason("precheck", child.ChildFailed(-SIGXCPU)) is Reason.TOO_LARGE
    assert reason("precheck", child.ChildFailed(71)) is Reason.RENDER_FAILED
    assert reason("sanitize", child.ChildFailed(1)) is Reason.DAMAGED
    assert reason("render", child.ChildTimeout()) is Reason.RENDER_FAILED
    assert reason("soffice", child.ChildFailed(-SIGXFSZ)) is Reason.RENDER_FAILED


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


async def test_a_child_timeout_fails_as_render_failed(fake: Fake) -> None:
    fake.child_errors = {"render": child.ChildTimeout()}
    fake.claims = [_claim()]
    await fake.runner().run_once()
    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]
    assert runner.last_child() is not None


async def test_a_failed_child_logs_exit_code_signal_and_its_cleaned_tail(
    fake: Fake, caplog: pytest.LogCaptureFixture
) -> None:
    fake.child_errors = {"render": child.ChildFailed(77, "Fatal exception <path>")}
    fake.claims = [_claim()]
    with caplog.at_level(logging.INFO, logger="pii_redaction_backend"):
        await fake.runner().run_once()
    (record,) = [record for record in caplog.records if record.getMessage() == "render step failed"]
    assert record.__dict__["exit_code"] == 77
    assert record.__dict__["signal"] is None
    assert record.__dict__["stderr_tail"] == "Fatal exception <path>"
    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]


async def test_a_failed_check_logs_kind_exit_code_and_signal_only(fake: Fake, caplog: pytest.LogCaptureFixture) -> None:
    fake.child_errors = {"precheck": child.ChildFailed(-SIGXFSZ)}
    fake.claims = [_claim()]
    with caplog.at_level(logging.INFO, logger="pii_redaction_backend"):
        await fake.runner().run_once()
    (record,) = [record for record in caplog.records if record.getMessage() == "check step failed"]
    assert record.__dict__["child"] == "precheck"
    assert record.__dict__["signal"] == SIGXFSZ
    assert record.__dict__["reason"] == "too_large"


async def test_a_missing_soffice_template_fails_closed_and_logs_only_its_reason(
    fake: Fake, caplog: pytest.LogCaptureFixture
) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.convert_error = soffice.ProfileTemplateMissing("missing")
    fake.claims = [_claim(expected="docx")]
    with caplog.at_level(logging.INFO, logger="pii_redaction_backend"):
        await fake.runner().run_once()
    (record,) = [record for record in caplog.records if record.getMessage() == "render step failed"]
    assert record.__dict__["exc_type"] == "ProfileTemplateMissing"
    assert record.__dict__["reason"] == "missing"
    assert soffice.PROFILE_TEMPLATE not in str(record.__dict__)
    assert fake.acks() == [("ack", "failed", {"reason": Reason.RENDER_FAILED})]


async def test_negative_other_failures_log_no_template_reason(fake: Fake, caplog: pytest.LogCaptureFixture) -> None:
    fake.source = _docx_bytes()
    fake.verdict = _docx_verdict()
    fake.cleaned = _cleaned()
    fake.convert_error = soffice.ConversionFailed()
    fake.claims = [_claim(expected="docx")]
    with caplog.at_level(logging.INFO, logger="pii_redaction_backend"):
        await fake.runner().run_once()
    (record,) = [record for record in caplog.records if record.getMessage() == "render step failed"]
    assert record.__dict__["exc_type"] == "ConversionFailed"
    assert record.__dict__["reason"] is None


# -- no parser in the server process (T-02-49) -----------------------------------------

# What parses a user file: these run only in a jailed child.
_PARSERS = frozenset({"zipfile", "pymupdf", "fitz", "pikepdf", "lxml", "pypdf", "pdfminer", "docx", "odf"})
_CHILD_MODULES = frozenset(
    {
        "pii_redaction_backend.intake.magic",
        "pii_redaction_backend.intake.pdfcheck",
        "pii_redaction_backend.intake.zipcheck",
        "pii_redaction_backend.intake.xmlcheck",
        "pii_redaction_backend.intake.sanitize",
        "pii_redaction_backend.workers.precheck",
        "pii_redaction_backend.workers.sanitize",
        "pii_redaction_backend.workers.render",
    }
)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_runner_imports_no_parser() -> None:
    imported = _imports(Path(runner.__file__))
    assert not {name for name in imported if name.split(".")[0] in _PARSERS}
    assert not imported & _CHILD_MODULES
    # Positive control: the scanner sees the imports that are there.
    assert "pii_redaction_backend.workers.child" in imported
    assert "pii_redaction_backend.intake.limits" in imported


def test_sniff_is_gone() -> None:
    package = Path(runner.__file__).resolve().parents[1]
    assert not (package / "workers" / "sniff.py").exists()
    assert not hasattr(runner, "_typed_source")


async def test_the_heartbeat_repeats_the_stage_while_a_child_runs(fake: Fake) -> None:
    fake.child_gate = asyncio.Event()
    fake.claims = [_claim()]
    round_ = asyncio.ensure_future(fake.runner().run_once())
    await _until(lambda: "render" in fake.children())
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
    await _until(lambda: "render" in fake.children())
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

# On the runner of python.yml the interpreter (uv), the venv and the editable
# package live below /home/runner, which the render profile does not read; the
# jail then refuses the execv of the child with EACCES and ends with 71, which
# is the right, fail-closed answer. In the image all three live below /usr and
# /app (profiles.SYSTEM_READ). The test hands exactly these three folders to
# the jail as extra read paths, the same way _jailed() in test_child.py does;
# the profile itself stays as it ships.
_TEST_INTERPRETER: tuple[str, ...] = (
    sys.base_prefix,
    sys.prefix,
    str(Path(runner.__file__).resolve().parents[2]),
)


async def _with_the_test_interpreter(args: list[str], **kwargs: Any) -> None:
    kwargs["read"] = (*kwargs.get("read", ()), *_TEST_INTERPRETER)
    await child.run_child(args, **kwargs)


def test_the_test_interpreter_paths_are_only_the_interpreter_and_the_package() -> None:
    package_root = Path(runner.__file__).resolve().parents[2]
    assert (package_root / "pii_redaction_backend").is_dir()
    assert (sys.base_prefix, sys.prefix, str(package_root)) == _TEST_INTERPRETER


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail needs Linux")
async def test_analyze_through_the_real_render_child(fake: Fake) -> None:
    fake.claims = [_claim(job_id=9)]
    await fake.runner(run_child=_with_the_test_interpreter).run_once()

    (ack,) = fake.acks()
    assert ack[1] == "review", ack
    meta = json.loads((fake.work_dir(9) / "meta.json").read_text(encoding="utf-8"))
    assert meta["pages"] == 2
