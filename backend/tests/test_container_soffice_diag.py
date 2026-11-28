"""Why 1800107_pdf.odt needs 4.4 GB and how long 1800107_pdf.docx needs: the soffice diagnosis (quick 261128-qaa).

Owner 28.11.2026: before the soffice address space cap of plan 02-24 is set,
its causes are measured. Sandbox run 46167327129 (commit 625eec7):
1800107_pdf.odt (144 images, 112 pages) reached VmHWM 4.41 GB in the product
jail, 1800107_pdf.docx (144 images) hit the 120 s wall of the product.

Q1, the memory: does the ODT need it for the decoded pixels of its images?
ci/soffice_diag.py wrote a copy whose PNG, JPEG and GIF members are 1x1 images
of the same format and name, every other member byte-identical, and printed
the decoded bytes of the images (SOFFICE-DIAG-IMAGES). Run 1 is the original
(positive control), run 2 the tiny copy (causal control), both through the
product path with the product wall.

Q2, the time: the jail sets RLIMIT_CPU to the wall of the profile plus 5 s
(125 s for soffice) in its own process, so no test can raise it. Run 3 is the
DOCX through the product path with only the soffice wall raised to 900 s (the
timeout_s parameter of soffice.convert, here in test code only): it shows what
stops soffice after 120 s. Run 4 is its tiny copy, the same way. Run 5 is the
exact soffice command with a fresh seeded and hardened job profile, without the
jail (no Landlock, seccomp or rlimits) in this container, which itself has no
network, with a wall of 900 s: it shows the real duration and CPU seconds. Run
5 reads the derived file as is, the product reads its sanitized copy.

The soffice runs happen on amd64 only (job budget: arm64 is about three times
slower and its job is already near the limit); the inventory runs on both.
sandbox/profiles.py and workers/soffice.py are unchanged. CPU seconds are the
delta of RUSAGE_CHILDREN around the soffice call; VmPeak, VmHWM, samples and
the address space limit come from the Sampler of test_container_corpus.py.
Nothing here goes to measurements.json; the log gets names and numbers only.

Lines in the job log:

    SOFFICE-DIAG-RUN doc=<name> variant=<original|tiny> mode=<product|product_wall900|unjailed_wall900>
        result=<word|-> reason=<word|-> soffice=<end> soffice_ms=<n> cpu_s=<n.n> vmpeak_kb= vmhwm_kb=
        samples= as_limit= wall_s=<120|900> pages=<n|->
    SOFFICE-DIAG-TAIL doc= mode= tail=<600 chars>
    JAIL-ZOMBIES after=diag n=<n>

A failing or timed out soffice is reported, never asserted; what fails the
test is a broken measurement: a missing file, zero samples where soffice ran,
not exactly one ack, a leftover profile or socket, a zombie.
"""

import asyncio
import os
import platform
import shutil
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pytest

from pii_redaction_backend.sandbox.reaper import become_subreaper, reap_group
from pii_redaction_backend.workers import child, soffice
from tests import product_path
from tests.test_container_corpus import DASH, Sampler, WatchedConvert, leftovers, load_real_corpus
from tests.test_jail_container import settled_zombies

pytestmark = [pytest.mark.container, pytest.mark.linux]

REAL_DIAG_ENV: Final = "PII_REAL_DIAG"
MANIFEST: Final = "manifest.json"
DIAG_WALL_S: Final = 900.0
JOB_BASE: Final = 990_700
AMD64: Final = frozenset({"x86_64", "amd64"})
ODT: Final = "1800107_pdf.odt"
DOCX: Final = "1800107_pdf.docx"
TINY_ODT: Final = "1800107_pdf_tiny.odt"
TINY_DOCX: Final = "1800107_pdf_tiny.docx"
TAIL_CHARS: Final = 600


def children_cpu_s() -> float:
    """User plus system CPU seconds of every child this process has collected so far."""
    if sys.platform == "win32":
        return 0.0
    import resource

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def _kill_group(pgid: int) -> None:
    if sys.platform == "win32":
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _word(value: object) -> str:
    return DASH if value is None else str(value).replace(" ", "_")


