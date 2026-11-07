"""The one worker of the container: ask for a task, do it, report it.

There is exactly one Runner per process and it holds ``asyncio.Semaphore(1)``:
two rounds never work at the same time (the PHP app enforces the same with its
slot row). A round asks for work only while the PHP app answered the handshake
(``companion.may_work``) and the memory guard admits the largest child of a
task (``admit("soffice")``, the format is unknown before the download). A job
that cannot start for lack of memory stays visibly in the queue.

Tasks (01-SKELETON.md):

- ``analyze``: source through the job bound gateway, format by magic bytes,
  DOCX/ODT to PDF with LibreOffice, page 1 as PNG, ``ack(review)``.
- ``apply``: the placeholder PDF without any source, ``ack(verified)`` with
  hash and size.
- ``purge``: delete ``work/<job>`` and the state row, ``ack(purged)``.

Everything that touches a foreign file runs in a child (workers/child.py).
While a task runs, a heartbeat repeats the current stage every 30 s, which
extends the lease; a refused report stops the task (the child is killed by
the cancellation) and deletes its folder. Logs carry ids, words and numbers.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pii_redaction_backend import companion, config, nc
from pii_redaction_backend.model import AckResult, Reason, Stage, Task
from pii_redaction_backend.resources import memory_guard
from pii_redaction_backend.store import repo
from pii_redaction_backend.workers import child, sniff, soffice

LOGGER = logging.getLogger(__name__)

IDLE_MIN_SECONDS: Final = 1.0
IDLE_MAX_SECONDS: Final = 10.0
HEARTBEAT_SECONDS: Final = 30.0
RENDER_TIMEOUT_SECONDS: Final = 60.0
SOFFICE_TIMEOUT_SECONDS: Final = 120.0
PLACEHOLDER_TIMEOUT_SECONDS: Final = 60.0
RENDER_DPI: Final = 120
ACK_ATTEMPTS: Final = 3
ACK_RETRY_SECONDS: Final = 2.0
PAGE_FILE: Final = "page-1.png"
META_FILE: Final = "meta.json"
OUTPUT_FILE: Final = "output.pdf"
SOURCE_STEM: Final = "src"
MAX_PAGES: Final = 100_000
MAX_SIDE: Final = 100_000
_SERVER_ERROR: Final = 500


@dataclass(frozen=True, slots=True)
class ChildRun:
    """The last child that ran: its kind, peak memory and duration, for /status."""

    kind: str
    rss_kb: int
    ms: int


# The one value /status shows; written after every child (key "last").
_LAST_CHILD: dict[str, ChildRun] = {}


def last_child() -> ChildRun | None:
    """The last child that ran in this process, or None before the first."""
    return _LAST_CHILD.get("last")


def next_delay(worked: bool, delay: float) -> float:
    """1 s after work, otherwise twice the last pause, at most 10 s."""
    return IDLE_MIN_SECONDS if worked else min(delay * 2, IDLE_MAX_SECONDS)


class _Abort(Exception):
    """The PHP app refused a report: stop the task, ack nothing."""


class _Fail(Exception):
    """The task ends as failed with a reason of the closed list."""

    def __init__(self, reason: Reason) -> None:
        super().__init__(reason.value)
        self.reason = reason


Client = Any


class Runner:
    """One claim at a time; every outside effect can be replaced for tests."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] = nc.new_client,
        claim: Callable[[Client], Awaitable[nc.Claim | None]] = nc.claim,
        progress: Callable[..., Awaitable[nc.Outcome]] = nc.progress_outcome,
        ack: Callable[..., Awaitable[nc.Outcome]] = nc.ack_outcome,
        fetch_source: Callable[..., Awaitable[nc.FetchResult]] = nc.fetch_source,
        may_work: Callable[[], bool] = companion.may_work,
        admit: Callable[[str], bool] = memory_guard.admit,
        run_child: Callable[..., Awaitable[None]] = child.run_child,
        convert: Callable[..., Awaitable[Path]] = soffice.convert,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], int] = lambda: int(time.time()),
        state_db: Callable[[], Path] = config.state_db_path,
        work_dir: Callable[[int], Path] = config.work_dir,
    ) -> None:
        self._slot = asyncio.Semaphore(1)
        self._client_factory = client_factory
        self._claim = claim
        self._progress = progress
        self._ack = ack
        self._fetch = fetch_source
        self._may_work = may_work
        self._admit = admit
        self._run_child = run_child
        self._convert = convert
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._state_db = state_db
        self._work_dir = work_dir
        self._client: Any = None
        self.busy = False
        self.delay = IDLE_MIN_SECONDS

    # -- the loop -----------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        """Rounds until ``stop`` is set: 1 s after work, doubling up to 10 s while idle."""
        self._client = self._client_factory()
        try:
            while not stop.is_set():
                try:
                    worked = await self.run_once()
                except Exception as exc:  # the loop must outlive any single round
                    LOGGER.error("runner round failed", extra={"exc_type": type(exc).__name__})
                    worked = False
                self.delay = next_delay(worked, self.delay)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.delay)
        finally:
            client, self._client = self._client, None
            closer = getattr(client, "aclose", None)
            if closer is not None:
                await closer()

    async def run_once(self) -> bool:
        """One round: True when a task was claimed and handled."""
        async with self._slot:
            if not self._may_work():
                return False
            if not self._admit("soffice"):
                LOGGER.info("not enough memory to take a task", extra={"reason": "out_of_memory"})
                return False
            if self._client is None:
                self._client = self._client_factory()
            claimed = await self._claim(self._client)
            if claimed is None:
                return False
            self.busy = True
            try:
                await self._handle(claimed)
            finally:
                self.busy = False
            return True

    # -- one task -----------------------------------------------------------------

    async def _handle(self, job: nc.Claim) -> None:
        started = self._clock()
        LOGGER.info("task claimed", extra={"job_id": job.job_id, "task": job.task.value})
        stage = _StageBox(Stage.WAITING)
        work = asyncio.ensure_future(self._dispatch(job, stage))
        beat = asyncio.ensure_future(self._heartbeat(job, stage, work))
        try:
            await work
        except asyncio.CancelledError:
            if not stage.aborted:
                raise
            LOGGER.info("task stopped by the PHP app", extra={"job_id": job.job_id, "task": job.task.value})
            await asyncio.to_thread(_remove, self._work_dir(job.job_id))
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beat
        duration = int((self._clock() - started) * 1000)
        LOGGER.info("task ended", extra={"job_id": job.job_id, "task": job.task.value, "duration_ms": duration})

    async def _dispatch(self, job: nc.Claim, stage: "_StageBox") -> None:
        if job.task is Task.ANALYZE:
            await self._analyze(job, stage)
        elif job.task is Task.APPLY:
            await self._apply(job, stage)
        else:
            await self._purge(job)

    async def _heartbeat(self, job: nc.Claim, stage: "_StageBox", work: "asyncio.Future[None]") -> None:
        """Repeat the current stage while the task runs; a refusal cancels the task."""
        while not work.done():
            await self._sleep(HEARTBEAT_SECONDS)
            if work.done():
                return
            outcome = await self._progress(self._client, job, stage.value, stage.done, stage.total)
            if outcome is nc.Outcome.REFUSED:
                stage.aborted = True
                work.cancel()
                return

    async def _report(
        self, job: nc.Claim, stage: "_StageBox", value: Stage, done: int | None, total: int | None
    ) -> None:
        stage.value, stage.done, stage.total = value, done, total
        await self._db(
            lambda db: repo.upsert_job(db, job.job_id, task=job.task, stage=value, now=self._now(), pages_total=total)
        )
        outcome = await self._progress(self._client, job, value, done, total)
        if outcome is nc.Outcome.REFUSED:
            raise _Abort

    async def _close(self, job: nc.Claim, result: AckResult, **fields: Any) -> None:
        """ack, repeated while the instance does not answer; a refusal ends it."""
        for attempt in range(1, ACK_ATTEMPTS + 1):
            outcome = await self._ack(self._client, job, result, **fields)
            if outcome is nc.Outcome.OK:
                return
            if outcome is nc.Outcome.REFUSED:
                LOGGER.info("ack refused", extra={"job_id": job.job_id, "status": result.value})
                return
            LOGGER.info("ack not delivered", extra={"job_id": job.job_id, "attempt": attempt})
            if attempt < ACK_ATTEMPTS:
                await self._sleep(ACK_RETRY_SECONDS * attempt)

    async def _fail(self, job: nc.Claim, reason: Reason) -> None:
        LOGGER.info("task failed", extra={"job_id": job.job_id, "task": job.task.value, "reason": reason.value})
        await asyncio.to_thread(_remove_sources, self._work_dir(job.job_id))
        await self._close(job, AckResult.FAILED, reason=reason)

    # -- analyze ------------------------------------------------------------------

    async def _analyze(self, job: nc.Claim, stage: "_StageBox") -> None:
        folder = self._work_dir(job.job_id)
        try:
            await asyncio.to_thread(_fresh_folder, folder)
            await self._report(job, stage, Stage.FETCHING, None, None)
            fetched = await self._fetch(self._client, job, folder / SOURCE_STEM, max_bytes=config.MAX_SOURCE_BYTES)
            if fetched.stale:
                # The PHP app already set the job stale; nothing to report.
                await asyncio.to_thread(_remove, folder)
                return
            if not fetched.ok:
                if fetched.http_status is None or fetched.http_status >= _SERVER_ERROR:
                    # No usable answer: the lease runs out and the job is handed out again.
                    await asyncio.to_thread(_remove, folder)
                    return
                raise _Fail(Reason.NOT_READABLE)
            if fetched.sha256 is not None:
                digest = fetched.sha256
                await self._db(
                    lambda db: repo.set_source(db, job.job_id, sha256=digest, size=fetched.size, now=self._now())
                )

            source = await asyncio.to_thread(_typed_source, folder)
            if source is None:
                raise _Fail(Reason.UNSUPPORTED_FORMAT)
            pdf = source
            if source.suffix != ".pdf":
                await self._report(job, stage, Stage.CONVERTING, None, None)
                pdf = await self._timed(
                    "soffice", self._convert(source, folder / "pdf", str(job.job_id), SOFFICE_TIMEOUT_SECONDS)
                )

            await self._report(job, stage, Stage.RENDERING, 0, None)
            args = child.python_child("render", str(pdf), str(folder / PAGE_FILE), str(RENDER_DPI))
            await self._timed("render", self._run_child(args, timeout_s=RENDER_TIMEOUT_SECONDS, cwd=folder))
            pages, width, height = await asyncio.to_thread(_read_meta, folder / META_FILE)
            await self._report(job, stage, Stage.RENDERING, 1, pages)
        except _Abort:
            await asyncio.to_thread(_remove, folder)
            return
        except _Fail as failure:
            await self._fail(job, failure.reason)
            return
        except (child.ChildTimeout, child.ChildFailed, soffice.ConversionFailed, ValueError, OSError) as exc:
            LOGGER.info("render step failed", extra={"job_id": job.job_id, "exc_type": type(exc).__name__})
            await self._fail(job, Reason.RENDER_FAILED)
            return

        # Only the page image stays; the source and the converted PDF go now.
        await asyncio.to_thread(_remove_sources, folder)
        await self._db(lambda db: repo.upsert_job(db, job.job_id, task=job.task, stage=Stage.DONE, now=self._now()))
        await self._close(job, AckResult.REVIEW, pages_total=pages, etag_seen=fetched.etag, image=(width, height))

    # -- apply --------------------------------------------------------------------

    async def _apply(self, job: nc.Claim, stage: "_StageBox") -> None:
        folder = self._work_dir(job.job_id)
        output = folder / OUTPUT_FILE
        try:
            await asyncio.to_thread(_ensure_folder, folder)
            await self._report(job, stage, Stage.RENDERING, None, None)
            args = child.python_child("placeholder", str(output), str(job.job_id))
            await self._timed("placeholder", self._run_child(args, timeout_s=PLACEHOLDER_TIMEOUT_SECONDS, cwd=folder))
            digest, size = await asyncio.to_thread(_hash_file, output)
        except _Abort:
            await asyncio.to_thread(_remove, folder)
            return
        except (child.ChildTimeout, child.ChildFailed, OSError) as exc:
            LOGGER.info("placeholder step failed", extra={"job_id": job.job_id, "exc_type": type(exc).__name__})
            await self._fail(job, Reason.RENDER_FAILED)
            return
        await self._db(lambda db: repo.upsert_job(db, job.job_id, task=job.task, stage=Stage.DONE, now=self._now()))
        await self._db(lambda db: repo.set_output(db, job.job_id, sha256=digest, size=size, now=self._now()))
        await self._close(job, AckResult.VERIFIED, output=(digest, size))

    # -- purge --------------------------------------------------------------------

    async def _purge(self, job: nc.Claim) -> None:
        await asyncio.to_thread(_remove, self._work_dir(job.job_id))
        await self._db(lambda db: repo.delete_job(db, job.job_id))
        await self._close(job, AckResult.PURGED)

    # -- helpers ------------------------------------------------------------------

    async def _timed[T](self, kind: str, step: Awaitable[T]) -> T:
        """Await a child step and remember kind, peak memory and duration."""
        started = self._clock()
        try:
            return await step
        finally:
            ms = int((self._clock() - started) * 1000)
            rss = child.peak_child_rss_kb()
            _LAST_CHILD["last"] = ChildRun(kind=kind, rss_kb=rss, ms=ms)
            LOGGER.info("child ended", extra={"child": kind, "rss_kb": rss, "duration_ms": ms})

    async def _db(self, work: Callable[[Any], None]) -> None:
        path = self._state_db()

        def locked() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = repo.connect(path)
            try:
                work(connection)
            finally:
                connection.close()

        await asyncio.to_thread(locked)


