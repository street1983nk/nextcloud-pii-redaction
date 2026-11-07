"""GET /status: version, readiness, the companion state and the last child.

No route in info.xml points here; ExAppService::status() calls it signed
(01-SKELETON.md "Signierte Container-Endpunkte"). The answer carries no name,
no path and no job number.
"""

from fastapi import APIRouter, Request

from pii_redaction_backend import companion, config
from pii_redaction_backend.runner.runner import Runner, last_child

router = APIRouter()


@router.get("/status")
async def status(request: Request) -> dict[str, object]:
    """``{version, ready, companion, busy, lastChild}`` with numbers and words only."""
    worker = getattr(request.app.state, "runner", None)
    ready = isinstance(worker, Runner)
    last = last_child()
    return {
        "version": config.app_version(),
        "ready": ready,
        "companion": companion.current().state,
        "busy": worker.busy if isinstance(worker, Runner) else False,
        "lastChild": None if last is None else {"kind": last.kind, "rssKb": last.rss_kb, "ms": last.ms},
    }
