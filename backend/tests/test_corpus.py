"""Container proof of success criterion 2 (plan 02-21): the whole corpus through the real jail children.

Runs only inside the test stage of the image (sandbox.yml, -m container). The
corpus of plan 02-07 is made on the runner and mounted at PII_CORPUS (the
image has no ci/). Every file goes the way the runner sends a source: copied
to <storage>/work/<job>/src, the precheck child in the jail of its profile,
its answer read with runner._read_verdict; a failed child gets its word from
runner._child_failure_reason, the one mapping of the product (no second
mapping here). Files with "sanitize" in the manifest also go through the
sanitize child (runner._read_sanitize), and the cleaned copy through precheck
again, which must say ok.

The harmless controls and the bombs run in the same pass: a pre-check that
refused everything would fail on the controls. After the corpus the server
still answers /heartbeat, PID 1 is the server and no zombie is left.

Lines in the job log:

    CORPUS-JAIL file=<name> precheck=<word> sanitize=<word|-> again=<word|-> ms=<longest child> ok=<ja|nein>
    CORPUS-JAIL-SUM files=<n> passed=<n> refused=<n> wrong=<n> max_ms=<n> total_s=<s> heartbeat=<ja|nein>
        pid1=<ja|nein> zombies=<n>                         (a gate: wrong=0, heartbeat, pid1, zombies=0)
"""

import asyncio
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

import httpx
import pytest

from pii_redaction_backend import config
from pii_redaction_backend.intake.verdict import OK
from pii_redaction_backend.runner import runner
from pii_redaction_backend.sandbox.profiles import PROFILES
from pii_redaction_backend.sandbox.reaper import become_subreaper
from pii_redaction_backend.workers import child
from tests.conftest import record_measurement
from tests.test_jail_container import settled_zombies

pytestmark = [pytest.mark.container, pytest.mark.linux]

Format = Literal["pdf", "docx", "odt"]
Corpus = tuple[Path, dict[str, dict[str, object]]]
# The type of pytest's record_property fixture.
RecordProperty = Callable[[str, object], None]

JOB_BASE = 990_400
# A child may take its profile wall clock plus this much, measured from outside.
SLACK_S = 5.0
CONTROLS = ("harmless.pdf", "harmless.docx", "harmless.odt")
# Fewer than these and the corpus ran almost empty (47 files run here, 34 of them bombs or broken files).
MIN_FILES = 40
MIN_BOMBS = 30
PASSING = frozenset({OK, "confirm"})
HARP_SOCKET = "/tmp/exapp.sock"  # noqa: S108 - the HaRP socket path, only asked over HTTP
ANSWER_REFUSED = "answer-refused"
NOT_RUN = "-"


def _client() -> httpx.Client:
    """The server as the smoke test reaches it: behind HaRP on its socket, otherwise on APP_PORT."""
    if os.environ.get("HP_SHARED_KEY"):
        path = os.environ.get("HP_EXAPP_SOCK", HARP_SOCKET)
        return httpx.Client(transport=httpx.HTTPTransport(uds=path), base_url="http://localhost", timeout=10)
    return httpx.Client(base_url=f"http://127.0.0.1:{os.environ['APP_PORT']}", timeout=10)


def _fresh(folder: Path) -> Path:
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def container_after() -> tuple[bool, bool, list[int]]:
    """After the corpus: does /heartbeat answer ok, is PID 1 still the server, which zombies are left."""
    with _client() as client:
        heartbeat = client.get("/heartbeat")
    beating = heartbeat.status_code == 200 and heartbeat.json() == {"status": "ok"}
    server = b"pii_redaction_backend.main" in Path("/proc/1/cmdline").read_bytes()
    return beating, server, settled_zombies()


async def run_precheck(source: Path, expected: Format, folder: Path) -> tuple[str, float]:
    """The precheck child on source as the runner starts it: its word and how long it took."""
    answer = folder / runner.VERDICT_FILE
    args = child.python_child("precheck", str(source), expected, str(answer))
    started = time.monotonic()
    try:
        await child.run_child(args, profile="precheck", cwd=folder, read=(str(source),), write=(str(folder),))
    except (child.ChildTimeout, child.ChildFailed) as exc:
        return runner._child_failure_reason("precheck", exc).value, time.monotonic() - started
    seconds = time.monotonic() - started
    try:
        verdict = runner._read_verdict(answer, expected)
    except (ValueError, OSError):
        # The runner would say damaged; a correct child never writes such an answer, so here it is a finding.
        return ANSWER_REFUSED, seconds
    # A signed PDF is ok and marked; the manifest calls that "confirm" (D-02-04).
    return ("confirm" if verdict.verdict == OK and verdict.signed else verdict.verdict), seconds


