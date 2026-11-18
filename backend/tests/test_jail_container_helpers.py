"""The parts of the container proof of plan 02-21 that run without the container.

The probe tests/probes/read_secrets.py and the helpers of test_jail_container.py
are checked here on every machine, so a broken probe cannot make the jail look
tight: a probe that read nothing would answer "denied" everywhere.
"""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import CORPUS_ENV, load_mounted_corpus
from tests.test_jail_container import PAGE_BREAK, PAGES, PROBE, docx_with_pages, expected_limits, vm_values

CANARY = "probe-canary-not-real"


def _probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("read_secrets_probe", PROBE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(tmp_path: Path, *paths: str) -> dict[str, Any]:
    canaries = tmp_path / "canaries.txt"
    canaries.write_text(f"{CANARY}\n", encoding="utf-8")
    out = tmp_path / "answer.json"
    assert _probe().main([str(out), str(canaries), "999999999", str(tmp_path / "foreign"), *paths]) == 0
    assert not out.with_name("answer.json.tmp").exists()
    return json.loads(out.read_text(encoding="utf-8"))


def test_positive_control_the_probe_reads_and_sees_the_canary(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text(f"key = {CANARY}", encoding="utf-8")
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    answer = _run(tmp_path, str(secret))
    assert answer["control"] == "read"
    assert answer["paths"] == {"/proc/999999999/environ": "missing", str(secret): "read"}
    assert answer["foreign_listing"] == "read"
    assert answer["canary_seen"] is True


def test_the_probe_answers_in_words_and_never_writes_a_value(tmp_path: Path) -> None:
    answer = _run(tmp_path, str(tmp_path / "absent"))
    assert answer["paths"][str(tmp_path / "absent")] == "missing"
    assert answer["foreign_listing"] == "missing"
    assert answer["canary_seen"] is False
    assert CANARY not in (tmp_path / "answer.json").read_text(encoding="utf-8")
    assert set(answer) == {
        "paths",
        "foreign_listing",
        "control",
        "env_keys",
        "canary_seen",
        "limits",
        "proc_self_limits",
        "socket_inet",
        "socket_unix",
    }


def test_the_probe_sees_a_canary_in_its_environment_but_names_only_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROBE_LEAK", CANARY)
    answer = _run(tmp_path)
    assert answer["canary_seen"] is True
    assert "PROBE_LEAK" in answer["env_keys"]
    assert CANARY not in (tmp_path / "answer.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("argv", [[], ["a", "b", "c"], ["a", "b", "pid", "d"]])
def test_the_probe_refuses_wrong_arguments(argv: list[str]) -> None:
    assert _probe().main(argv) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="no rlimits on Windows")
def test_the_probe_reports_its_rlimits(tmp_path: Path) -> None:
    limits = _run(tmp_path)["limits"]
    assert isinstance(limits, dict)
    assert set(limits) == {"CPU", "FSIZE", "NOFILE", "AS", "CORE"}


def test_the_300_page_docx_has_one_break_less_than_pages(tmp_path: Path) -> None:
    path = docx_with_pages(tmp_path / "pages.docx", PAGES)
    with zipfile.ZipFile(path) as archive:
        document = archive.read("word/document.xml").decode()
        assert set(archive.namelist()) == {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    assert document.count(PAGE_BREAK) == PAGES - 1
    assert document.count("<w:p>") == PAGES


def test_vm_values_reads_peak_and_high_water_mark() -> None:
    status = "Name:\tsoffice.bin\nVmPeak:\t  812345 kB\nVmSize:\t  700000 kB\nVmHWM:\t  234567 kB\nVmRSS:\t 1 kB\n"
    assert vm_values(status) == {"VmPeak": 812345, "VmHWM": 234567}
    assert vm_values("Name:\tkthreadd\n") == {}


def test_expected_limits_follow_the_profile() -> None:
    precheck = expected_limits("precheck")
    assert precheck == {
        "CPU": [65, 65],
        "FSIZE": [1024 * 1024, 1024 * 1024],
        "NOFILE": [256, 256],
        "AS": [1024**3, 1024**3],
        "CORE": [0, 0],
    }


@pytest.mark.skipif(sys.platform == "win32", reason="no rlimits on Windows")
def test_without_an_address_space_limit_the_child_keeps_the_parents() -> None:
    # The probe asks getrlimit on its own: an independent route to the same value.
    assert expected_limits("detect")["AS"] == _probe()._limits()["AS"]


def test_the_mounted_corpus_fails_loudly_without_its_variable(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match=CORPUS_ENV):
        load_mounted_corpus({})
    with pytest.raises(pytest.fail.Exception, match=CORPUS_ENV):
        load_mounted_corpus({CORPUS_ENV: str(tmp_path)})
    # Positive control: a folder with its manifest is taken.
    (tmp_path / "manifest.json").write_text('{"harmless.pdf": {"expect": ["ok"]}}', encoding="utf-8")
    assert load_mounted_corpus({CORPUS_ENV: str(tmp_path)}) == (tmp_path, {"harmless.pdf": {"expect": ["ok"]}})
