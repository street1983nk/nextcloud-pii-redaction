"""Test-only work of each sandbox profile, for risk R2 of plan 02-16; never part of the product.

The soffice child may not call connect() since the owner decision of 17.11.
For the other profiles the question is open: does their work still run when
the child can reach no socket? test_container_soffice.py runs the work below
once in the product jail of the profile and once in the same jail with
deny_connect (jail_layers.py deny-connect) and compares.

    python -I profile_work.py module <child> <args...>   a product child (render, placeholder) as __main__
    python -I profile_work.py precheck <pdf> <docx>       the intake checks of the pre-check
    python -I profile_work.py sanitize <docx> <out>       the sanitizer on a DOCX
    python -I profile_work.py detect <models root> <work> [<dump every s>]
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

Sandbox run of 87f5744 (CI 44221141543): the cause was OMP_THREAD_LIMIT=1
from SAFE_ENV; without it arm64 extracted in about 230 ms. The product
environment of detect now carries OMP_NUM_THREADS=<n> from the parent
instead (child.child_env), and detect and torchbench hand the same count to
torch right after the import (hardware.apply_worker_threads), as the
detection child will.

    python -I profile_work.py torchbench <work>           torch facts and three timings

Sandbox run of c2ac178 (arm64): all four detect variants hung 120 s, the
unjailed one too, with cpuinfo=ok and /sys readable; amd64 extracted in
about 230 ms. torchbench writes <work>/torch-bench.txt, one BENCH line per
step: facts (torch version, the summary of torch.__config__.parallel_info(),
threads, mkldnn/ACL flags), a 512x512 float32 matmul x20, the tensor work of
gliner2 SpanMarkerV0.score_queries in the shapes of the detect text x20, and
the same with torch.set_flush_denormal(True). Each step runs in its own
thread with BENCH_STEP_S; a step that does not finish writes ms=timeout and
the next step still runs, so a hang still yields a line.

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
import threading
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
CPU_FILES: Final = (
    ("present", "/sys/devices/system/cpu/present"),
    ("possible", "/sys/devices/system/cpu/possible"),
    ("online", "/sys/devices/system/cpu/online"),
    ("cpuinfo", "/proc/cpuinfo"),
)
BENCH_FILE: Final = "torch-bench.txt"
BENCH_STEPS: Final = ("facts", "matmul", "score_queries", "score_queries_ftz")
BENCH_STEP_S: Final = 10.0
BENCH_REPEAT: Final = 20
MATMUL_SIZE: Final = 512
# gliner2 2.1.0 layers.py SpanMarkerV0.score_queries for the detect text:
# batch 1, two queries (person, location), mDeBERTa-v3-base hidden size 768,
# max_width 8 (configuration.py default), about 32 tokens. The hot frame of
# the arm64 hang was layers.py:487, torch.matmul(queries, final_linear.weight)
# with the weight of the 4H -> H layer, [768, 3072].
SQ_QUERIES: Final = 2
SQ_TOKENS: Final = 32
SQ_HIDDEN: Final = 768
SQ_WIDTH: Final = 8
# The lines of torch.__config__.parallel_info() worth a key (key : value).
PARALLEL_KEYS: Final = {
    "at::get_num_threads()": "aten_threads",
    "at::get_num_interop_threads()": "aten_interop",
    "omp_get_max_threads()": "omp_max_threads",
    "mkl_get_max_threads()": "mkl_max_threads",
    "std::thread::hardware_concurrency()": "hw_concurrency",
    "ATen parallel backend": "backend",
}


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


def apply_threads() -> None:
    """The thread count of the child environment to torch, as the detection child does it (product helper)."""
    import torch

    from pii_redaction_backend.resources import hardware

    hardware.apply_worker_threads(torch)


def detect(models: Path, work: Path, every_s: float = DUMP_EVERY_S) -> None:
    """Load both detectors from local folders, offline as the detection child will be, and find a name."""
    use_work_folder_as_temp(work)
    trace = Trace(work, every_s)
    try:
        trace.mark("start")
        _detect(models, trace)
        trace.mark("done")
    except BaseException as exc:
        trace.mark(f"raised:{type(exc).__name__}")
        raise
    finally:
        trace.close()


def _detect(models: Path, trace: Trace) -> None:
    from pii_redaction_backend import offline

    offline.configure()
    trace.mark("offline_configured")
    apply_threads()
    trace.mark("threads_set")
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    trace.mark("presidio_imported")
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


class BenchHung(Exception):
    """A bench step is still running in its thread: main writes the result line and leaves with os._exit."""


def parallel_summary(text: str) -> str:
    """torch.__config__.parallel_info() as key=value words (PARALLEL_KEYS, openmp, mkldnn); - for a missing key."""
    values: dict[str, str] = {}
    openmp = mkldnn = "-"
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("OpenMP "):
            openmp = _word(line.split("(")[0].removeprefix("OpenMP "))
        elif "MKL-DNN" in line or "oneDNN" in line:
            versions = [word for word in line.split() if word.startswith("v") and word[1:2].isdigit()]
            mkldnn = versions[0] if versions else "ja"
        key, sep, value = line.rpartition(":")
        if sep and key.strip() in PARALLEL_KEYS:
            values[PARALLEL_KEYS[key.strip()]] = _word(value)
    words = [f"{name}={values.get(name, '-')}" for name in PARALLEL_KEYS.values()]
    return " ".join([*words, f"openmp={openmp}", f"mkldnn_version={mkldnn}"])


def _flag(call: Callable[[], object] | None) -> str:
    if call is None:
        return "absent"
    try:
        return "ja" if call() else "nein"
    except Exception as exc:
        return f"error:{type(exc).__name__}"


def torch_facts() -> str:
    """The facts step: version, parallel_info summary, threads, mkldnn/ACL/MKL/OpenMP flags, CPU capability."""
    import torch

    backends = torch.backends
    capability = getattr(backends.cpu, "get_cpu_capability", None)
    parts = [
        f"torch={_word(torch.__version__)}",
        parallel_summary(torch.__config__.parallel_info()),
        f"num_threads={torch.get_num_threads()}",
        f"interop={torch.get_num_interop_threads()}",
        f"mkldnn={_flag(backends.mkldnn.is_available)}",
        f"acl={_flag(getattr(backends.mkldnn, 'is_acl_available', None))}",
        f"config_acl={'ja' if 'ACL' in torch.__config__.show() else 'nein'}",
        f"mkl={_flag(backends.mkl.is_available)}",
        f"omp_avail={_flag(backends.openmp.is_available)}",
        f"cpu_cap={_word(str(capability())) if capability is not None else 'absent'}",
        f"omp_thread_limit={_word(os.environ.get('OMP_THREAD_LIMIT', ''))}",
        f"omp_num_threads={_word(os.environ.get('OMP_NUM_THREADS', ''))}",
    ]
    return " ".join(parts)


def _ms(begun: float) -> str:
    return f"{(time.perf_counter() - begun) * 1000:.1f}"


def _matmul() -> str:
    import torch

    left = torch.randn(MATMUL_SIZE, MATMUL_SIZE)
    right = torch.randn(MATMUL_SIZE, MATMUL_SIZE)
    begun = time.perf_counter()
    for _ in range(BENCH_REPEAT):
        torch.matmul(left, right)
    return f"ms={_ms(begun)}"


def _score_queries() -> str:
    """The tensor work of gliner2 SpanMarkerV0.score_queries (layers.py 441 to 502), random weights, x BENCH_REPEAT."""
    import torch
    from torch.nn import functional

    hidden, wide = SQ_HIDDEN, 4 * SQ_HIDDEN
    h = torch.randn(1, SQ_TOKENS, hidden).relu()
    queries = torch.randn(1, SQ_QUERIES, hidden)
    first = torch.randn(wide, 2 * hidden) / hidden
    first_bias = torch.randn(wide)
    final = torch.randn(hidden, wide) / wide
    final_bias = torch.randn(hidden)
    first_ms = "-"
    begun = time.perf_counter()
    for index in range(BENCH_REPEAT):
        start_hidden = functional.linear(h, first[:, :hidden], None)
        end_hidden = functional.linear(h, first[:, hidden:], None)
        end_padded = functional.pad(end_hidden, (0, 0, 0, SQ_WIDTH - 1))
        windows = end_padded.unfold(1, SQ_WIDTH, 1).permute(0, 1, 3, 2)
        spans = (start_hidden.unsqueeze(2) + windows + first_bias).relu().reshape(1, SQ_TOKENS * SQ_WIDTH, -1)
        folded = torch.matmul(queries, final)  # layers.py:487
        bias = torch.matmul(queries, final_bias)
        torch.baddbmm(bias[:, None, :], spans, folded.transpose(1, 2))
        if index == 0:
            first_ms = _ms(begun)
    return f"ms={_ms(begun)} first_ms={first_ms}"


def _score_queries_ftz() -> str:
    import torch

    flushed = torch.set_flush_denormal(True)
    return f"{_score_queries()} ftz={'ja' if flushed else 'nein'}"


BENCH_CALLS: Final[dict[str, Callable[[], str]]] = {
    "facts": torch_facts,
    "matmul": _matmul,
    "score_queries": _score_queries,
    "score_queries_ftz": _score_queries_ftz,
}


def bench_step(step: str, budget_s: float) -> tuple[str, bool]:
    """The BENCH line of one step run in its own thread, and whether that thread still runs after budget_s."""
    box: list[str] = []

    def run() -> None:
        import torch

        try:
            with torch.inference_mode():
                box.append(BENCH_CALLS[step]())
        except Exception as exc:
            box.append(f"ms=fail:{type(exc).__name__}")

    thread = threading.Thread(target=run, name=f"bench-{step}", daemon=True)
    thread.start()
    thread.join(budget_s)
    if thread.is_alive():
        return f"BENCH step={step} ms=timeout", True
    return f"BENCH step={step} {box[0] if box else 'ms=fail:nothing'}", False


def torchbench(work: Path, budget_s: float = BENCH_STEP_S) -> None:
    """Every BENCH_STEPS step into <work>/BENCH_FILE; raises BenchHung when a step thread is left running."""
    use_work_folder_as_temp(work)
    hung = False
    with (work / BENCH_FILE).open("a", encoding="ascii", errors="replace") as handle:
        handle.write("BENCH step=start\n")
        handle.flush()
        import torch

        apply_threads()
        torch.manual_seed(0)
        for step in BENCH_STEPS:
            line, still_running = bench_step(step, budget_s)
            handle.write(f"{line}\n")
            handle.flush()
            hung = hung or still_running
    if hung:
        raise BenchHung


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
    elif len(argv) == 2 and argv[0] == "torchbench":
        torchbench(Path(argv[1]))
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
    except BenchHung:
        # A thread still spins in a torch call: no interpreter shutdown that could wait for it.
        print(result_line("ok", seen), flush=True)
        os._exit(0)
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
