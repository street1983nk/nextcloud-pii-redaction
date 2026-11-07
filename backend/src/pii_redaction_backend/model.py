"""The closed lists the container shares with the PHP app (01-SKELETON.md).

The PHP side holds the same words as string backed enums in php/lib/Model/.
Nothing outside these lists is sent to Nextcloud or written to state.db, and
an answer of the PHP app with a word outside them is discarded.
"""

from enum import StrEnum


class Stage(StrEnum):
    """Where a running job stands, reported with every progress call."""

    WAITING = "waiting"
    FETCHING = "fetching"
    CONVERTING = "converting"
    RENDERING = "rendering"
    DONE = "done"


class Reason(StrEnum):
    """Why a job failed or went stale."""

    ENCRYPTED_PDF = "encrypted_pdf"
    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_MANY_PAGES = "too_many_pages"
    OUT_OF_MEMORY = "out_of_memory"
    REPEATEDLY_STUCK = "repeatedly_stuck"
    LEAK_DETECTED = "leak_detected"
    CHECK_ERROR = "check_error"
    ORIGINAL_CHANGED = "original_changed"
    ORIGINAL_DELETED = "original_deleted"
    TARGET_NOT_WRITABLE = "target_not_writable"
    BACKEND_STATE_LOST = "backend_state_lost"
    DOWNLOAD_BLOCKED = "download_blocked"
    NOT_READABLE = "not_readable"
    RENDER_FAILED = "render_failed"
    BACKEND_UNAVAILABLE = "backend_unavailable"


class Task(StrEnum):
    """What a claim asks the container to do."""

    ANALYZE = "analyze"
    APPLY = "apply"
    PURGE = "purge"


class AckResult(StrEnum):
    """How the container closes a claimed task."""

    REVIEW = "review"
    VERIFIED = "verified"
    PURGED = "purged"
    FAILED = "failed"
