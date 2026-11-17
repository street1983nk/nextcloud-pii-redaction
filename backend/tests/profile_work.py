"""Test-only work of each sandbox profile, for risk R2 of plan 02-16; never part of the product.

The soffice child may not call connect() since the owner decision of 17.11.
For the other profiles the question is open: does their work still run when
the child can reach no socket? test_container_soffice.py runs the work below
once in the product jail of the profile and once in the same jail with
deny_connect (jail_layers.py deny-connect) and compares.

    python -I profile_work.py module <child> <args...>   a product child (render, placeholder) as __main__
    python -I profile_work.py precheck <pdf> <docx>       the intake checks of the pre-check
    python -I profile_work.py sanitize <docx> <out>       the sanitizer on a DOCX
    python -I profile_work.py detect <models root> <work> Presidio with de_core_news_lg and GLiNER2, offline

Exactly one line goes to stdout:

    result=<ok|fail:<word>> events=<comma separated audit events|->

<word> is an exit code or an exception class, never a path or a message.
events are the Python level network steps the work tried (an audit hook that
records and never blocks, so the seccomp answer is what the work sees). It
sees Python only: C code that connects (libcurl, a resolver) shows up as a
failure in the deny-connect run, not here. No precheck or sanitize child
exists yet (plan 02-05, 02-19); this runs the intake functions they will run.
The OCR profile runs Tesseract directly and needs no helper here.
"""

import os
import runpy
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

CHILD_MODULES: Final = frozenset({"render", "placeholder"})
# The audit events of a network step: what offline.NETWORK_EVENTS forbids, plus every other socket event.
NETWORK_PREFIXES: Final = ("socket.", "urllib.")
DETECT_TEXT: Final = "Erika Mustermann wohnt in der Hafenstraße 12 in Hamburg und schreibt an Jonas Weber."
DETECT_NAME: Final = "Mustermann"
SPACY_FOLDER: Final = ("spacy", "de_core_news_lg-3.8.0")


class WorkFailed(Exception):
    """The work ran but did not give what it should; the word goes to the result line."""

    def __init__(self, word: str) -> None:
        super().__init__(word)
        self.word = word


def _recorder(seen: set[str]) -> Callable[[str, tuple[object, ...]], None]:
    def hook(event: str, _args: tuple[object, ...]) -> None:
        if event.startswith(NETWORK_PREFIXES):
            seen.add(event)

    return hook


def run_module(name: str, args: list[str]) -> None:
    if name not in CHILD_MODULES:
        raise WorkFailed("unknown_child")
    dotted = f"pii_redaction_backend.workers.{name}"
    sys.argv = [dotted, *args]
    try:
        runpy.run_module(dotted, run_name="__main__", alter_sys=True)
    except SystemExit as stop:
        if stop.code not in (0, None):
            raise WorkFailed(f"exit{stop.code}") from None
        return
    raise WorkFailed("no_exit")


def precheck(pdf: Path, docx: Path) -> None:
    from pii_redaction_backend.intake import magic, pdfcheck, xmlcheck, zipcheck

    if magic.detect(pdf, "pdf") != "pdf" or magic.detect(docx, "docx") != "docx":
        raise WorkFailed("wrong_type")
    if pdfcheck.check_pdf(pdf).pages < 1:
        raise WorkFailed("no_pages")
    xmlcheck.check_parts(docx, zipcheck.check_zip(docx).names)


def sanitize(docx: Path, out: Path) -> None:
    from pii_redaction_backend.intake import sanitize as cleaner

    cleaner.sanitize(docx, out, "docx")
    if not out.is_file() or out.stat().st_size == 0:
        raise WorkFailed("no_output")


def _gliner_folder(models: Path) -> Path:
    folders = sorted(path for path in (models / "gliner2").iterdir() if path.is_dir())
    if len(folders) != 1:
        raise WorkFailed("gliner_folder")
    return folders[0]


def use_work_folder_as_temp(work: Path) -> None:
    """tempfile and torch's compile cache go to the work folder of the run, the only folder the jail lets it write.

    Sandbox run of df2d2e5: detect failed with FileNotFoundError in the
    product jail and with deny_connect alike. Importing presidio_analyzer
    pulls in transformers, which imports torch._dynamo; its module
    torch/_dynamo/package.py calls cache_dir() at import time, which takes
    TORCHINDUCTOR_CACHE_DIR or else tempfile.gettempdir() and creates the
    folder. The child has HOME=/tmp and no TMPDIR, the jail grants no write
    right on /tmp, /var/tmp or the working folder, so gettempdir() finds no
    usable folder and raises FileNotFoundError. Found locally with the stack
    of the gettempdir() call; the models were there (/models in sandbox.yml).
    """
    os.environ["TMPDIR"] = str(work)
    os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(work / "torchinductor")
    tempfile.tempdir = str(work)


def detect(models: Path, work: Path) -> None:
    """Load both detectors from local folders, offline as the detection child will be, and find a name."""
    use_work_folder_as_temp(work)
    from pii_redaction_backend import offline

    offline.configure()
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    engine = SpacyNlpEngine(models=[{"lang_code": "de", "model_name": str(models.joinpath(*SPACY_FOLDER))}])
    engine.load()
    analyzer = AnalyzerEngine(nlp_engine=engine, supported_languages=["de"])
    found = analyzer.analyze(DETECT_TEXT, language="de")
    if not any(DETECT_NAME in DETECT_TEXT[item.start : item.end] for item in found):
        raise WorkFailed("presidio_missed")
    from gliner2 import GLiNER2

    model = GLiNER2.from_pretrained(str(_gliner_folder(models)))
    entities = model.extract_entities(DETECT_TEXT, ["person", "location"])
    if DETECT_NAME not in str(entities):
        raise WorkFailed("gliner_missed")


def work(argv: list[str]) -> None:
    if len(argv) >= 2 and argv[0] == "module":
        run_module(argv[1], argv[2:])
    elif len(argv) == 3 and argv[0] == "precheck":
        precheck(Path(argv[1]), Path(argv[2]))
    elif len(argv) == 3 and argv[0] == "sanitize":
        sanitize(Path(argv[1]), Path(argv[2]))
    elif len(argv) == 3 and argv[0] == "detect":
        detect(Path(argv[1]), Path(argv[2]))
    else:
        raise WorkFailed("usage")


def result_line(word: str, events: set[str]) -> str:
    return f"result={word} events={','.join(sorted(events)) or '-'}"


def main(argv: list[str]) -> int:
    seen: set[str] = set()
    sys.addaudithook(_recorder(seen))
    try:
        work(argv)
    except WorkFailed as failed:
        print(result_line(f"fail:{failed.word}", seen), flush=True)
        return 1
    except Exception as exc:
        print(result_line(f"fail:{type(exc).__name__}", seen), flush=True)
        return 1
    print(result_line("ok", seen), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
