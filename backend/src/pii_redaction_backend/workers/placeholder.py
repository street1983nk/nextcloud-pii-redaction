"""Child entry point: the one page placeholder PDF of phase 1 (UI-SPEC area 4).

Runs as python -I -m pii_redaction_backend.workers.placeholder <out_pdf> <job_id>.
It takes no source document at all, so nothing of the original can end up in
it: three blocks (German, English, French), each a 20 pt bold title and a
12 pt sentence, and one line with the job number. Metadata: title only.
"""

import sys
from pathlib import Path
from typing import Final

NBSP: Final = chr(0x00A0)
TITLES: Final = {
    "de": "Platzhalter aus PII Redaction",
    "en": "Placeholder from PII Redaction",
    "fr": "Fichier provisoire de PII Redaction",
}
SENTENCES: Final = {
    "de": "Nicht geschwärzt: Diese Datei enthält nichts aus dem Original.",
    "en": "Not redacted: this file contains nothing from the original.",
    "fr": f"Non caviardé{NBSP}: ce fichier ne contient rien de l'original.",
}
JOB_LINE: Final = "Auftrag {n} · Job {n} · Tâche {n}"
MARGIN: Final = 72
TITLE_SIZE: Final = 20
SENTENCE_SIZE: Final = 12


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit() or not argv[1].isascii():
        return 2
    out, job_id = Path(argv[0]), argv[1]
    try:
        import pymupdf

        document = pymupdf.open()
        page = document.new_page(width=pymupdf.paper_rect("a4").width, height=pymupdf.paper_rect("a4").height)
        y = MARGIN + TITLE_SIZE
        for language in ("de", "en", "fr"):
            page.insert_text((MARGIN, y), TITLES[language], fontname="hebo", fontsize=TITLE_SIZE)
            y += SENTENCE_SIZE * 2
            page.insert_text((MARGIN, y), SENTENCES[language], fontname="helv", fontsize=SENTENCE_SIZE)
            y += TITLE_SIZE * 2.5
        page.insert_text((MARGIN, y), JOB_LINE.format(n=job_id), fontname="helv", fontsize=SENTENCE_SIZE)
        document.set_metadata({"title": "PII Redaction placeholder", "author": "", "creator": "", "producer": ""})
        document.save(out, garbage=4, deflate=True)
        document.close()
    except Exception:
        out.unlink(missing_ok=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
