"""ci/soffice_gate.py, the product conversion docker.yml runs on the pushed image (plan 02-16, risk R3).

The conversion itself needs LibreOffice and runs only in docker.yml; the
DOCX it writes, the line it prints and the pass rule are decided here.
"""

import zipfile
from pathlib import Path
from types import ModuleType

from tests.conftest import ci_module

GOOD = {"pdf": "ja", "marker": "ja", "rest": 0, "ms": 900, "reason": "ok"}


def gate() -> ModuleType:
    return ci_module("soffice_gate")


def test_the_docx_holds_the_marker(tmp_path: Path) -> None:
    module = gate()
    path = module.write_docx(tmp_path / "gate.docx")
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        assert module.MARKER in archive.read("word/document.xml").decode()


def test_the_gate_line_and_its_pass_rule() -> None:
    module = gate()
    assert module.gate_line(GOOD) == "SOFFICE-GATE pdf=ja marker=ja rest=0 ms=900 reason=ok"
    assert module.passed(GOOD)


def test_negative_each_failure_fails_the_gate() -> None:
    module = gate()
    assert not module.passed({**GOOD, "pdf": "nein", "reason": "exit1"})
    assert not module.passed({**GOOD, "marker": "nein"})
    assert not module.passed({**GOOD, "rest": 1})
