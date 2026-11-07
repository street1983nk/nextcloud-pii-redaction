"""GET /jobs/{job_id}/output: the finished copy, only once it is verified.

The state row has to carry output_sha256, which the runner writes only after
the output exists and was hashed (state verified, T-01-10-06). The PHP app
compares hash and size with the ack before it stores the copy.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pii_redaction_backend import config
from pii_redaction_backend.runner.runner import OUTPUT_FILE
from pii_redaction_backend.store import repo

router = APIRouter()


def _verified_output(job_id: int) -> Path | None:
    database = config.state_db_path()
    if not database.is_file():
        return None
    connection = repo.connect(database)
    try:
        row = repo.get_job(connection, job_id)
    finally:
        connection.close()
    if row is None or row["output_sha256"] is None:
        return None
    path = config.work_dir(job_id) / OUTPUT_FILE
    return path if path.is_file() else None


@router.get("/jobs/{job_id}/output")
async def output(job_id: int) -> FileResponse:
    """The output PDF of a verified job, or 404."""
    if job_id < 1:
        raise HTTPException(status_code=404)
    path = await asyncio.to_thread(_verified_output, job_id)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "private, no-store"})
