"""The precheck child: stages A, B and C on one file, a closed answer in out.json (plan 02-17).

The child is called in process here (main(argv)); in the container it runs as
python -I -m pii_redaction_backend.workers.precheck inside the jail of the
"precheck" profile (02-21 runs the whole corpus through the real jail).
"""

import json
import os
from pathlib import Path

import pytest

from pii_redaction_backend.intake import pdfcheck, verdict
from pii_redaction_backend.workers import precheck

Corpus = tuple[Path, dict[str, dict[str, object]]]
KEYS = {"verdict", "format", "pages", "signed", "ownerProtected"}


def _run(source: Path, expected: str, out: Path) -> tuple[int, dict[str, object]]:
    code = precheck.main([str(source), expected, str(out)])
    answer = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    return code, answer


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["a.pdf", "pdf"],
        ["a.pdf", "pdf", "out.json", "extra"],
        ["a.pdf", "txt", "out.json"],
        ["a.pdf", "PDF", "out.json"],
        ["a.pdf", "", "out.json"],
    ],
)
def test_wrong_arguments_end_with_exit_two_and_no_answer(tmp_path: Path, argv: list[str]) -> None:
    out = tmp_path / "out.json"
    real = [str(tmp_path / part) if part.endswith((".pdf", ".json")) else part for part in argv]
    assert precheck.main(real) == 2
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_every_file_of_the_corpus_gets_a_word_of_its_manifest(corpus: Corpus, tmp_path: Path) -> None:
    folder, manifest = corpus
    wrong: list[str] = []
    checked = 0
    for name, entry in sorted(manifest.items()):
        # unit_only files are judged by one stage only (zip_entries_10000 has empty parts).
        if entry["unit_only"]:
            continue
        out = tmp_path / f"{name}.json"
        code, answer = _run(folder / name, str(entry["expected_format"]), out)
        expected = set(entry["expect"])  # type: ignore[arg-type]
        word = answer.get("verdict")
        confirm = "confirm" in expected and word == "ok" and answer.get("signed") is True
        if code != 0 or set(answer) != KEYS or (word not in expected and not confirm):
            wrong.append(f"{name}: exit={code} answer={answer}")
            continue
        if answer["ownerProtected"] is not bool(entry["owner_protected"]):
            wrong.append(f"{name}: ownerProtected={answer['ownerProtected']}")
        checked += 1
    assert wrong == []
    assert checked >= 30, "the corpus ran almost empty"


def test_owner_protection_is_set_only_for_the_owner_only_pdf(corpus: Corpus, tmp_path: Path) -> None:
    folder, manifest = corpus
    owners = sorted(name for name, entry in manifest.items() if entry["owner_protected"])
    assert owners == ["pdf_owner_only.pdf"]
    code, answer = _run(folder / "pdf_owner_only.pdf", "pdf", tmp_path / "out.json")
    assert code == 0
    assert answer == {"verdict": "ok", "format": "pdf", "pages": 1, "signed": False, "ownerProtected": True}


def test_a_signed_pdf_is_ok_and_marked(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    code, answer = _run(folder / "pdf_signed.pdf", "pdf", tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "ok"
    assert answer["signed"] is True


def test_the_harmless_files_pass_with_their_format(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    code, answer = _run(folder / "harmless.pdf", "pdf", tmp_path / "pdf.json")
    assert (code, answer) == (
        0,
        {"verdict": "ok", "format": "pdf", "pages": 1, "signed": False, "ownerProtected": False},
    )
    for fmt in ("docx", "odt"):
        code, answer = _run(folder / f"harmless.{fmt}", fmt, tmp_path / f"{fmt}.json")
        # The page count of a DOCX or ODT comes only from the LibreOffice PDF (plan 02-19).
        assert (code, answer) == (
            0,
            {"verdict": "ok", "format": fmt, "pages": None, "signed": False, "ownerProtected": False},
        )


def test_a_rejection_carries_the_word_and_nothing_of_the_file(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    code, answer = _run(folder / "wrong_docx_as_pdf.pdf", "pdf", tmp_path / "out.json")
    assert code == 0
    assert answer == {"verdict": "wrong_type", "format": None, "pages": None, "signed": False, "ownerProtected": False}


def test_an_internal_error_is_damaged_fail_closed(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = corpus

    def broken(_path: Path) -> object:
        raise RuntimeError("parser exploded with a secret file name")

    monkeypatch.setattr(pdfcheck, "check_pdf", broken)
    code, answer = _run(folder / "harmless.pdf", "pdf", tmp_path / "out.json")
    assert code == 0
    assert answer == {"verdict": "damaged", "format": None, "pages": None, "signed": False, "ownerProtected": False}
    assert "secret" not in (tmp_path / "out.json").read_text(encoding="utf-8")


def test_running_out_of_memory_is_too_large(corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder, _ = corpus

    def hungry(_path: Path) -> object:
        raise MemoryError

    monkeypatch.setattr(pdfcheck, "check_pdf", hungry)
    code, answer = _run(folder / "harmless.pdf", "pdf", tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "too_large"


def test_every_word_is_one_of_the_closed_list(corpus: Corpus, tmp_path: Path) -> None:
    folder, manifest = corpus
    for name, entry in manifest.items():
        if entry["unit_only"]:
            continue
        _, answer = _run(folder / name, str(entry["expected_format"]), tmp_path / "out.json")
        assert answer["verdict"] in verdict.VERDICTS


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
    assert precheck.main([str(folder / "harmless.pdf"), "pdf", str(out)]) == 0
    assert calls == [(str(out) + ".tmp", str(out))]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out.json"]


def test_an_answer_that_cannot_be_written_is_exit_two(corpus: Corpus, tmp_path: Path) -> None:
    folder, _ = corpus
    out = tmp_path / "missing-folder" / "out.json"
    assert precheck.main([str(folder / "harmless.pdf"), "pdf", str(out)]) == 2
    assert not out.parent.exists()


def test_a_missing_source_is_damaged(tmp_path: Path) -> None:
    code, answer = _run(tmp_path / "gone.pdf", "pdf", tmp_path / "out.json")
    assert code == 0
    assert answer["verdict"] == "damaged"


def test_the_child_says_nothing_on_stdout_or_stderr(
    corpus: Corpus, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, manifest = corpus
    for name, entry in manifest.items():
        if entry["unit_only"]:
            continue
        precheck.main([str(folder / name), str(entry["expected_format"]), str(tmp_path / "out.json")])
    precheck.main([])

    def broken(_path: Path) -> object:
        raise RuntimeError("loud")

    monkeypatch.setattr(pdfcheck, "check_pdf", broken)
    precheck.main([str(folder / "harmless.pdf"), "pdf", str(tmp_path / "out.json")])
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_the_module_prints_and_logs_nothing() -> None:
    source = Path(precheck.__file__).read_text(encoding="utf-8")
    assert "print(" not in source
    assert "logging" not in source
    assert "sys.stderr" not in source
