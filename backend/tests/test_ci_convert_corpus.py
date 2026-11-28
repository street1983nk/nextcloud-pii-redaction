"""ci/convert_corpus.py without LibreOffice: the command, the names, what is written down when a conversion fails.

The real conversion runs only in sandbox.yml (the test image has LibreOffice,
this machine does not). Here a fake runner stands in for soffice; the process
group handling is checked with real processes on Linux.
"""

import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

from tests.conftest import ci_module


def cc() -> ModuleType:
    return ci_module("convert_corpus")


def _package(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


DOCX = _package({"word/document.xml": b"<w/>", "word/media/image1.png": b"p", "word/media/image2.png": b"p"})
ODT = _package({"content.xml": b"<o/>", "Pictures/a.png": b"p", "Pictures/": b""})


def _corpus(root: Path, names: list[tuple[str, str]]) -> Path:
    root.mkdir()
    files = [{"name": name, "format": fmt} for name, fmt in names]
    (root / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    for name, _ in names:
        (root / name).write_bytes(b"%PDF-1.7")
    return root


class FakeSoffice:
    """Plays soffice: writes <stem>.<fmt> into --outdir, or does what the test asks."""

    def __init__(self, answer: str = "ok", body: dict[str, bytes] | None = None, write: bool = True) -> None:
        self.answer = answer
        self.body = body or {"docx": DOCX, "odt": ODT}
        self.write = write
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], timeout_s: float) -> str:
        assert timeout_s == cc().TIMEOUT_S
        self.calls.append(argv)
        outdir = Path(argv[argv.index("--outdir") + 1])
        fmt = argv[argv.index("--convert-to") + 1].split(":", 1)[0]
        assert outdir.is_dir()
        if self.write:
            (outdir / f"{Path(argv[-1]).stem}.{fmt}").write_bytes(self.body[fmt])
        return self.answer

    def profiles(self) -> list[Path]:
        prefix = "-env:UserInstallation=file://"
        return [Path(next(a for a in argv if a.startswith(prefix)).removeprefix(prefix)) for argv in self.calls]


def test_the_derived_names() -> None:
    assert cc().derived_name("1913500.pdf", "docx") == "1913500_pdf.docx"
    assert cc().derived_name("BMBF_BuFI-2024_Hauptband.pdf", "odt") == "BMBF_BuFI-2024_Hauptband_pdf.odt"


def test_the_time_limit_fits_the_arm64_bufi_conversion() -> None:
    """arm64 needs about 10 to 11 min per format for the 451-page BuFI PDF (run 46150036977)."""
    assert cc().TIMEOUT_S == 1800.0


def test_the_command_imports_the_pdf_into_writer_and_exports_the_format(tmp_path: Path) -> None:
    argv = cc().command(tmp_path / "a.pdf", tmp_path / "out", tmp_path / "profile", "docx:MS Word 2007 XML")
    assert argv[0] == "/usr/bin/soffice"
    assert "--headless" in argv
    assert "--infilter=writer_pdf_import" in argv
    assert argv[argv.index("--convert-to") + 1] == "docx:MS Word 2007 XML"
    assert argv[argv.index("--outdir") + 1] == str(tmp_path / "out")
    assert f"-env:UserInstallation=file://{tmp_path / 'profile'}" in argv
    assert argv[-1] == str(tmp_path / "a.pdf")
    assert [fmt for fmt, _, _ in cc().TARGETS] == ["docx", "odt"]


def test_positive_control_every_pdf_becomes_a_docx_and_an_odt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = _corpus(tmp_path / "corpus", [("a.pdf", "pdf"), ("b.docx", "docx"), ("c.pdf", "pdf")])
    out = tmp_path / "out"
    soffice = FakeSoffice()

    assert cc().main([str(corpus), str(out)], soffice) == 0

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["files"]
    assert [(e["name"], e["source"], e["format"], e["result"]) for e in manifest] == [
        ("a_pdf.docx", "a.pdf", "docx", "ok"),
        ("a_pdf.odt", "a.pdf", "odt", "ok"),
        ("c_pdf.docx", "c.pdf", "docx", "ok"),
        ("c_pdf.odt", "c.pdf", "odt", "ok"),
    ]
    assert manifest[0]["images"] == 2
    assert manifest[1]["images"] == 1
    assert manifest[0]["bytes"] == len(DOCX)
    assert (out / "a_pdf.docx").read_bytes() == DOCX
    assert sorted(path.name for path in out.iterdir()) == [
        "a_pdf.docx",
        "a_pdf.odt",
        "c_pdf.docx",
        "c_pdf.odt",
        "manifest.json",
    ]
    # The DOCX of the corpus is not sent to the PDF import.
    assert all(argv[-1].endswith(".pdf") for argv in soffice.calls)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 4
    assert lines[0].startswith(f"CORPUS-CONVERT source=a.pdf format=docx result=ok bytes={len(DOCX)} images=2 ms=")
    assert lines[1].startswith(f"CORPUS-CONVERT source=a.pdf format=odt result=ok bytes={len(ODT)} images=1 ms=")


