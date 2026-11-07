"""The SQLite state of the container ($APP_PERSISTENT_STORAGE/state.db).

One connection per caller, WAL and foreign keys on every connection. Task and
stage are words of the closed lists of model.py; anything else is refused
before it reaches the database.
"""

import sqlite3
from importlib import resources
from pathlib import Path
from typing import Final

from pii_redaction_backend.model import Stage, Task

TASKS: Final = frozenset(item.value for item in Task)
STAGES: Final = frozenset(item.value for item in Stage)


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create) the state database with the pragmas this app relies on."""
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    schema = resources.files("pii_redaction_backend.store").joinpath("schema.sql").read_text(encoding="utf-8")
    connection.executescript(schema)
    return connection


def upsert_job(
    connection: sqlite3.Connection,
    job_id: int,
    *,
    task: Task | str,
    stage: Stage | str,
    now: int,
    pages_total: int | None = None,
) -> None:
    """Insert a job or move it to a new stage; created_at stays from the first write."""
    if task not in TASKS:
        msg = "task outside the closed list"
        raise ValueError(msg)
    if stage not in STAGES:
        msg = "stage outside the closed list"
        raise ValueError(msg)
    connection.execute(
        "INSERT INTO jobs (job_id, task, stage, pages_total, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(job_id) DO UPDATE SET task = excluded.task, stage = excluded.stage, "
        "pages_total = COALESCE(excluded.pages_total, jobs.pages_total), updated_at = excluded.updated_at",
        (job_id, task, stage, pages_total, now, now),
    )


def get_job(connection: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return row if isinstance(row, sqlite3.Row) else None


def delete_job(connection: sqlite3.Connection, job_id: int) -> None:
    connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))


def set_source(connection: sqlite3.Connection, job_id: int, *, sha256: str, size: int, now: int) -> None:
    """Remember hash and size of the fetched source (never its name)."""
    connection.execute(
        "UPDATE jobs SET src_sha256 = ?, src_bytes = ?, updated_at = ? WHERE job_id = ?",
        (sha256, size, now, job_id),
    )


def set_output(connection: sqlite3.Connection, job_id: int, *, sha256: str, size: int, now: int) -> None:
    """Remember hash and size of the finished output; /jobs/{id}/output serves only then."""
    connection.execute(
        "UPDATE jobs SET output_sha256 = ?, output_bytes = ?, updated_at = ? WHERE job_id = ?",
        (sha256, size, now, job_id),
    )
