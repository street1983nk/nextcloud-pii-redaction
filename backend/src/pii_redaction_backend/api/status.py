"""GET /status: version, readiness, the companion state and the last child.

No route in info.xml points here; ExAppService::status() calls it signed
(01-SKELETON.md "Signierte Container-Endpunkte"). The answer carries no name,
no path and no job number.

The companion state is asked again first when it is unknown or older than
companion.STALE_SECONDS (as in AVS): after the PHP app came back from being
disabled, the admin section and the next start see ok again without waiting
for the five minute round of companion.run_periodic.
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
    state = await companion.refresh_if_stale()
    return {
        "version": config.app_version(),
        "ready": ready,
        "companion": state.state,
        "busy": worker.busy if isinstance(worker, Runner) else False,
        "lastChild": None if last is None else {"kind": last.kind, "rssKb": last.rss_kb, "ms": last.ms},
    }
