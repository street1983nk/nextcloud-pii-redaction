"""The container state: ids, hashes, sizes and closed words, never document text or a file name."""

import sqlite3
from pathlib import Path

import pytest

from pii_redaction_backend.store import repo

FORBIDDEN_PARTS = ("name", "path", "text", "content", "snippet", "title")


def _columns(connection: sqlite3.Connection) -> dict[str, list[str]]:
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")] for table in tables}


def test_the_schema_has_no_column_for_text_or_names(tmp_path: Path) -> None:
    connection = repo.connect(tmp_path / "state.db")
    columns = _columns(connection)
    connection.close()

    assert set(columns) == {"meta", "jobs"}
    assert [f"{t}.{c}" for t, cs in columns.items() for c in cs if any(p in c for p in FORBIDDEN_PARTS)] == []


def test_the_database_runs_in_wal_mode(tmp_path: Path) -> None:
    connection = repo.connect(tmp_path / "state.db")
    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    connection.close()
    assert mode == "wal"


def test_a_job_round_trips_and_is_deleted(tmp_path: Path) -> None:
    connection = repo.connect(tmp_path / "state.db")
    repo.upsert_job(connection, 7, task="analyze", stage="fetching", now=100)
    repo.upsert_job(connection, 7, task="analyze", stage="rendering", now=101, pages_total=3)

    job = repo.get_job(connection, 7)
    assert job is not None
    assert (job["stage"], job["pages_total"], job["created_at"], job["updated_at"]) == ("rendering", 3, 100, 101)

    repo.delete_job(connection, 7)
    assert repo.get_job(connection, 7) is None
    connection.close()


def test_words_outside_the_closed_lists_are_refused(tmp_path: Path) -> None:
    connection = repo.connect(tmp_path / "state.db")
    with pytest.raises(ValueError, match="task"):
        repo.upsert_job(connection, 1, task="Bericht.pdf", stage="waiting", now=1)
    with pytest.raises(ValueError, match="stage"):
        repo.upsert_job(connection, 1, task="analyze", stage="anything", now=1)
    connection.close()
