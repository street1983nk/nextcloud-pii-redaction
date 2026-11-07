-- The state of the container: ids, hashes, sizes, counts and words of the
-- closed lists. There is no column for document text, a file name or a path
-- (success criterion 5 of phase 1); backend/tests/test_store_schema.py holds
-- the column names to that.

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    val TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id INTEGER PRIMARY KEY,
    task TEXT NOT NULL,
    stage TEXT NOT NULL,
    pages_total INTEGER,
    src_sha256 TEXT,
    src_bytes INTEGER,
    output_sha256 TEXT,
    output_bytes INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO meta (key, val) VALUES ('schema_version', '1');
