"""The parts of the network proof (tests/test_lo_network.py) that run everywhere, each with a positive control.

A canary that cannot count, a retarget that changes nothing or a macro ODT the
sanitizer refuses would let the container runs pass for the wrong reason.
"""

import http.client
import zipfile
from pathlib import Path

import pytest

from pii_redaction_backend.intake.verdict import OK
from pii_redaction_backend.workers import sanitize
from tests.test_lo_network import (
    CANDIDATES,
    CORPUS_ADDRESS,
    LAYERS,
    MACRO_MARKER_ODT,
    MARKER,
    Outcome,
    canary_sees_a_connect,
    closed_problems,
    macro_marker_odt,
    positive_control_word,
    retarget,
    running_canary,
)

Corpus = tuple[Path, dict[str, dict[str, object]]]
PORT = 41234


def test_the_canary_counts_a_plain_connect_and_a_request() -> None:
    with running_canary() as canary:
        assert canary.since(canary.snapshot()) == (0, [])
        assert canary_sees_a_connect(canary)
        mark = canary.snapshot()
        connection = http.client.HTTPConnection("127.0.0.1", canary.port, timeout=5)
        try:
            connection.request("GET", "/img.png")
            assert connection.getresponse().status == 404
        finally:
            connection.close()
        assert canary.since(mark) == (1, ["GET:/img.png"])


@pytest.mark.parametrize("name", CANDIDATES)
def test_retarget_points_every_candidate_to_the_canary(name: str, corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    target = tmp_path / name
    changed = retarget(folder / name, target, PORT)
    new = f"http://127.0.0.1:{PORT}/".encode("ascii")
    with zipfile.ZipFile(folder / name) as before, zipfile.ZipFile(target) as after:
        assert after.namelist() == before.namelist()
        assert [i.compress_type for i in after.infolist()] == [i.compress_type for i in before.infolist()]
        data = b"".join(after.read(info) for info in after.infolist())
        original = b"".join(before.read(info) for info in before.infolist())
    assert changed >= 1
    assert CORPUS_ADDRESS in original
    assert CORPUS_ADDRESS not in data
    assert new in data


def test_retarget_changes_nothing_in_a_file_without_an_address(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    assert retarget(folder / "harmless.odt", tmp_path / "harmless.odt", PORT) == 0
    with zipfile.ZipFile(tmp_path / "harmless.odt") as archive:
        first = archive.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


def test_the_macro_odt_carries_its_basic_and_the_sanitizer_takes_it_out(tmp_path: Path) -> None:
    marker = tmp_path / "out" / MARKER
    odt = macro_marker_odt(tmp_path / MACRO_MARKER_ODT, marker)
    with zipfile.ZipFile(odt) as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.infolist()[0].compress_type == zipfile.ZIP_STORED
        content = archive.read("content.xml").decode("utf-8")
        module = archive.read("Basic/Standard/Module1.xml").decode("utf-8")
        manifest = archive.read("META-INF/manifest.xml").decode("utf-8")
    assert 'script:event-name="dom:load"' in content
    assert "Standard.Module1.Main" in content
    assert f"Open &quot;{marker}&quot; For Output" in module
    assert 'manifest:full-path="Basic/Standard/Module1.xml"' in manifest

    clean = tmp_path / "clean.odt"
    answer = sanitize.clean(odt, "odt", clean)
    assert answer["verdict"] == OK
    assert answer["macrosRemoved"] is True
    with zipfile.ZipFile(clean) as archive:
        assert not [name for name in archive.namelist() if name.startswith("Basic/")]
        assert b"event-listener" not in archive.read("content.xml")


def test_the_layers_switch_one_protection_each() -> None:
    on = {name: (layer.sanitize, layer.harden, layer.jail) for name, layer in LAYERS.items()}
    assert on == {
        "a": (True, True, True),
        "b": (False, True, False),
        "c": (False, False, True),
        "d": (False, False, False),
    }


def test_the_positive_control_word() -> None:
    assert positive_control_word({"ext_image.docx": 0, "ext_template.docx": 2}) == "triggered"
    assert positive_control_word({"ext_image.docx": 0, "ext_template.docx": 0}) == "not_triggered"
    assert positive_control_word({}) == "not_triggered"


def _outcome(connections: int = 0, pdf: bool = True, macro: str = "-") -> Outcome:
    return Outcome(connections=connections, asked=[], pdf=pdf, word="ok", macro=macro)


def test_closed_problems_fire_on_each_failure_and_stay_empty_when_closed() -> None:
    assert closed_problems({"x": _outcome(), "m": _outcome(macro="absent")}, 0) == []
    assert closed_problems({"x": _outcome(connections=1)}, 0) == ["x: 1 connections"]
    assert closed_problems({"x": _outcome(pdf=False)}, 0) == ["x: no PDF (ok)"]
    assert closed_problems({"m": _outcome(macro="ran")}, 0) == ["m: the macro ran"]
    assert closed_problems({"x": _outcome()}, 2) == ["2 zombies"]
