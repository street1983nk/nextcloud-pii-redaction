"""The placeholder copy: one page, three languages, nothing from the original (UI-SPEC area 4)."""

from pathlib import Path

import pymupdf

from pii_redaction_backend.workers import placeholder

NBSP = chr(0x00A0)
EXPECTED_LINES = (
    "Platzhalter aus PII Redaction",
    "Nicht geschwärzt: Diese Datei enthält nichts aus dem Original.",
    "Placeholder from PII Redaction",
    "Not redacted: this file contains nothing from the original.",
    "Fichier provisoire de PII Redaction",
    "Non caviardé : ce fichier ne contient rien de l'original.",
    "Auftrag 7",
    "Job 7",
    "Tâche 7",
)


def _text(path: Path) -> tuple[int, str, dict[str, str]]:
    document = pymupdf.open(path)
    pages = document.page_count
    text = "".join(str(page.get_text()) for page in document).replace(NBSP, " ")
    metadata = {key: value or "" for key, value in (document.metadata or {}).items()}
    document.close()
    return pages, " ".join(text.split()), metadata


def test_the_placeholder_is_one_page_with_all_three_languages(tmp_path: Path) -> None:
    out = tmp_path / "placeholder.pdf"

    assert placeholder.main([str(out), "7"]) == 0

    pages, text, metadata = _text(out)
    assert pages == 1
    for line in EXPECTED_LINES:
        assert line in text, line
    assert metadata["title"] == "PII Redaction placeholder"
    assert metadata["author"] == ""


def test_the_french_sentence_carries_the_narrow_space_in_the_source() -> None:
    assert "Non caviardé" + NBSP + ": ce fichier" in placeholder.SENTENCES["fr"]


def test_the_placeholder_takes_no_source_file() -> None:
    # The child has no argument for a source document; it cannot read one.
    assert placeholder.main(["only-one-argument"]) == 2


def test_a_job_id_that_is_not_digits_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "placeholder.pdf"
    assert placeholder.main([str(out), "7; rm"]) == 2
    assert not out.exists()
