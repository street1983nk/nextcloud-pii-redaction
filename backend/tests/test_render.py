"""Page 1 as PNG plus meta.json, and the LibreOffice command line.

The render child is called in process here (main(argv)); in the container it
runs as python -I -m pii_redaction_backend.workers.render. LibreOffice is not
installed on the development machine, so soffice is checked by its argument
list here and for real in CI (plan 15).
"""

import json
import sys
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.workers import child, render, soffice


def _two_page_pdf(path: Path) -> Path:
    document = pymupdf.open()
    for number in (1, 2):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Testseite {number}")
    document.save(path)
    document.close()
    return path


def test_page_one_becomes_a_png_with_its_meta(tmp_path: Path) -> None:
    source = _two_page_pdf(tmp_path / "in.pdf")
    out = tmp_path / "page-1.png"

    assert render.main([str(source), str(out), "120"]) == 0

    assert out.read_bytes().startswith(b"\x89PNG")
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["pages"] == 2
    assert 985 <= meta["width"] <= 1000, "A4 at 120 dpi is about 992 px wide"
    assert meta["height"] > meta["width"]


def test_a_broken_file_ends_with_exit_two_and_no_output(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7 this is not a pdf")
    out = tmp_path / "page-1.png"

    assert render.main([str(source), str(out), "120"]) == 2
    assert not out.exists()
    assert not (tmp_path / "meta.json").exists()


def test_wrong_arguments_end_with_exit_two(tmp_path: Path) -> None:
    assert render.main([]) == 2
    assert render.main([str(tmp_path / "a.pdf"), str(tmp_path / "b.png"), "zero"]) == 2


def test_the_soffice_command_is_exactly_the_documented_one(tmp_path: Path) -> None:
    source = tmp_path / "in.docx"
    outdir = tmp_path / "out"

    assert soffice.command(source, outdir, "17") == [
        "/usr/bin/soffice",
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nologo",
        "-env:UserInstallation=file:///tmp/lo-17",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(outdir),
        str(source),
    ]


@pytest.mark.parametrize("job_id", ["", "1a", "../x", "-1", "1 2"])
def test_a_job_id_that_is_not_digits_is_refused(tmp_path: Path, job_id: str) -> None:
    with pytest.raises(ValueError, match="digits"):
        soffice.command(tmp_path / "in.odt", tmp_path, job_id)


# -- the soffice call (plan 02-08) ------------------------------------------------------


async def test_convert_hands_libreoffice_a_tmpdir_inside_its_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    async def fake_run_child(args: list[str], **kwargs: object) -> None:
        seen.update(kwargs)
        seen["profile_existed"] = (tmp_path / "lo-5" / "tmp").is_dir()
        seen["profile_folders"] = sorted(path.name for path in (tmp_path / "lo-5").iterdir())
        (tmp_path / "out" / "in.pdf").write_bytes(b"%PDF-1.7\n")

    monkeypatch.setattr(soffice, "PROFILE_ROOT", str(tmp_path))
    monkeypatch.setattr(soffice, "run_child", fake_run_child)

    pdf = await soffice.convert(tmp_path / "in.docx", tmp_path / "out", "5")

    assert pdf == tmp_path / "out" / "in.pdf"
    assert seen["profile"] == "soffice"
    profile = tmp_path / "lo-5"
    # Only TMPDIR: HOME and XDG stay closed until a run proves them needed.
    assert seen["extra_env"] == {"TMPDIR": str(profile / "tmp")}
    assert seen["profile_folders"] == ["tmp"]
    assert seen["write"] == (str(tmp_path / "out"), str(profile))
    assert seen["diagnose"] is True
    assert seen["tail_lines"] == child.SOFFICE_TAIL_LINES
    assert seen["profile_existed"] is True
    # The profile with its temporary folder is gone after the run.
    assert not (tmp_path / "lo-5").exists()


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Unix sockets and uids need Linux")
def test_only_the_libreoffice_sockets_of_this_uid_are_removed(tmp_path: Path) -> None:
    assert sys.platform != "win32"
    import socket

    pipe = tmp_path / "OSL_PIPE_10001_SingleOfficeIPC_0123abcd"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(pipe))
    server.close()
    # Same name pattern, but a regular file: not ours to remove.
    lookalike = tmp_path / "OSL_PIPE_10001_SingleOfficeIPC_ffff"
    lookalike.write_bytes(b"")
    other = tmp_path / "exapp.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(other))
    server.close()

    soffice._remove_ipc_sockets(tmp_path)

    assert not pipe.exists()
    assert lookalike.exists()
    assert other.exists()


def test_the_real_soffice_profile_folders_pass_the_child_allowlist() -> None:
    # The values convert() hands over with the real PROFILE_ROOT are exactly
    # what child.child_env lets through for the soffice profile.
    profile = soffice.job_profile("5")
    env = {key: f"{profile.as_posix()}/{name}" for key, name in soffice.PROFILE_FOLDERS.items()}
    assert set(env) == child.SOFFICE_ENV
    assert child.child_env(env, profile="soffice") == {**child.SAFE_ENV, **env}
