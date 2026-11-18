"""Child entry point: the pre-check of one file, stages A, B and C, a closed answer in out.json.

Runs as python -I -m pii_redaction_backend.workers.precheck <src> <expected> <out.json>
inside run_child (empty environment, own process group, time limit) in the
jail of the "precheck" profile (SAFE-01, SAFE-02). <expected> is the format the
file claims to be (pdf, docx or odt, from its Nextcloud mime type).

Order: stage A by the bytes (intake.magic), then for a PDF stage C
(intake.pdfcheck), for a DOCX or ODT stage B (intake.zipcheck) and the XML
parts (intake.xmlcheck). out.json holds exactly five keys:
verdict (a word of intake.verdict.VERDICTS), format (the format found, null on
a rejection), pages (int for a PDF, null for DOCX and ODT, whose page count
comes only from the LibreOffice PDF), signed and ownerProtected (bools,
JOB-05, D-02-10). A signed PDF is verdict ok with signed true; the server asks
the user before it goes on (plan 02-19).

Fail-closed: an unexpected error of a parser is damaged, running out of
memory is too_large; neither says what happened. The child writes nothing to
stdout or stderr and logs nothing (T-02-20); the answer is written to a temp
file and moved into place, so the server never reads half an answer. Exit 2
only for wrong arguments or an answer that cannot be written; exit 0 means
out.json exists. The server checks the answer against the closed list again,
the child counts as one an attacker may have taken over (T-02-15, plan 02-19).
"""

import json
import os
import sys
from pathlib import Path
from typing import Final, Literal

from pii_redaction_backend.intake.verdict import OK, Rejected

FORMATS: Final = ("pdf", "docx", "odt")

Answer = dict[str, str | int | bool | None]


def _rejected(verdict: str) -> Answer:
    return {"verdict": verdict, "format": None, "pages": None, "signed": False, "ownerProtected": False}


def _check(source: Path, expected: Literal["pdf", "docx", "odt"]) -> Answer:
    from pii_redaction_backend.intake import magic, pdfcheck, xmlcheck, zipcheck

    found = magic.detect(source, expected)
    if found == "pdf":
        report = pdfcheck.check_pdf(source)
        return {
            "verdict": OK,
            "format": found,
            "pages": report.pages,
            "signed": report.signed,
            "ownerProtected": report.owner_protected,
        }
    xmlcheck.check_parts(source, zipcheck.check_zip(source).names)
    return {"verdict": OK, "format": found, "pages": None, "signed": False, "ownerProtected": False}


def judge(source: Path, expected: Literal["pdf", "docx", "odt"]) -> Answer:
    """The answer for one file; every failure becomes a word, never a message."""
    try:
        return _check(source, expected)
    except Rejected as rejected:
        return _rejected(rejected.verdict)
    except MemoryError:
        return _rejected("too_large")
    except Exception:  # fail-closed: whatever a parser raises, the file is refused as damaged
        return _rejected("damaged")


def write_answer(out: Path, answer: Answer) -> None:
    """out.json through a temp file beside it and os.replace; a failed write leaves no temp file."""
    temp = out.with_name(out.name + ".tmp")
    try:
        temp.write_text(json.dumps(answer, sort_keys=True), encoding="utf-8")
        os.replace(temp, out)
    except OSError:
        temp.unlink(missing_ok=True)
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in FORMATS:
        return 2
    expected: Literal["pdf", "docx", "odt"] = "pdf" if argv[1] == "pdf" else "docx" if argv[1] == "docx" else "odt"
    try:
        write_answer(Path(argv[2]), judge(Path(argv[0]), expected))
    except OSError:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
