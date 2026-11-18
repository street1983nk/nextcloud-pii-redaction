"""Container proof of RES-02 (plan 02-22): Presidio, tldextract and GLiNER2 make no hidden network call.

Runs only inside the test stage of the image (sandbox.yml, -m container,
--network none) with the models of ci/fetch_models.py mounted read only at
PII_MODELS (D-02-09). The probe tests/probes/offline_stack.py calls
offline.configure() and counts every network audit event; in the raise run it
also calls install_network_tripwire(), so every Python network step fails.

    (1) the probe as a plain child of the test, no jail
    (2) the probe in the jail of profile detect, /models its only extra read path
    (2b) as (2) with the raising tripwire: exit 0
    (3) config.json and encoder_config/config.json of GLiNER2 carry no auto_map
    (4) after configure the tldextract of the image has no suffix list URL
    (5) the positive control: the probe without configure and with an empty
        tldextract cache counts at least one network event

(1), (2) and (2b) must find the e-mail address and the person with 0 network
events. Missing models fail the run loudly, a skip would be a false green.

Lines in the job log:

    OFFLINE-STACK run=<unjailed|jailed|jailed-raise|control> exit=<n> email=<bool> person=<bool> net_events=<n>
        events=<names> error=<word> ms=<n>
"""

import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import pytest

from pii_redaction_backend import offline
from pii_redaction_backend.workers import child
from tests.conftest import record_measurement
from tests.test_lo_network import run_unjailed

pytestmark = [pytest.mark.container, pytest.mark.linux]

PROBE: Final = Path(__file__).with_name("probes") / "offline_stack.py"
MODELS_ENV: Final = "PII_MODELS"
GLINER_FOLDER: Final = ("gliner2", "1cb4166094dc58fa8d836429f060d6c95f62b495")
CONFIG_FILES: Final = ("config.json", "encoder_config/config.json")
REMOTE_CODE_KEY: Final = "auto_map"
# Model load and two extractions: about 20 s on amd64 (plan 02-16), arm64 slower.
PROBE_TIMEOUT_S: Final = 300.0
CONTROL_TIMEOUT_S: Final = 120.0


def models_root(env: Mapping[str, str]) -> Path:
    """The model folder sandbox.yml mounts; fails loudly when it is missing (never skips)."""
    root = Path(env.get(MODELS_ENV, ""))
    if not env.get(MODELS_ENV) or not root.is_absolute() or not root.joinpath(*GLINER_FOLDER).is_dir():
        pytest.fail(f"{MODELS_ENV} names no model folder with GLiNER2 (sandbox.yml mounts /models)")
    return root


def has_key(value: object, key: str) -> bool:
    """Whether key stands anywhere in a JSON value, nested objects and lists included."""
    if isinstance(value, dict):
        return key in value or any(has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(has_key(item, key) for item in value)
    return False


def stack_line(run: str, code: int, answer: Mapping[str, object], ms: int) -> str:
    events = answer.get("event_names") or []
    names = ",".join(str(name) for name in events) if isinstance(events, list) else "-"
    return (
        f"OFFLINE-STACK run={run} exit={code} email={answer.get('email')} person={answer.get('person')} "
        f"net_events={answer.get('net_events')} events={names or '-'} error={answer.get('error')} ms={ms}"
    )


def _answer(out: Path) -> dict[str, object]:
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "no-answer"}


async def run_probe(mode: str, work: Path, *, jailed: bool, models: Path | None) -> tuple[int, dict[str, object], int]:
    """The probe in mode: exit code, its answer and the milliseconds it took; work must exist."""
    out = work / "answer.json"
    args = [sys.executable, "-I", str(PROBE), mode, str(out)]
    if models is not None:
        args.append(str(models))
    started = time.monotonic()
    timeout = CONTROL_TIMEOUT_S if models is None else PROBE_TIMEOUT_S
    if jailed:
        assert models is not None
        try:
            await child.run_child(
                args, profile="detect", cwd=work, read=(str(models),), write=(str(work),), timeout_s=timeout
            )
            code = 0
        except child.ChildFailed as failed:
            code = failed.exit_code
    else:
        code = await run_unjailed(args, cwd=work, env=child.child_env(profile="detect"), timeout_s=timeout)
    return code, _answer(out), int((time.monotonic() - started) * 1000)


def folder(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _say(capsys: pytest.CaptureFixture[str], text: str) -> None:
    with capsys.disabled():
        print()
        print(text)


@pytest.mark.parametrize(("run", "mode", "jailed"), [("unjailed", "count", False), ("jailed", "count", True)])
async def test_the_stack_finds_email_and_person_without_a_network_event(
    run: str, mode: str, jailed: bool, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, answer, ms = await run_probe(mode, folder(tmp_path / run), jailed=jailed, models=models_root(os.environ))
    report = stack_line(run, code, answer, ms)
    _say(capsys, report)
    record_measurement(f"offline_stack_{run}", {**answer, "exit": code, "ms": ms})
    assert code == 0, report
    assert answer["email"] is True, report
    assert answer["person"] is True, report
    assert answer["net_events"] == 0, report


async def test_the_stack_runs_through_with_the_raising_tripwire_in_the_detect_jail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """offline.install_network_tripwire() in the detect jail: any network step would end the probe with exit 1."""
    code, answer, ms = await run_probe("raise", folder(tmp_path / "raise"), jailed=True, models=models_root(os.environ))
    report = stack_line("jailed-raise", code, answer, ms)
    _say(capsys, report)
    record_measurement("offline_stack_jailed_raise", {**answer, "exit": code, "ms": ms})
    assert code == 0, report
    assert answer["email"] is True, report
    assert answer["person"] is True, report
    assert answer["net_events"] == 0, report


@pytest.mark.parametrize("name", CONFIG_FILES)
def test_the_gliner2_configs_carry_no_remote_code(name: str) -> None:
    path = models_root(os.environ).joinpath(*GLINER_FOLDER) / name
    assert not has_key(json.loads(path.read_text(encoding="utf-8")), REMOTE_CODE_KEY), name


def test_tldextract_of_the_image_has_no_suffix_list_url_after_configure(monkeypatch: pytest.MonkeyPatch) -> None:
    import tldextract.tldextract as extractor_module

    for key in offline.OFFLINE_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(extractor_module, "TLD_EXTRACTOR", extractor_module.TLD_EXTRACTOR)
    offline.configure()
    assert extractor_module.TLD_EXTRACTOR.suffix_list_urls == ()


async def test_positive_control_tldextract_without_configure_reaches_for_the_net(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without configure and with an empty cache, tldextract tries the network: the probe can see a leak."""
    code, answer, ms = await run_probe("control", folder(tmp_path / "control"), jailed=False, models=None)
    report = stack_line("control", code, answer, ms)
    _say(capsys, report)
    record_measurement("offline_positive_control", {**answer, "exit": code, "ms": ms})
    events = answer.get("net_events")
    assert isinstance(events, int), report
    assert events >= 1, report
