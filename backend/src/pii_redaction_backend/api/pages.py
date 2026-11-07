"""GET /jobs/{job_id}/pages/{n}.png: page 1 of a job as PNG, nothing else.

The path is built from the whole number job id and the fixed name page-1.png;
no part of the request becomes a file name (T-01-10-02). Phase 1 renders only
page 1, so every other n is 404. The PHP app asks only after its recheck of
the user and the etag and passes the bytes on with no-store.
"""

import asyncio
from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pii_redaction_backend import config
from pii_redaction_backend.runner.runner import PAGE_FILE

router = APIRouter()

NO_STORE: Final = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
ONLY_PAGE: Final = 1


def _page(job_id: int) -> Path | None:
    path = config.work_dir(job_id) / PAGE_FILE
    return path if path.is_file() else None


@router.get("/jobs/{job_id}/pages/{n}.png")
async def page(job_id: int, n: int) -> FileResponse:
    """The PNG of page n, or 404 for any other page, an unknown job or a missing image."""
    if job_id < 1 or n != ONLY_PAGE:
        raise HTTPException(status_code=404)
    path = await asyncio.to_thread(_page, job_id)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers=NO_STORE)
