"""The parts of the RES-02 proof (tests/test_offline_container.py) that run everywhere, each with a positive control.

The probe installs audit hooks, which cannot be removed, so every run that
gets that far is a child process (sys.executable -I). Without the models here
the stack itself cannot run; what runs is the argument check, the event
filter, the positive control and a stack run that fails at the model load
without any network event on the way.
"""

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.test_offline_container import PROBE, has_key, models_root, stack_line

CHILD_TIMEOUT_S = 180


def _probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("offline_stack_probe", PROBE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(args: list[str], cwd: Path) -> tuple[int, dict[str, object]]:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and the probe of this repository
        [sys.executable, "-I", str(PROBE), *args], cwd=cwd, check=False, timeout=CHILD_TIMEOUT_S
    )
    out = cwd / "answer.json"
    return result.returncode, (json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {})


@pytest.mark.parametrize(
    "argv",
    [[], ["count"], ["count", "out.json"], ["control", "out.json", "/models"], ["other", "out.json", "/m"]],
)
def test_the_probe_refuses_wrong_arguments(argv: list[str]) -> None:
    assert _probe().main(argv) == 2


def test_the_probe_refuses_a_relative_model_folder(tmp_path: Path) -> None:
    assert _probe().main(["count", str(tmp_path / "answer.json"), "models"]) == 2
    assert not (tmp_path / "answer.json").exists()


def test_the_event_filter_counts_the_network_and_not_the_local_steps() -> None:
    probe = _probe()
    # A peer, a lookup, a URL opener: counted, loopback peers included.
    assert probe.is_network_event("socket.connect", (None, ("127.0.0.1", 9)))
    assert probe.is_network_event("socket.sendto", (None, ("192.0.2.1", 53)))
    assert probe.is_network_event("socket.getaddrinfo", ("example.org", 443, 0, 0, 0))
    assert probe.is_network_event("socket.gethostbyname", ("example.org",))
    assert probe.is_network_event("urllib.Request", ("https://example.org", None, {}, "GET"))
    assert probe.is_network_event("http.client.connect", (None, "example.org", 443))
    assert probe.is_network_event("socket.bind", (None, ("0.0.0.0", 8080)))  # noqa: S104 - an audit argument only
    assert probe.is_network_event("socket.bind", (None, ("", 8080)))
    # No peer, nothing sent: socket creation (urllib3 at import), loopback and Unix binds, the own host name.
    assert not probe.is_network_event("socket.__new__", (None, socket.AF_INET, socket.SOCK_STREAM, 0))
    assert not probe.is_network_event("socket.bind", (None, ("::1", 0)))
    assert not probe.is_network_event("socket.bind", (None, ("127.0.0.1", 0)))
    assert not probe.is_network_event("socket.bind", (None, "/tmp/x.sock"))  # noqa: S108 - an audit argument only
    assert not probe.is_network_event("socket.gethostname", ())
    assert not probe.is_network_event("open", ("/etc/hosts", "r", 0))


def test_positive_control_the_probe_sees_tldextract_reach_for_the_net(tmp_path: Path) -> None:
    """Without configure and with an empty cache the probe counts the attempt; the tripwire stops it here as well."""
    code, answer = _run(["control", str(tmp_path / "answer.json")], tmp_path)
    assert code == 0, answer
    events = answer["net_events"]
    assert isinstance(events, int)
    assert events >= 1, answer
    assert answer["error"] == "-"


def test_the_stack_run_without_models_fails_at_the_load_and_counts_no_network_event(tmp_path: Path) -> None:
    """raise mode, so nothing can leave this machine; the imports of torch and Presidio make no network step."""
    code, answer = _run(["raise", str(tmp_path / "answer.json"), str(tmp_path / "no-models")], tmp_path)
    assert code == 1
    assert answer["error"] == "presidio:FileNotFoundError", answer
    assert answer["email"] is False
    assert answer["person"] is False
    assert answer["net_events"] == 0, answer


def test_has_key_finds_a_nested_key_and_nothing_else() -> None:
    assert has_key({"auto_map": {"AutoModel": "x.Model"}}, "auto_map")
    assert has_key({"encoder": [{"inner": {"auto_map": 1}}]}, "auto_map")
    assert not has_key({"model_name": "microsoft/mdeberta-v3-base", "list": ["auto_map"]}, "auto_map")


def test_models_root_fails_loudly_without_models(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception):
        models_root({})
    with pytest.raises(pytest.fail.Exception):
        models_root({"PII_MODELS": str(tmp_path)})
    gliner = tmp_path / "gliner2" / "1cb4166094dc58fa8d836429f060d6c95f62b495"
    gliner.mkdir(parents=True)
    assert models_root({"PII_MODELS": str(tmp_path)}) == tmp_path


def test_the_stack_line_names_every_field() -> None:
    answer = {"email": True, "person": True, "net_events": 0, "event_names": [], "error": "-"}
    assert stack_line("jailed", 0, answer, 1234) == (
        "OFFLINE-STACK run=jailed exit=0 email=True person=True net_events=0 events=- error=- ms=1234"
    )
