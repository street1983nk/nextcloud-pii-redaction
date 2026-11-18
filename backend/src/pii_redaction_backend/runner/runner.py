"""The one worker of the container: ask for a task, do it, report it.

There is exactly one Runner per process and it holds ``asyncio.Semaphore(1)``:
two rounds never work at the same time (the PHP app enforces the same with its
slot row). A round asks for work only while the PHP app answered the handshake
(``companion.may_work``) and the memory guard admits the largest child of a
task (``admit("soffice")``, the format is unknown before the download). A job
that cannot start for lack of memory stays visibly in the queue. When the
queue route answers 403 or 404 (the PHP app was disabled or removed), the
round asks the handshake at once (``companion.check_once``), so the container
reports the companion missing within one round and claims nothing more,
instead of after the next five minute check (plan 18, PLAT-02).

Tasks (01-SKELETON.md):

- ``analyze``: source through the job bound gateway, then the pre-check in a
  jailed child (stage ``checking``, SAFE-02). A refusal ends the job with its
  word; a signed PDF the initiator has not confirmed yet ends with
  ``ack(confirm)`` (D-02-04). DOCX/ODT go through the cleaner child first
  (SAFE-03) and LibreOffice only ever sees the cleaned copy. Page 1 as PNG,
  the page count against the one cap of intake.limits (D-02-08), then
  ``ack(review)`` with what the pre-check and the cleaner changed (D-02-10,
  D-02-12). The server process parses no user file: it only reads the closed
  answers of the children and checks them again (T-02-15, T-02-49).
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
from typing import Any, Final, Literal

from pii_redaction_backend import companion, config, nc
from pii_redaction_backend.intake import limits
from pii_redaction_backend.intake.verdict import OK, VERDICTS
from pii_redaction_backend.model import AckResult, Reason, Stage, Task
from pii_redaction_backend.resources import memory_guard
from pii_redaction_backend.sandbox import probe
from pii_redaction_backend.store import repo
from pii_redaction_backend.workers import child, soffice

LOGGER = logging.getLogger(__name__)

IDLE_MIN_SECONDS: Final = 1.0
IDLE_MAX_SECONDS: Final = 10.0
HEARTBEAT_SECONDS: Final = 30.0
# Every child runs within the wall clock of its jail profile (sandbox/profiles.py);
# the runner names no time limit of its own.
RENDER_DPI: Final = 120
ACK_ATTEMPTS: Final = 3
ACK_RETRY_SECONDS: Final = 2.0
PAGE_FILE: Final = "page-1.png"
META_FILE: Final = "meta.json"
VERDICT_FILE: Final = "verdict.json"
SANITIZE_FILE: Final = "sanitize.json"
OUTPUT_FILE: Final = "output.pdf"
# The source, its typed name and the cleaned copy all start with this stem, so
# _remove_sources takes every form of the user file in one sweep.
SOURCE_STEM: Final = "src"
CLEAN_STEM: Final = "src-clean"
# Plausibility caps of the protocol (QueueController::MAX_PAGES): an answer
# beyond them is broken. The page cap for the user is limits.MAX_PAGES (300,
# D-02-08), checked after rendering with its own word too_many_pages.
MAX_PAGES: Final = 100_000
MAX_SIDE: Final = 100_000
_SERVER_ERROR: Final = 500
# The child gave up because a layer of the jail was offered but could not be
# loaded (sandbox/jail.py EXIT_LAYER_FAILED); the admin has to see it (D-02-11).
_EXIT_LAYER_FAILED: Final = 71
# Linux numbers (x86_64 and arm64) of the signals the kernel sends at
# RLIMIT_CPU and RLIMIT_FSIZE; asyncio reports a killed child as minus the number.
_SIGXCPU: Final = 24
_SIGXFSZ: Final = 25
# The children that judge the file itself: a limit hit there means the file is too large.
_CHECK_CHILDREN: Final = frozenset({"precheck", "sanitize"})
_VERDICT_KEYS: Final = frozenset({"verdict", "format", "pages", "signed", "ownerProtected"})
_SANITIZE_KEYS: Final = frozenset({"verdict", "macrosRemoved", "externalLinksRemoved"})


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


@dataclass(frozen=True, slots=True)
class Verdict:
    """The checked answer of the pre-check child (workers/precheck.py)."""

    verdict: str
    format: Literal["pdf", "docx", "odt"] | None
    pages: int | None
    signed: bool
    owner_protected: bool


@dataclass(frozen=True, slots=True)
class Cleaned:
    """The checked answer of the cleaner child (workers/sanitize.py)."""

    verdict: str
    macros_removed: bool
    external_links_removed: int


def _child_failure_reason(kind: str, exc: Exception) -> Reason:
    """The word for a child that did not end well.

    Exit 71 is the jail, not the file: render_failed (the runner marks the jail
    as failed besides). In precheck and sanitize, the time limit and the
    rlimit signals SIGXCPU and SIGXFSZ mean the file asks for more than a safe
    analysis gives: too_large; any other crash there is a file the parsers
    could not take: damaged. In render and soffice every failure stays
    render_failed.
    """
    if isinstance(exc, child.ChildFailed) and exc.exit_code == _EXIT_LAYER_FAILED:
        return Reason.RENDER_FAILED
    if kind not in _CHECK_CHILDREN:
        return Reason.RENDER_FAILED
    if isinstance(exc, child.ChildTimeout):
        return Reason.TOO_LARGE
    if isinstance(exc, child.ChildFailed) and exc.signal in {_SIGXCPU, _SIGXFSZ}:
        return Reason.TOO_LARGE
    return Reason.DAMAGED


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
        recheck_companion: Callable[[], Awaitable[object]] = companion.check_once,
        admit: Callable[[str], bool] = memory_guard.admit,
        run_child: Callable[..., Awaitable[None]] = child.run_child,
        convert: Callable[..., Awaitable[Path]] = soffice.convert,
        mark_jail_failed: Callable[[], None] = probe.mark_jail_failed,
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
        self._recheck_companion = recheck_companion
        self._admit = admit
        self._run_child = run_child
        self._convert = convert
        self._mark_jail_failed = mark_jail_failed
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
            try:
                claimed = await self._claim(self._client)
            except nc.CompanionGone:
                # The handshake decides; while it says missing, may_work is
                # false and the next round asks for nothing.
                await self._recheck_companion()
                return False
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
            if job.expected is None:
                # The PHP app names no format: the file is gone or no longer
                # a PDF, DOCX or ODT (plan 02-15). Nothing to download.
                raise _Fail(Reason.UNSUPPORTED_FORMAT)
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

            await self._report(job, stage, Stage.CHECKING, None, None)
            verdict = await self._precheck(job, folder, job.expected)
            if verdict.verdict != OK:
                raise _Fail(Reason(verdict.verdict))
            if verdict.signed and not job.confirmed:
                # The signature is lost by any redaction: the user decides
                # first (D-02-04). Confirmed, the job comes back to the queue.
                LOGGER.info("signature needs confirmation", extra={"job_id": job.job_id})
                await asyncio.to_thread(_remove_sources, folder)
                await self._close(job, AckResult.CONFIRM)
                return
            source = await asyncio.to_thread(_name_source, folder, job.expected)
            flags: dict[str, Any]
            if job.expected == "pdf":
                pdf = source
                flags = {"owner_protection_dropped": verdict.owner_protected}
            else:
                clean, cleaned = await self._sanitize(job, folder, source, job.expected)
                flags = {
                    "macros_removed": cleaned.macros_removed,
                    "external_links_removed": cleaned.external_links_removed,
                }
                await self._report(job, stage, Stage.CONVERTING, None, None)
                # LibreOffice only ever opens the cleaned copy (T-02-13).
                pdf = await self._timed("soffice", self._convert(clean, folder / "pdf", str(job.job_id)))

            await self._report(job, stage, Stage.RENDERING, 0, None)
            args = child.python_child("render", str(pdf), str(folder / PAGE_FILE), str(RENDER_DPI))
            run = self._run_child(args, profile="render", cwd=folder, read=(str(pdf),), write=(str(folder),))
            await self._timed("render", run)
            pages, width, height = await asyncio.to_thread(_read_meta, folder / META_FILE)
            if pages > limits.MAX_PAGES:
                # The one page cap (D-02-08); for DOCX and ODT the count exists
                # only now, in the PDF of LibreOffice.
                raise _Fail(Reason.TOO_MANY_PAGES)
            await self._report(job, stage, Stage.RENDERING, 1, pages)
        except _Abort:
            await asyncio.to_thread(_remove, folder)
            return
        except _Fail as failure:
            await self._fail(job, failure.reason)
            return
        except (child.ChildTimeout, child.ChildFailed, soffice.ConversionFailed, ValueError, OSError) as exc:
            self._note_jail(exc)
            # Exit code, signal and the cleaned stderr tail (child.diagnostic_tail) of a
            # failed child; the other exceptions carry none of them.
            LOGGER.info(
                "render step failed",
                extra={
                    "job_id": job.job_id,
                    "exc_type": type(exc).__name__,
                    "exit_code": getattr(exc, "exit_code", None),
                    "signal": getattr(exc, "signal", None),
                    "stderr_tail": getattr(exc, "stderr_tail", None) or None,
                    # ProfileTemplateMissing: missing, unreadable, unsafe_entry, malformed or conflict, never a path.
                    "reason": exc.reason if isinstance(exc, soffice.ProfileTemplateMissing) else None,
                },
            )
            await self._fail(job, Reason.RENDER_FAILED)
            return

        # Only the page image stays; the source and the converted PDF go now.
        await asyncio.to_thread(_remove_sources, folder)
        await self._db(lambda db: repo.upsert_job(db, job.job_id, task=job.task, stage=Stage.DONE, now=self._now()))
        await self._close(
            job, AckResult.REVIEW, pages_total=pages, etag_seen=fetched.etag, image=(width, height), **flags
        )

    async def _precheck(self, job: nc.Claim, folder: Path, expected: Literal["pdf", "docx", "odt"]) -> Verdict:
        """The pre-check child on the source, its answer checked again here (T-02-15)."""
        source = folder / SOURCE_STEM
        answer = folder / VERDICT_FILE
        args = child.python_child("precheck", str(source), expected, str(answer))
        await self._check_child(job, "precheck", args, folder, read=(str(source),))
        try:
            return await asyncio.to_thread(_read_verdict, answer, expected)
        except (ValueError, OSError) as exc:
            LOGGER.info(
                "check answer refused",
                extra={"job_id": job.job_id, "child": "precheck", "exc_type": type(exc).__name__},
            )
            raise _Fail(Reason.DAMAGED) from None

    async def _sanitize(
        self, job: nc.Claim, folder: Path, source: Path, fmt: Literal["pdf", "docx", "odt"]
    ) -> tuple[Path, Cleaned]:
        """The cleaner child: a cleaned copy of a DOCX or ODT beside the source, and its checked answer."""
        clean = folder / f"{CLEAN_STEM}.{fmt}"
        answer = folder / SANITIZE_FILE
        args = child.python_child("sanitize", str(source), fmt, str(clean), str(answer))
        await self._check_child(job, "sanitize", args, folder, read=(str(source),))
        try:
            cleaned = await asyncio.to_thread(_read_sanitize, answer, clean)
        except (ValueError, OSError) as exc:
            LOGGER.info(
                "check answer refused",
                extra={"job_id": job.job_id, "child": "sanitize", "exc_type": type(exc).__name__},
            )
            raise _Fail(Reason.DAMAGED) from None
        if cleaned.verdict != OK:
            raise _Fail(Reason(cleaned.verdict))
        return clean, cleaned

    async def _check_child(
        self, job: nc.Claim, kind: str, args: list[str], folder: Path, *, read: tuple[str, ...]
    ) -> None:
        """Run precheck or sanitize in the jail profile of its kind; a failure becomes its word."""
        try:
            await self._timed(kind, self._run_child(args, profile=kind, cwd=folder, read=read, write=(str(folder),)))
        except (child.ChildTimeout, child.ChildFailed) as exc:
            reason = _child_failure_reason(kind, exc)
            self._note_jail(exc)
            LOGGER.info(
                "check step failed",
                extra={
                    "job_id": job.job_id,
                    "child": kind,
                    "exc_type": type(exc).__name__,
                    "exit_code": getattr(exc, "exit_code", None),
                    "signal": getattr(exc, "signal", None),
                    "reason": reason.value,
                },
            )
            raise _Fail(reason) from None

    def _note_jail(self, exc: BaseException) -> None:
        """Exit 71: a jail layer was offered but not loadable; /status shows jail failed from now on."""
        if isinstance(exc, child.ChildFailed) and exc.exit_code == _EXIT_LAYER_FAILED:
            self._mark_jail_failed()

    # -- apply --------------------------------------------------------------------

    async def _apply(self, job: nc.Claim, stage: "_StageBox") -> None:
        folder = self._work_dir(job.job_id)
        output = folder / OUTPUT_FILE
        try:
            await asyncio.to_thread(_ensure_folder, folder)
            await self._report(job, stage, Stage.RENDERING, None, None)
            args = child.python_child("placeholder", str(output), str(job.job_id))
            run = self._run_child(args, profile="render", cwd=folder, write=(str(folder),))
            await self._timed("placeholder", run)
            digest, size = await asyncio.to_thread(_hash_file, output)
        except _Abort:
            await asyncio.to_thread(_remove, folder)
            return
        except (child.ChildTimeout, child.ChildFailed, OSError) as exc:
            self._note_jail(exc)
            LOGGER.info(
                "placeholder step failed",
                extra={
                    "job_id": job.job_id,
                    "exc_type": type(exc).__name__,
                    "exit_code": getattr(exc, "exit_code", None),
                    "signal": getattr(exc, "signal", None),
                },
            )
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


def _name_source(folder: Path, fmt: str) -> Path:
    """The source renamed to src.<format>, the format the pre-check confirmed; nothing is read."""
    typed = folder / f"{SOURCE_STEM}.{fmt}"
    (folder / SOURCE_STEM).replace(typed)
    return typed


def _answer_object(path: Path, keys: frozenset[str]) -> dict[str, Any]:
    """A child's answer file as an object with exactly these keys, or ValueError."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != keys:
        msg = "answer is not an object with the closed keys"
        raise ValueError(msg)
    return data


