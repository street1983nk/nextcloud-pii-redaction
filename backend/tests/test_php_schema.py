"""The data model of the PHP app, read from its sources (no PHP on this machine).

phpunit checks the enums in CI (``php/tests/Unit/ModelTest.php``). This module
decides locally what can be decided by reading the files:

1. Every enum under ``php/lib/Model`` carries exactly the words of the closed
   lists in 01-SKELETON.md, in that order.
2. The migration creates exactly the three tables with exactly the columns of
   01-SKELETON.md, and no column name contains a part that could carry clear
   text (``name``, ``path``, ``mime``, ``text``, ``value``, ``snippet``,
   ``title``, ``comment``, ``content``): success criterion 5 of phase 1.
3. Every enum value fits the length of the column it is stored in.

Each rule has a mutated sample that has to make it fire.
"""

import re

import pytest

from tests.conftest import REPO_ROOT

MODEL = REPO_ROOT / "php" / "lib" / "Model"
MIGRATION = REPO_ROOT / "php" / "lib" / "Migration" / "Version000100Date20261107000000.php"

CLOSED_LISTS = {
    "Status": [
        "queued",
        "analyzing",
        "review",
        "submitted",
        "approved",
        "applying",
        "verified",
        "published",
        "failed",
        "stale",
        "cancelled",
        "expired",
        "confirm",
    ],
    "Reason": [
        "encrypted_pdf",
        "unsupported_format",
        "too_many_pages",
        "out_of_memory",
        "repeatedly_stuck",
        "leak_detected",
        "check_error",
        "original_changed",
        "original_deleted",
        "target_not_writable",
        "backend_state_lost",
        "download_blocked",
        "not_readable",
        "render_failed",
        "backend_unavailable",
        "e2e_encrypted",
        "encrypted_document",
        "wrong_type",
        "damaged",
        "too_large",
        "unsafe_content",
        "signature_declined",
    ],
    "Stage": ["waiting", "fetching", "checking", "converting", "rendering", "done"],
    "Task": ["analyze", "apply", "purge"],
    "Mode": ["redact", "pseudonymize"],
    "Subject": ["review_ready", "job_failed", "job_stale", "copy_created"],
    "Lang": ["de", "en", "fr"],
}

TABLES = {
    "pii_jobs": [
        "id",
        "file_id",
        "initiator_uid",
        "file_etag",
        "mode",
        "lang",
        "status",
        "reason",
        "task",
        "stage",
        "pages_done",
        "pages_total",
        "claim_token",
        "lease_until",
        "attempts",
        "revision",
        "revision_hash",
        "output_sha256",
        "output_size",
        "output_file_id",
        "image_width",
        "image_height",
        "created_at",
        "updated_at",
        "expires_at",
    ],
    "pii_job_events": ["id", "job_id", "uid", "action", "at"],
    "pii_slot": ["id", "job_id", "claim_token", "lease_until"],
}

# Column a list is stored in: (table, column).
STORED_IN = {
    "Status": [("pii_jobs", "status"), ("pii_job_events", "action")],
    "Reason": [("pii_jobs", "reason")],
    "Stage": [("pii_jobs", "stage")],
    "Task": [("pii_jobs", "task")],
    "Mode": [("pii_jobs", "mode")],
    "Subject": [("pii_job_events", "action")],
    "Lang": [("pii_jobs", "lang")],
}

FORBIDDEN_PARTS = ("name", "path", "mime", "text", "value", "snippet", "title", "comment", "content")

CASE = re.compile(r"^\s*case\s+\w+\s*=\s*'([^']*)';", re.MULTILINE)
TABLE = re.compile(r"createTable\('([^']+)'\)")
COLUMN = re.compile(r"addColumn\('([^']+)',\s*Types::(\w+)(?:,\s*\[([^\]]*)\])?\)")
LENGTH = re.compile(r"'length'\s*=>\s*(\d+)")


def enum_values(source: str) -> list[str]:
    return CASE.findall(source)


def schema(source: str) -> dict[str, dict[str, tuple[str, int | None]]]:
    """Table to column to (type, length), in the order of the migration."""
    tables: dict[str, dict[str, tuple[str, int | None]]] = {}
    current: dict[str, tuple[str, int | None]] | None = None
    for line in source.splitlines():
        table = TABLE.search(line)
        if table:
            current = tables.setdefault(table.group(1), {})
            continue
        column = COLUMN.search(line)
        if column and current is not None:
            length = LENGTH.search(column.group(3) or "")
            current[column.group(1)] = (column.group(2), int(length.group(1)) if length else None)
    return tables