def test_every_conversion_gets_a_fresh_profile_that_is_removed_after(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path / "corpus", [("a.pdf", "pdf")])
    soffice = FakeSoffice()
    assert cc().main([str(corpus), str(tmp_path / "out")], soffice) == 0
    profiles = soffice.profiles()
    assert len(set(profiles)) == 2
    assert not any(profile.exists() for profile in profiles)
    workdirs = [Path(argv[argv.index("--outdir") + 1]) for argv in soffice.calls]
    assert not any(folder.exists() for folder in workdirs)


@pytest.mark.parametrize(
    ("answer", "write", "body", "result"),
    [
        ("timeout", False, None, "timeout"),
        ("exit 81", False, None, "exit 81"),
        ("ok", False, None, "no_output"),
        ("ok", True, {"docx": b"not a zip", "odt": b"not a zip"}, "not_a_package"),
    ],
)
def test_negative_a_failed_conversion_is_written_down_and_leaves_no_file(
    tmp_path: Path, answer: str, write: bool, body: dict[str, bytes] | None, result: str
) -> None:
    corpus = _corpus(tmp_path / "corpus", [("a.pdf", "pdf")])
    out = tmp_path / "out"
    assert cc().main([str(corpus), str(out)], FakeSoffice(answer, body, write)) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["files"]
    assert [(e["name"], e["result"], e["bytes"], e["images"]) for e in manifest] == [
        ("a_pdf.docx", result, 0, 0),
        ("a_pdf.odt", result, 0, 0),
    ]
    assert sorted(path.name for path in out.iterdir()) == ["manifest.json"]


@pytest.mark.parametrize(
    "manifest",
    [
        None,
        "not json",
        json.dumps({"files": []}),
        json.dumps({"files": [{"name": "a.docx", "format": "docx"}]}),
        json.dumps({"files": [{"name": "../a.pdf", "format": "pdf"}]}),
        json.dumps({"files": [{"name": "a.pdf"}]}),
        json.dumps({"other": 1}),
        json.dumps([1, 2]),
    ],
)
def test_negative_a_corpus_without_a_usable_pdf_is_exit_2(
    tmp_path: Path, manifest: str | None, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    if manifest is not None:
        (corpus / "manifest.json").write_text(manifest, encoding="utf-8")
    soffice = FakeSoffice()
    assert cc().main([str(corpus), str(tmp_path / "out")], soffice) == 2
    assert soffice.calls == []
    assert "no usable manifest" in capsys.readouterr().err


def test_wrong_arguments_are_exit_2() -> None:
    assert cc().main([]) == 2
    assert cc().main(["a"]) == 2


# -- the process group, with real processes ------------------------------------------------


@pytest.mark.linux
def test_run_group_ok_and_exit_code() -> None:
    assert cc().run_group([sys.executable, "-I", "-c", "raise SystemExit(0)"], 30) == "ok"
    assert cc().run_group([sys.executable, "-I", "-c", "raise SystemExit(3)"], 30) == "exit 3"


@pytest.mark.linux
def test_negative_a_timeout_kills_the_group_with_its_grandchild(tmp_path: Path) -> None:
    ids = tmp_path / "ids"
    script = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(ids)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    started = time.monotonic()
    assert cc().run_group([sys.executable, "-I", "-c", script], 2) == "timeout"
    assert time.monotonic() - started < 30
    grandchild = int(ids.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _alive(grandchild):
        time.sleep(0.1)
    assert not _alive(grandchild)


def _alive(pid: int) -> bool:
    """True while pid exists and is no zombie."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return False
    return stat.rpartition(")")[2].split()[0] != "Z" and os.path.exists(f"/proc/{pid}")
