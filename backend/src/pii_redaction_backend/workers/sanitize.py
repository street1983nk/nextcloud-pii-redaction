"""Child entry point: the cleaned copy of a DOCX or ODT before LibreOffice, a closed answer in out.json.

Runs as python -I -m pii_redaction_backend.workers.sanitize <src> <fmt> <dst> <out.json>
inside run_child (empty environment, own process group, time limit) in the
jail of the "sanitize" profile (SAFE-01, SAFE-03). <fmt> is docx or odt, the
format the pre-check found. The work is intake.sanitize (plan 02-13): no
external relations, no macros, no loading fields; the copy is checked again by
zipcheck and xmlcheck before it counts.

out.json holds exactly three keys: verdict (a word of intake.verdict.VERDICTS),
macrosRemoved (bool) and externalLinksRemoved (int), for the file card and the
protocol (D-02-12). On any failure there is no copy at dst and the answer is a
word only: a rejection keeps its word, running out of memory is too_large,
anything unexpected is damaged. Nothing goes to stdout or stderr, nothing is
logged (T-02-20). Exit 2 only for wrong arguments or an answer that cannot be
written (then the copy goes as well); exit 0 means out.json exists.
"""

import sys
from pathlib import Path
from typing import Final, Literal

from pii_redaction_backend.intake.verdict import OK, Rejected
from pii_redaction_backend.workers.precheck import Answer, write_answer

FORMATS: Final = ("docx", "odt")


def _failed(verdict: str) -> Answer:
    return {"verdict": verdict, "macrosRemoved": False, "externalLinksRemoved": 0}


def clean(source: Path, fmt: Literal["docx", "odt"], target: Path) -> Answer:
    """Write the cleaned copy and return the answer; on a failure target does not exist."""
    try:
        from pii_redaction_backend.intake import sanitize as cleaner

        report = cleaner.sanitize(source, target, fmt)
    except Rejected as rejected:
        verdict = rejected.verdict
    except MemoryError:
        verdict = "too_large"
    except Exception:  # fail-closed: whatever the cleaner raises, the file is refused as damaged
        verdict = "damaged"
    else:
        return {
            "verdict": OK,
            "macrosRemoved": report.macros_removed,
            "externalLinksRemoved": report.external_links_removed,
        }
    target.unlink(missing_ok=True)
    return _failed(verdict)


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in FORMATS:
        return 2
    fmt: Literal["docx", "odt"] = "docx" if argv[1] == "docx" else "odt"
    target = Path(argv[2])
    try:
        write_answer(Path(argv[3]), clean(Path(argv[0]), fmt, target))
    except OSError:
        target.unlink(missing_ok=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