def _word(value: object) -> str:
    if not isinstance(value, str) or value not in VERDICTS:
        msg = "answer word outside the closed list"
        raise ValueError(msg)
    return value


def _flag(value: object) -> bool:
    if not isinstance(value, bool):
        msg = "answer flag is not a bool"
        raise ValueError(msg)
    return value


def _read_verdict(path: Path, expected: Literal["pdf", "docx", "odt"]) -> Verdict:
    """verdict.json of the pre-check, every field against its list and range (T-02-15).

    ok needs the format the job expects; a PDF has 1 to limits.MAX_PAGES pages,
    DOCX and ODT none yet, and only a PDF may be signed or owner protected. A
    refusal carries no format, no pages and no flag set. Anything else is a
    ValueError, which the runner turns into damaged.
    """
    data = _answer_object(path, _VERDICT_KEYS)
    word = _word(data["verdict"])
    signed = _flag(data["signed"])
    owner = _flag(data["ownerProtected"])
    pages = data["pages"]
    fmt = data["format"]
    if word != OK:
        if fmt is not None or pages is not None or signed or owner:
            msg = "a refusal carries no facts"
            raise ValueError(msg)
        return Verdict(verdict=word, format=None, pages=None, signed=False, owner_protected=False)
    if fmt != expected:
        msg = "format is not the expected one"
        raise ValueError(msg)
    if expected == "pdf":
        if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= limits.MAX_PAGES:
            msg = "pages out of range"
            raise ValueError(msg)
    elif pages is not None or signed or owner:
        msg = "an office document has no pages, signature or owner protection yet"
        raise ValueError(msg)
    return Verdict(verdict=word, format=expected, pages=pages, signed=signed, owner_protected=owner)


def _read_sanitize(path: Path, clean: Path) -> Cleaned:
    """sanitize.json of the cleaner, checked; ok also needs the cleaned copy to exist."""
    data = _answer_object(path, _SANITIZE_KEYS)
    word = _word(data["verdict"])
    macros = _flag(data["macrosRemoved"])
    links = data["externalLinksRemoved"]
    if isinstance(links, bool) or not isinstance(links, int) or not 0 <= links <= nc.MAX_LINKS_REMOVED:
        msg = "externalLinksRemoved out of range"
        raise ValueError(msg)
    if word == OK and not clean.is_file():
        msg = "the cleaned copy is missing"
        raise ValueError(msg)
    return Cleaned(verdict=word, macros_removed=macros, external_links_removed=links)


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