@dataclass(slots=True)
class TimedConvert:
    """The convert of the runner, with soffice time and CPU seconds; wall_s None keeps the product wall."""

    wall_s: float | None = None
    watched: WatchedConvert = field(default_factory=WatchedConvert)
    ms: int | None = None
    cpu_s: float | None = None

    async def __call__(self, src: Path, outdir: Path, job_id: str, *args: Any) -> Path:
        cpu_before, started = children_cpu_s(), time.monotonic()
        try:
            if self.wall_s is None:
                return await self.watched(src, outdir, job_id, *args)
            return await self.watched(src, outdir, job_id, self.wall_s)
        finally:
            self.ms = int((time.monotonic() - started) * 1000)
            self.cpu_s = children_cpu_s() - cpu_before


def _remove_own_sockets() -> None:
    uid = os.getuid() if sys.platform != "win32" else -1
    for entry in Path(soffice.PROFILE_ROOT).glob(soffice.IPC_SOCKET_GLOB):
        try:
            if soffice.is_own_ipc_socket(entry.name, entry.lstat(), uid):
                entry.unlink()
        except OSError:
            continue


def _make_folder(folder: Path) -> None:
    folder.mkdir(parents=True)


def _pdf_count(folder: Path) -> int:
    return len(list(folder.glob("*.pdf")))


@dataclass(slots=True)
class Unjailed:
    end: str | None = None
    ms: int | None = None
    cpu_s: float | None = None


async def unjailed_convert(src: Path, outdir: Path, job_id: str) -> Unjailed:
    """soffice.command with a fresh seeded and hardened profile, without the jail, killed as a group at DIAG_WALL_S."""
    _make_folder(outdir)
    profile, env = soffice.prepare_profile(job_id)
    _remove_own_sockets()
    measured = Unjailed()
    process: asyncio.subprocess.Process | None = None
    cpu_before, started = children_cpu_s(), time.monotonic()
    try:
        soffice.seed_profile(profile)
        soffice.harden_profile(profile)
        process = await asyncio.create_subprocess_exec(
            *soffice.command(src, outdir, job_id),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=outdir,
            env=child.child_env(env, profile="soffice"),
            start_new_session=True,
        )
        try:
            code = await asyncio.wait_for(process.wait(), DIAG_WALL_S)
        except TimeoutError:
            _kill_group(process.pid)
            await process.wait()
            measured.end = "timeout"
        else:
            pdfs = _pdf_count(outdir)
            if code != 0:
                measured.end = f"exit={code}"
            else:
                measured.end = "pdf" if pdfs == 1 else "no_pdf"
    finally:
        if process is not None:
            reap_group(process.pid)
        measured.ms = int((time.monotonic() - started) * 1000)
        measured.cpu_s = children_cpu_s() - cpu_before
        shutil.rmtree(profile, ignore_errors=True)
        _remove_own_sockets()
    return measured


def run_line(name: str, variant: str, mode: str, entry: dict[str, Any]) -> str:
    cpu = DASH if entry["cpu_s"] is None else f"{entry['cpu_s']:.1f}"
    return (
        f"SOFFICE-DIAG-RUN doc={name} variant={variant} mode={mode} result={_word(entry['result'])} "
        f"reason={_word(entry['reason'])} soffice={_word(entry['soffice'])} soffice_ms={_word(entry['ms'])} "
        f"cpu_s={cpu} vmpeak_kb={entry['vmpeak_kb']} vmhwm_kb={entry['vmhwm_kb']} samples={entry['samples']} "
        f"as_limit={entry['as_limit']} wall_s={int(entry['wall_s'])} pages={_word(entry['pages'])}"
    )


def _sampled(sampler: Sampler) -> dict[str, Any]:
    return {
        "vmpeak_kb": sampler.vmpeak_kb,
        "vmhwm_kb": sampler.vmhwm_kb,
        "samples": sampler.samples,
        "as_limit": ",".join(sorted(sampler.as_limits)) or DASH,
    }


