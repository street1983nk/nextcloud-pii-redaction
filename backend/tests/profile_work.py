"""Test-only work of each sandbox profile, for risk R2 of plan 02-16; never part of the product.

The soffice child may not call connect() since the owner decision of 17.11.
For the other profiles the question is open: does their work still run when
the child can reach no socket? test_container_soffice.py runs the work below
once in the product jail of the profile and once in the same jail with
deny_connect (jail_layers.py deny-connect) and compares.

    python -I profile_work.py module <child> <args...>   a product child (render, placeholder) as __main__
    python -I profile_work.py precheck <pdf> <docx>       the intake checks of the pre-check
    python -I profile_work.py sanitize <docx> <out>       the sanitizer on a DOCX
    python -I profile_work.py detect <models root> <work> [<dump every s> [<threads>]]
                                                          Presidio with de_core_news_lg and GLiNER2, offline

detect writes <work>/detect-trace.txt (sandbox run of cfb428a: on arm64 it
ran into the 900 s limit with nothing on stdout or stderr): a MARK line after
each step (seconds since start, torch loaded or not, VmRSS), the Python stack
of every thread each <dump every s> seconds (faulthandler, also on SIGUSR1
and on a fatal signal). The test reads it when the run times out.

Sandbox run of 335a80f (arm64): detect stopped after gliner_loaded, all
stacks in gliner2 score_queries, one thread busy for 300 s, stderr "Error in
cpuinfo: failed to parse the list of present processors"; amd64 extracted in
0.4 s. So detect also writes a FACTS line (what torch and the kernel say about
the CPUs, and whether /sys/devices/system/cpu/{present,possible,online} and
/proc/cpuinfo are readable) and an EXTRACT line (ms of extract_entities).
<threads> is "-" (unchanged, the product) or "cpu": OMP_NUM_THREADS and
torch.set_num_threads fixed to os.cpu_count(), a measurement variant only.

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

import errno
import faulthandler
import os
import runpy
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final, TextIO

CHILD_MODULES: Final = frozenset({"render", "placeholder"})
# The audit events of a network step: what offline.NETWORK_EVENTS forbids, plus every other socket event.
NETWORK_PREFIXES: Final = ("socket.", "urllib.")
DETECT_TEXT: Final = "Erika Mustermann wohnt in der Hafenstraße 12 in Hamburg und schreibt an Jonas Weber."
DETECT_NAME: Final = "Mustermann"
SPACY_FOLDER: Final = ("spacy", "de_core_news_lg-3.8.0")
TRACE_FILE: Final = "detect-trace.txt"
DUMP_EVERY_S: Final = 60.0
THREADS_UNCHANGED: Final = "-"
THREADS_CPU: Final = "cpu"
CPU_FILES: Final = (
    ("present", "/sys/devices/system/cpu/present"),
    ("possible", "/sys/devices/system/cpu/possible"),
    ("online", "/sys/devices/system/cpu/online"),
    ("cpuinfo", "/proc/cpuinfo"),
)


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


def _rss() -> str:
    """VmRSS of this process from /proc/self/status, or - where it cannot be read (Windows, the jail)."""
    try:
        text = Path("/proc/self/status").read_text(encoding="ascii", errors="replace")
    except OSError:
        return "-"
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            return "".join(line.split()[1:2]) + "kB"
    return "-"


class Trace:
    """MARK lines and periodic stacks of all threads in <work>/detect-trace.txt, test only.

    faulthandler writes to the file descriptor itself, so a dump also comes
    out while the main thread hangs in C code (as long as the GIL is free or
    the hang is in Python). close() cancels everything; a killed child leaves
    the file as it was.
    """

    def __init__(self, work: Path, every_s: float) -> None:
        self.path = work / TRACE_FILE
        self._started = time.monotonic()
        self._file: TextIO = self.path.open("a", encoding="ascii", errors="replace", buffering=1)
        faulthandler.enable(file=self._file, all_threads=True)
        faulthandler.dump_traceback_later(every_s, repeat=True, file=self._file, exit=False)
        if sys.platform != "win32":
            faulthandler.register(signal.SIGUSR1, file=self._file, all_threads=True)

    def mark(self, step: str) -> None:
        elapsed = time.monotonic() - self._started
        torch = "ja" if "torch" in sys.modules else "nein"
        self._file.write(f"MARK t={elapsed:.1f}s step={step} torch={torch} rss={_rss()}\n")
        self._file.flush()

    def line(self, text: str) -> None:
        """One extra line (FACTS, EXTRACT) in the trace file."""
        self._file.write(f"{text}\n")
        self._file.flush()

    def close(self) -> None:
        faulthandler.cancel_dump_traceback_later()
        if sys.platform != "win32":
            faulthandler.unregister(signal.SIGUSR1)
        faulthandler.disable()
        self._file.close()


def _word(text: str) -> str:
    """One blank-free word for a key=value line; - when empty."""
    return "_".join(text.split()) or "-"


def _readable(path: str) -> str:
    """The first line of a small kernel file as one word (cpuinfo: ok), or the errno name when it cannot be read."""
    try:
        with Path(path).open(encoding="ascii", errors="replace") as handle:
            first = handle.readline()
    except OSError as exc:
        return errno.errorcode.get(exc.errno or 0, "OSError")
    return "ok" if path == "/proc/cpuinfo" else _word(first)


def _affinity() -> str:
    getter = getattr(os, "sched_getaffinity", None)
    if getter is None:
        return "-"
    try:
        cpus = sorted(getter(0))
    except OSError:
        return "error"
    return f"{len(cpus)}:{cpus[0]}-{cpus[-1]}" if cpus else "0"


def cpu_facts() -> str:
    """What torch, os and the kernel files say about the CPUs, one FACTS line; never raises."""
    parts: list[str] = []
    torch = sys.modules.get("torch")
    for key, call in (
        ("torch_threads", "get_num_threads"),
        ("interop", "get_num_interop_threads"),
    ):
        value = "-"
        if torch is not None:
            try:
                value = str(getattr(torch, call)())
            except Exception as exc:
                value = f"error:{type(exc).__name__}"
        parts.append(f"{key}={value}")
    capability = "-"
    if torch is not None:
        try:
            getter = getattr(torch.backends.cpu, "get_cpu_capability", None)
            capability = _word(str(getter())) if getter is not None else "absent"
        except Exception as exc:
            capability = f"error:{type(exc).__name__}"
    parts += [f"cpu_cap={capability}", f"cpu_count={os.cpu_count()}", f"affinity={_affinity()}"]
    parts += [f"{name}={_readable(path)}" for name, path in CPU_FILES]
    for name in ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT"):
        parts.append(f"{name.lower()}={_word(os.environ.get(name, ''))}")
    return "FACTS " + " ".join(parts)


def thread_count(spec: str) -> int | None:
    """None for the product setting, the CPU count for "cpu"; anything else is a usage error."""
    if spec == THREADS_UNCHANGED:
        return None
    if spec == THREADS_CPU:
        return os.cpu_count() or 1
    raise WorkFailed("usage")


def detect(models: Path, work: Path, every_s: float = DUMP_EVERY_S, threads: str = THREADS_UNCHANGED) -> None:
    """Load both detectors from local folders, offline as the detection child will be, and find a name."""
    count = thread_count(threads)
    use_work_folder_as_temp(work)
    if count is not None:
        # Before torch is imported: OpenMP reads it when it loads.
        os.environ["OMP_NUM_THREADS"] = str(count)
    trace = Trace(work, every_s)
    try:
        trace.mark("start")
        _detect(models, trace, count)
        trace.mark("done")
    except BaseException as exc:
        trace.mark(f"raised:{type(exc).__name__}")
        raise
    finally:
        trace.close()


def _detect(models: Path, trace: Trace, threads: int | None = None) -> None:
    from pii_redaction_backend import offline

    offline.configure()
    trace.mark("offline_configured")
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    trace.mark("presidio_imported")
    if threads is not None:
        import torch

        torch.set_num_threads(threads)
    trace.line(cpu_facts())
    engine = SpacyNlpEngine(models=[{"lang_code": "de", "model_name": str(models.joinpath(*SPACY_FOLDER))}])
    engine.load()
    trace.mark("spacy_loaded")
    analyzer = AnalyzerEngine(nlp_engine=engine, supported_languages=["de"])
    found = analyzer.analyze(DETECT_TEXT, language="de")
    trace.mark("presidio_analyzed")
    if not any(DETECT_NAME in DETECT_TEXT[item.start : item.end] for item in found):
        raise WorkFailed("presidio_missed")
    from gliner2 import GLiNER2

    trace.mark("gliner_imported")
    model = GLiNER2.from_pretrained(str(_gliner_folder(models)))
    trace.mark("gliner_loaded")
    begun = time.monotonic()
    entities = model.extract_entities(DETECT_TEXT, ["person", "location"])
    trace.line(f"EXTRACT ms={int((time.monotonic() - begun) * 1000)}")
    trace.mark("gliner_extracted")
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
    elif len(argv) == 4 and argv[0] == "detect":
        detect(Path(argv[1]), Path(argv[2]), _seconds(argv[3]))
    elif len(argv) == 5 and argv[0] == "detect":
        detect(Path(argv[1]), Path(argv[2]), _seconds(argv[3]), argv[4])
    else:
        raise WorkFailed("usage")


def _seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise WorkFailed("usage") from None
    if not value > 0:
        raise WorkFailed("usage")
    return value


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
