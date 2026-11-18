"""The sanitize child: the cleaned copy and a closed answer in out.json (plan 02-17).

Called in process here (main(argv)); in the container it runs as
python -I -m pii_redaction_backend.workers.sanitize inside the jail of the
"sanitize" profile. What the sanitizer removes is held by test_sanitize.py
(plan 02-13); this file holds the child around it.
"""

import json
import os
from pathlib import Path

import pytest

from pii_redaction_backend.intake import sanitize as cleaner
from pii_redaction_backend.intake.verdict import Rejected
from pii_redaction_backend.workers import sanitize

Corpus = tuple[Path, dict[str, dict[str, object]]]
KEYS = {"verdict", "macrosRemoved", "externalLinksRemoved"}


def _run(source: Path, fmt: str, dst: Path, out: Path) -> tuple[int, dict[str, object]]:
    code = sanitize.main([str(source), fmt, str(dst), str(out)])
    answer = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    return code, answer


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["a.docx", "docx", "b.docx"],
        ["a.docx", "docx", "b.docx", "out.json", "extra"],
        ["a.docx", "pdf", "b.docx", "out.json"],
        ["a.docx", "DOCX", "b.docx", "out.json"],
    ],
)
def test_wrong_arguments_end_with_exit_two_and_nothing_written(tmp_path: Path, argv: list[str]) -> None:
    real = [str(tmp_path / part) if "." in part else part for part in argv]
    assert sanitize.main(real) == 2
    assert list(tmp_path.iterdir()) == []


def test_an_external_image_is_removed_and_counted(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    dst = tmp_path / "clean.docx"
    code, answer = _run(folder / "ext_image.docx", "docx", dst, tmp_path / "out.json")
    assert code == 0
    assert dst.is_file()
    assert set(answer) == KEYS
    assert answer["verdict"] == "ok"
    assert answer["macrosRemoved"] is False
    links = answer["externalLinksRemoved"]
    assert isinstance(links, int)
    assert links >= 1
    assert b"127.0.0.1" not in dst.read_bytes()


def test_macros_are_reported(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    code, answer = _run(folder / "macro_vba.docx", "docx", tmp_path / "clean.docx", tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "ok"
    assert answer["macrosRemoved"] is True


def test_an_odt_is_cleaned_as_odt(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    dst = tmp_path / "clean.odt"
    code, answer = _run(folder / "odt_ext_image.odt", "odt", dst, tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "ok"
    assert dst.is_file()


def test_a_harmless_file_reports_nothing_removed(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    code, answer = _run(folder / "harmless.docx", "docx", tmp_path / "clean.docx", tmp_path / "out.json")
    assert (code, answer) == (0, {"verdict": "ok", "macrosRemoved": False, "externalLinksRemoved": 0})


def test_a_rejection_carries_the_word_and_leaves_no_copy(tmp_path: Path) -> None:
    source = tmp_path / "broken.docx"
    source.write_bytes(b"PK\x03\x04 not a zip at all")
    dst = tmp_path / "clean.docx"
    code, answer = _run(source, "docx", dst, tmp_path / "out.json")
    assert code == 0
    assert answer == {"verdict": "damaged", "macrosRemoved": False, "externalLinksRemoved": 0}
    assert not dst.exists()


def test_a_rejected_word_passes_through_and_a_half_copy_is_removed(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = corpus

    def grows(_src: Path, dst: Path, _fmt: str) -> object:
        dst.write_bytes(b"half written")
        raise Rejected("too_large")

    monkeypatch.setattr(cleaner, "sanitize", grows)
    dst = tmp_path / "clean.docx"
    code, answer = _run(folder / "harmless.docx", "docx", dst, tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "too_large"
    assert not dst.exists()


def test_an_internal_error_is_damaged_and_leaves_no_copy(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = corpus

    def broken(_src: Path, dst: Path, _fmt: str) -> object:
        dst.write_bytes(b"half written")
        raise RuntimeError("secret detail")

    monkeypatch.setattr(cleaner, "sanitize", broken)
    dst = tmp_path / "clean.docx"
    code, answer = _run(folder / "harmless.docx", "docx", dst, tmp_path / "out.json")
    assert code == 0
    assert answer == {"verdict": "damaged", "macrosRemoved": False, "externalLinksRemoved": 0}
    assert not dst.exists()
    assert "secret" not in (tmp_path / "out.json").read_text(encoding="utf-8")


def test_running_out_of_memory_is_too_large(corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder, _ = corpus

    def hungry(_src: Path, _dst: Path, _fmt: str) -> object:
        raise MemoryError

    monkeypatch.setattr(cleaner, "sanitize", hungry)
    code, answer = _run(folder / "harmless.docx", "docx", tmp_path / "clean.docx", tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "too_large"


def test_the_answer_goes_through_a_temp_file_and_replace(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = corpus
    calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        calls.append((os.fspath(source), os.fspath(target)))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", spy)
    out = tmp_path / "out.json"
    assert sanitize.main([str(folder / "harmless.docx"), "docx", str(tmp_path / "clean.docx"), str(out)]) == 0
    assert (str(out) + ".tmp", str(out)) in calls
    assert sorted(path.name for path in tmp_path.iterdir()) == ["clean.docx", "out.json"]


def test_an_answer_that_cannot_be_written_is_exit_two_and_leaves_no_copy(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    dst = tmp_path / "clean.docx"
    out = tmp_path / "missing-folder" / "out.json"
    assert sanitize.main([str(folder / "harmless.docx"), "docx", str(dst), str(out)]) == 2
    assert not dst.exists()


def test_the_child_says_nothing_on_stdout_or_stderr(
    corpus: Corpus, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, manifest = corpus
    for name, entry in manifest.items():
        if not entry["sanitize"]:
            continue
        fmt = str(entry["expected_format"])
        sanitize.main([str(folder / name), fmt, str(tmp_path / f"clean.{fmt}"), str(tmp_path / "out.json")])
    sanitize.main([])
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_the_module_prints_and_logs_nothing() -> None:
    source = Path(sanitize.__file__).read_text(encoding="utf-8")
    assert "print(" not in source
    assert "logging" not in source
    assert "sys.stderr" not in source
