"""The closed lists of the container are exactly those of 01-SKELETON.md."""

import pytest

from pii_redaction_backend.model import AckResult, Reason, Stage, Task


def test_stage_is_the_skeleton_list() -> None:
    assert [item.value for item in Stage] == ["waiting", "fetching", "converting", "rendering", "done"]


def test_task_is_the_skeleton_list() -> None:
    assert [item.value for item in Task] == ["analyze", "apply", "purge"]


def test_ack_result_is_the_skeleton_list() -> None:
    assert [item.value for item in AckResult] == ["review", "verified", "purged", "failed"]


def test_reason_is_the_skeleton_list() -> None:
    assert [item.value for item in Reason] == [
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
    ]


@pytest.mark.parametrize("enum", [Stage, Task, AckResult, Reason])
def test_a_word_outside_the_list_raises(enum: type[Stage | Task | AckResult | Reason]) -> None:
    with pytest.raises(ValueError, match="is not a valid"):
        enum("x")


def test_members_compare_as_their_words() -> None:
    assert Task.ANALYZE == "analyze"
    assert f"{Reason.RENDER_FAILED}" == "render_failed"
