"""One file through the product path of an analyze task, with only the Nextcloud side replaced (plan 02-24).

The real Runner runs its real children: pre-check, cleaner and render in
their jails (child.run_child) and LibreOffice through soffice.convert in the
jail of the "soffice" profile, with the limits of sandbox/profiles.py. What is
replaced is what lies outside the container: the claim, the download (a copy
of the file), the progress reports and the ack, which are recorded. The
outcome is therefore the product's own answer: review with the page count,
or failed with a reason of the closed list, or confirm for a signed PDF.

Used by test_container_corpus.py; the pure parts are checked in
test_container_corpus_helpers.py on every machine.
"""

import asyncio
import hashlib
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from pii_redaction_backend import nc
from pii_redaction_backend.model import AckResult, Stage, Task
from pii_redaction_backend.runner import runner
from pii_redaction_backend.workers import child

ETAG: Final = '"corpus-etag"'
TOKEN: Final = "c" * 64
USER: Final = "corpus"
LEASE_S: Final = 3600
Format = Literal["pdf", "docx", "odt"]
FORMATS: Final[dict[str, Format]] = {"pdf": "pdf", "docx": "docx", "odt": "odt"}


def format_of(name: str) -> Format:
    """The format a file claims by its name, as Nextcloud would claim it by its mime type."""
    suffix = name.rsplit(".", 1)[-1].lower()
    if suffix not in FORMATS:
        msg = f"no product format: {suffix}"
        raise ValueError(msg)
    return FORMATS[suffix]


@dataclass(slots=True)
class Nextcloud:
    """The PHP app and the gateway as the runner sees them; one claim, every report recorded."""

    source: Path
    claims: list[nc.Claim] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    acks: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    jail_marks: int = 0

    async def claim(self, _client: object) -> nc.Claim | None:
        return self.claims.pop(0) if self.claims else None

    async def recheck(self) -> None:
        return None

    async def progress(
        self, _client: object, _job: nc.Claim, stage: Stage, _done: int | None, _total: int | None
    ) -> nc.Outcome:
        self.stages.append(stage.value)
        return nc.Outcome.OK

    async def ack(self, _client: object, _job: nc.Claim, result: AckResult, **fields: Any) -> nc.Outcome:
        self.acks.append((result.value, fields))
        return nc.Outcome.OK

    async def fetch(self, _client: object, _job: nc.Claim, target: Path, *, max_bytes: int) -> nc.FetchResult:
        return await asyncio.to_thread(self._copy, target, max_bytes)

    def _copy(self, target: Path, max_bytes: int) -> nc.FetchResult:
        size = self.source.stat().st_size
        if size > max_bytes:
            # What the gateway download does past the cap: not ok, nothing at the target.
            return nc.FetchResult(ok=False, stale=False, sha256=None, size=0, etag=None, http_status=200)
        shutil.copyfile(self.source, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return nc.FetchResult(ok=True, stale=False, sha256=digest, size=size, etag=ETAG, http_status=200)

    def mark_jail_failed(self) -> None:
        self.jail_marks += 1


@dataclass(frozen=True, slots=True)
class ProductRun:
    """The product's answer for one file."""

    result: str
    reason: str | None
    pages: int | None
    stages: tuple[str, ...]
    ms: int
    jail_marks: int


def answer(acks: list[tuple[str, dict[str, Any]]]) -> tuple[str, str | None, int | None]:
    """result, reason and pages of the one ack of a task; anything but exactly one ack is a broken run."""
    if len(acks) != 1:
        msg = f"expected one ack, got {len(acks)}"
        raise AssertionError(msg)
    result, fields = acks[0]
    reason = fields.get("reason")
    pages = fields.get("pages_total")
    return result, None if reason is None else str(reason), pages if isinstance(pages, int) else None


Convert = Callable[..., Awaitable[Path]]


async def run_product(
    source: Path, job_id: int, root: Path, convert: Convert, run_child: Callable[..., Awaitable[None]] = child.run_child
) -> ProductRun:
    """The analyze task of source as job job_id, its work folder and state below root.

    run_child is the real one in the container; only the tests of the harness itself replace it.
    """
    world = Nextcloud(source)
    world.claims.append(
        nc.Claim(
            job_id=job_id,
            task=Task.ANALYZE,
            token=TOKEN,
            file_id=job_id,
            user_id=USER,
            etag=ETAG,
            lease_seconds=LEASE_S,
            expected=format_of(source.name),
        )
    )
    worker = runner.Runner(
        client_factory=object,
        claim=world.claim,
        progress=world.progress,
        ack=world.ack,
        fetch_source=world.fetch,
        may_work=lambda: True,
        recheck_companion=world.recheck,
        admit=lambda _kind: True,
        run_child=run_child,
        convert=convert,
        mark_jail_failed=world.mark_jail_failed,
        state_db=lambda: root / "state.db",
        work_dir=lambda job: root / "work" / str(job),
    )
    started = time.monotonic()
    handled = await worker.run_once()
    ms = int((time.monotonic() - started) * 1000)
    if not handled:
        msg = "the runner claimed nothing"
        raise AssertionError(msg)
    result, reason, pages = answer(world.acks)
    return ProductRun(result, reason, pages, tuple(world.stages), ms, world.jail_marks)
