"""The closed list of pre-check verdicts and the exception that carries one.

Each word becomes a Reason of the job (plans 02-05, 02-19) and a text on the
file card (02-TEXTS.md). A verdict is a word and nothing else: never a name, a
path, a size or a message from a parser (T-02-33).
"""

from typing import Final

OK: Final = "ok"

VERDICTS: Final = frozenset(
    {
        OK,
        "encrypted_pdf",
        "encrypted_document",
        "wrong_type",
        "damaged",
        "too_large",
        "too_many_pages",
        "unsafe_content",
        "unsupported_format",
    }
)


class Rejected(Exception):
    """The file is refused; ``verdict`` is a word of VERDICTS other than ok."""

    def __init__(self, verdict: str) -> None:
        if verdict not in VERDICTS or verdict == OK:
            msg = f"not a rejection verdict: {verdict!r}"
            raise ValueError(msg)
        super().__init__(verdict)
        self.verdict = verdict