def _files() -> dict[str, Path]:
    """The derived originals and their tiny copies; fails loudly when one is missing."""
    corpus = load_real_corpus(os.environ)
    diag = os.environ.get(REAL_DIAG_ENV, "")
    if not diag or not (Path(diag) / MANIFEST).is_file():
        pytest.fail(f"{REAL_DIAG_ENV} names no folder with {MANIFEST} (sandbox.yml makes and mounts it)")
    files = {
        ODT: corpus.derived / ODT,
        DOCX: corpus.derived / DOCX,
        TINY_ODT: Path(diag) / TINY_ODT,
        TINY_DOCX: Path(diag) / TINY_DOCX,
    }
    for name, path in files.items():
        if not path.is_file():
            pytest.fail(f"{name} is missing for the soffice diagnosis")
    return files


async def test_soffice_diagnosis_of_the_1800107_conversions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if platform.machine().lower() not in AMD64:
        pytest.skip("soffice diagnosis on amd64 only: job budget, quick 261128-qaa")
    assert become_subreaper()
    files = _files()
    # Product path: (doc, variant, mode, wall of soffice or None for the product wall).
    product_runs = (
        (ODT, "original", "product", None),
        (TINY_ODT, "tiny", "product", None),
        (DOCX, "original", "product_wall900", DIAG_WALL_S),
        (TINY_DOCX, "tiny", "product_wall900", DIAG_WALL_S),
    )
    measured: list[tuple[str, str, str, dict[str, Any]]] = []
    lines: list[str] = []
    left: dict[str, list[str]] = {}
    jail_marks = 0
    for index, (name, variant, mode, wall_s) in enumerate(product_runs):
        job_id = JOB_BASE + index
        timed = TimedConvert(wall_s)
        with Sampler() as sampler:
            run = await product_path.run_product(files[name], job_id, tmp_path / f"run-{index}", timed)
        watched = timed.watched
        entry: dict[str, Any] = {
            "result": run.result,
            "reason": run.reason,
            "soffice": watched.end,
            "ms": timed.ms,
            "cpu_s": timed.cpu_s,
            "wall_s": soffice.DEFAULT_TIMEOUT_S if wall_s is None else wall_s,
            "pages": run.pages if run.pages is not None else watched.pages,
            "jailed": True,
            **_sampled(sampler),
        }
        measured.append((name, variant, mode, entry))
        lines.append(run_line(name, variant, mode, entry))
        if watched.tail:
            tail = watched.tail.replace(chr(10), " | ")[:TAIL_CHARS]
            lines.append(f"SOFFICE-DIAG-TAIL doc={name} mode={mode} tail={tail}")
        jail_marks += run.jail_marks
        if found := leftovers(job_id):
            left[f"{name} {mode}"] = found

    # Run 5: the same soffice without the jail, on a byte-identical copy of the derived DOCX.
    job_id = JOB_BASE + len(product_runs)
    work = tmp_path / "unjailed"
    work.mkdir()
    source = work / DOCX
    shutil.copyfile(files[DOCX], source)
    with Sampler() as sampler:
        unjailed = await unjailed_convert(source, work / "out", str(job_id))
    entry = {
        "result": None,
        "reason": None,
        "soffice": unjailed.end,
        "ms": unjailed.ms,
        "cpu_s": unjailed.cpu_s,
        "wall_s": DIAG_WALL_S,
        "pages": None,
        "jailed": False,
        **_sampled(sampler),
    }
    measured.append((DOCX, "original", "unjailed_wall900", entry))
    lines.append(run_line(DOCX, "original", "unjailed_wall900", entry))
    if found := leftovers(job_id):
        left[f"{DOCX} unjailed_wall900"] = found

    zombies = settled_zombies()
    lines.append(f"JAIL-ZOMBIES after=diag n={len(zombies)}")
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    report = "\n".join(lines)

    # Only the measurement is asserted, never what soffice did.
    assert len(measured) == 5, report
    for name, _variant, mode, entry in measured:
        if entry["soffice"] is not None:
            assert entry["samples"] > 0, (name, mode, report)
            assert entry["vmpeak_kb"] > 0, (name, mode, report)
            if entry["jailed"]:
                assert entry["as_limit"] == "unlimited", (name, mode, report)
    assert jail_marks == 0, report
    assert left == {}, report
    assert zombies == [], report