async def run_sanitize(source: Path, fmt: Format, folder: Path) -> tuple[str, float, Path]:
    """The sanitize child as the runner starts it on the typed source: word, duration, cleaned copy."""
    # The runner names the source by the format the pre-check confirmed (src -> src.<fmt>).
    typed = runner._name_source(source.parent, fmt)
    clean = folder / f"{runner.CLEAN_STEM}.{fmt}"
    answer = folder / runner.SANITIZE_FILE
    args = child.python_child("sanitize", str(typed), fmt, str(clean), str(answer))
    started = time.monotonic()
    try:
        await child.run_child(args, profile="sanitize", cwd=folder, read=(str(typed),), write=(str(folder),))
    except (child.ChildTimeout, child.ChildFailed) as exc:
        return runner._child_failure_reason("sanitize", exc).value, time.monotonic() - started, clean
    seconds = time.monotonic() - started
    try:
        cleaned = runner._read_sanitize(answer, clean)
    except (ValueError, OSError):
        return ANSWER_REFUSED, seconds, clean
    return cleaned.verdict, seconds, clean


async def test_the_corpus_is_refused_in_the_real_jail_and_the_container_lives(
    mounted_corpus: Corpus, capsys: pytest.CaptureFixture[str], record_property: RecordProperty
) -> None:
    # As the server (main.harden_process): orphans of a child come back here and reap_group collects them.
    assert become_subreaper()
    corpus, manifest = mounted_corpus
    lines: list[str] = []
    words: dict[str, str] = {}
    wrong: list[str] = []
    slow: list[str] = []
    refused = 0
    longest = 0.0
    started = time.monotonic()
    for index, (name, entry) in enumerate(sorted(manifest.items())):
        # unit_only files are judged by one stage only (zip_entries_10000 has empty parts).
        if entry["unit_only"]:
            continue
        expect = set(cast("list[str]", entry["expect"]))
        fmt = cast("Format", entry["expected_format"])
        folder = _fresh(config.work_dir(JOB_BASE + 2 * index))
        again_folder = config.work_dir(JOB_BASE + 2 * index + 1)
        sanitized, again = NOT_RUN, NOT_RUN
        try:
            source = Path(shutil.copyfile(corpus / name, folder / runner.SOURCE_STEM))
            word, took = await run_precheck(source, fmt, folder)
            durations = {"precheck": took}
            if entry["sanitize"] and word == OK:
                sanitized, took, clean = await run_sanitize(source, fmt, folder)
                durations["sanitize"] = took
                if sanitized == OK:
                    copy = Path(shutil.copyfile(clean, _fresh(again_folder) / runner.SOURCE_STEM))
                    again, took = await run_precheck(copy, fmt, again_folder)
                    durations["precheck-again"] = took
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(again_folder, ignore_errors=True)
        passed = word in expect and (not entry["sanitize"] or (sanitized == OK and again == OK))
        for kind, seconds in durations.items():
            longest = max(longest, seconds)
            profile = "sanitize" if kind == "sanitize" else "precheck"
            if seconds > PROFILES[profile].wall_s + SLACK_S:
                slow.append(f"{name}:{kind}")
        words[name] = word
        if word not in PASSING:
            refused += 1
        if not passed:
            wrong.append(name)
        ms = int(max(durations.values()) * 1000)
        lines.append(
            f"CORPUS-JAIL file={name} precheck={word} sanitize={sanitized} again={again} ms={ms} "
            f"ok={'ja' if passed else 'nein'}"
        )
    total = time.monotonic() - started

    beating, server, found = await asyncio.to_thread(container_after)
    lines.append(
        f"CORPUS-JAIL-SUM files={len(words)} passed={len(words) - len(wrong)} refused={refused} wrong={len(wrong)} "
        f"max_ms={int(longest * 1000)} total_s={total:.1f} heartbeat={'ja' if beating else 'nein'} "
        f"pid1={'ja' if server else 'nein'} zombies={len(found)}"
    )
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    record_measurement(
        "corpus_jail", {"words": words, "wrong": wrong, "slow": slow, "total_s": round(total, 1), "refused": refused}
    )
    record_property("corpus_total_s", round(total, 1))

    report = "\n".join(lines)
    assert len(words) >= MIN_FILES, "the corpus ran almost empty"
    # Positive controls: a pre-check that refused everything would stop here.
    for name in CONTROLS:
        assert words.get(name) == OK, (name, words.get(name))
    # The bombs ran in the same pass and were refused, every one of them.
    bombs = [name for name in words if not set(cast("list[str]", manifest[name]["expect"])) & PASSING]
    assert len(bombs) >= MIN_BOMBS, bombs
    assert refused == len(bombs), report
    assert wrong == [], report
    assert slow == [], slow
    assert beating, "the server no longer answers /heartbeat after the corpus"
    assert server, "PID 1 is no longer the server after the corpus"
    assert found == [], report