@dataclass
class _StageBox:
    """The stage the heartbeat repeats, shared between the task and its heartbeat."""

    value: Stage
    done: int | None = None
    total: int | None = None
    aborted: bool = False


# -- file helpers (run in threads) ----------------------------------------------------


def _fresh_folder(folder: Path) -> None:
    """An empty folder for the job, only the owner may enter (0700)."""
    shutil.rmtree(folder, ignore_errors=True)
    _ensure_folder(folder)


def _ensure_folder(folder: Path) -> None:
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)


def _remove(folder: Path) -> None:
    shutil.rmtree(folder, ignore_errors=True)


def _remove_sources(folder: Path) -> None:
    """Delete the source in every form; the page image and meta.json stay."""
    for path in folder.glob(f"{SOURCE_STEM}*"):
        path.unlink(missing_ok=True)
    shutil.rmtree(folder / "pdf", ignore_errors=True)


def _typed_source(folder: Path) -> Path | None:
    """The source renamed to src.<format> (LibreOffice needs the suffix), or None."""
    raw = folder / SOURCE_STEM
    kind = sniff.detect(raw)
    if kind is None:
        return None
    typed = folder / f"{SOURCE_STEM}.{kind}"
    raw.replace(typed)
    return typed


def _read_meta(path: Path) -> tuple[int, int, int]:
    """pages, width and height out of the render child's meta.json, each checked."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "meta.json is not an object"
        raise ValueError(msg)
    values = []
    for key, ceiling in (("pages", MAX_PAGES), ("width", MAX_SIDE), ("height", MAX_SIDE)):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
            msg = "meta.json value out of range"
            raise ValueError(msg)
        values.append(value)
    return values[0], values[1], values[2]


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
            size += len(chunk)
    if size == 0:
        msg = "empty output"
        raise OSError(msg)
    return digest.hexdigest(), size