def forbidden_columns(tables: dict[str, dict[str, tuple[str, int | None]]]) -> list[str]:
    return [
        f"{table}.{column}"
        for table, columns in tables.items()
        for column in columns
        if any(part in column for part in FORBIDDEN_PARTS)
    ]


@pytest.mark.parametrize("name", sorted(CLOSED_LISTS))
def test_every_enum_carries_the_closed_list(name: str) -> None:
    source = (MODEL / f"{name}.php").read_text(encoding="utf-8")
    assert f"enum {name}: string" in source
    assert enum_values(source) == CLOSED_LISTS[name]


def test_the_migration_creates_exactly_the_skeleton_tables() -> None:
    tables = schema(MIGRATION.read_text(encoding="utf-8"))
    assert {table: list(columns) for table, columns in tables.items()} == TABLES


def test_no_column_could_carry_clear_text() -> None:
    assert forbidden_columns(schema(MIGRATION.read_text(encoding="utf-8"))) == []


def test_no_boolean_column() -> None:
    tables = schema(MIGRATION.read_text(encoding="utf-8"))
    assert all(kind != "BOOLEAN" for columns in tables.values() for kind, _ in columns.values())


@pytest.mark.parametrize("name", sorted(STORED_IN))
def test_every_value_fits_its_column(name: str) -> None:
    tables = schema(MIGRATION.read_text(encoding="utf-8"))
    values = enum_values((MODEL / f"{name}.php").read_text(encoding="utf-8"))
    for table, column in STORED_IN[name]:
        kind, length = tables[table][column]
        assert kind == "STRING"
        assert length is not None
        assert max(len(value) for value in values) <= length, f"{name} in {table}.{column}"


def test_the_rules_fire_on_mutated_samples() -> None:
    mutated = MIGRATION.read_text(encoding="utf-8").replace("'file_etag', Types::STRING", "'file_name', Types::STRING")
    assert forbidden_columns(schema(mutated)) == ["pii_jobs.file_name"]

    shortened = MIGRATION.read_text(encoding="utf-8").replace(
        "addColumn('reason', Types::STRING, ['notnull' => false, 'length' => 32])",
        "addColumn('reason', Types::STRING, ['notnull' => false, 'length' => 16])",
    )
    assert schema(shortened)["pii_jobs"]["reason"] == ("STRING", 16)
    assert max(len(value) for value in CLOSED_LISTS["Reason"]) > 16

    extra = (
        (MODEL / "Task.php")
        .read_text(encoding="utf-8")
        .replace("case Purge = 'purge';", "case Purge = 'purge';\n\tcase Extra = 'extra';")
    )
    assert enum_values(extra) != CLOSED_LISTS["Task"]


# -- job event actions (plan 02-05) ------------------------------------------------------

JOB_EVENT_MAPPER = REPO_ROOT / "php" / "lib" / "Db" / "JobEventMapper.php"
ACTION_CONSTANT = re.compile(r"const (ACTION_\w+) = '([^']*)';")
ACTION_WORD = re.compile(r"[a-z_]{1,32}")


def action_problems(source: str) -> list[str]:
    """Every ACTION_ constant is a word of at most 32 characters from [a-z_] (the action column)."""
    return [
        f"{name} = {value!r}" for name, value in ACTION_CONSTANT.findall(source) if not ACTION_WORD.fullmatch(value)
    ]


def test_every_job_event_action_is_a_short_word() -> None:
    source = JOB_EVENT_MAPPER.read_text(encoding="utf-8")
    actions = dict(ACTION_CONSTANT.findall(source))
    assert actions == {
        "ACTION_PLACEHOLDER_REQUESTED": "placeholder_requested",
        "ACTION_SIGNATURE_NOTICE": "signature_notice",
        "ACTION_SIGNATURE_CONFIRMED": "signature_confirmed",
        "ACTION_MACROS_REMOVED": "macros_removed",
        "ACTION_EXTERNAL_LINKS_REMOVED": "external_links_removed",
        "ACTION_OWNER_PROTECTION_DROPPED": "owner_protection_dropped",
    }
    assert action_problems(source) == []
    for name in actions:
        assert f"self::{name}," in source  # listed in ACTIONS, so isAllowedAction takes it


def test_the_action_rule_fires_on_a_long_or_odd_word() -> None:
    long_word = "a" * 33
    assert action_problems(f"const ACTION_X = '{long_word}';") == [f"ACTION_X = '{long_word}'"]
    assert action_problems("const ACTION_Y = 'Has Space';") == ["ACTION_Y = 'Has Space'"]
    assert action_problems("const ACTION_Z = '" + "a" * 32 + "';") == []
