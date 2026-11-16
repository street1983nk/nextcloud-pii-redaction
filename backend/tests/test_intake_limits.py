"""The fixed limits of the pre-check (D-02-07, D-02-08, D-02-13) and the closed verdict list."""

import pytest

from pii_redaction_backend import config
from pii_redaction_backend.intake import limits
from pii_redaction_backend.intake.verdict import OK, VERDICTS, Rejected

MIB = 1024 * 1024


def test_there_is_one_page_cap_of_300() -> None:
    assert limits.MAX_PAGES == 300


def test_the_source_limit_lives_in_one_place() -> None:
    assert config.MAX_SOURCE_BYTES is limits.MAX_SOURCE_BYTES
    assert limits.MAX_SOURCE_BYTES == 256 * MIB


def test_the_limits_match_the_research_table() -> None:
    assert limits.MAX_PDF_OBJECTS == 500_000
    assert limits.MAX_PAGE_SIDE_PT == 14_400
    assert limits.MAX_IMAGE_PIXELS == 100_000_000
    assert limits.MAX_RENDER_PIXELS == 50_000_000
    assert limits.ZIP_MAX_ENTRIES == 10_000
    assert limits.ZIP_MAX_CENTRAL_DIRECTORY_BYTES == 8 * MIB
    assert limits.ZIP_MAX_MEMBER_BYTES == 64 * MIB
    assert limits.ZIP_MAX_TOTAL_BYTES == 256 * MIB
    assert limits.ZIP_MAX_RATIO == 100
    assert limits.ZIP_MALICIOUS_RATIO == 1000
    assert limits.ZIP_RATIO_MIN_BYTES == MIB
    assert limits.ZIP_MAX_NAME_BYTES == 255
    assert limits.ZIP_MAX_DEPTH == 0
    assert limits.XML_MAX_PART_BYTES == limits.ZIP_MAX_MEMBER_BYTES


def test_the_verdicts_are_a_closed_list() -> None:
    assert frozenset(
        {
            "ok",
            "encrypted_pdf",
            "encrypted_document",
            "wrong_type",
            "damaged",
            "too_large",
            "too_many_pages",
            "unsafe_content",
            "unsupported_format",
        }
    ) == VERDICTS


def test_a_rejection_carries_its_word_and_nothing_else() -> None:
    error = Rejected("damaged")
    assert error.verdict == "damaged"
    assert str(error) == "damaged"


@pytest.mark.parametrize("word", ["ok", "file.pdf", "", "Damaged"])
def test_a_rejection_needs_a_rejection_word(word: str) -> None:
    with pytest.raises(ValueError, match="not a rejection verdict"):
        Rejected(word)
    assert OK == "ok"
