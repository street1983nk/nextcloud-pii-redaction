"""The PDFs of the real corpus as DOCX and ODT, made by LibreOffice outside the sandbox (plan 02-24, step 2).

usage: python -I convert_corpus.py <corpus> <outdir>

The product never sends a PDF to LibreOffice; it converts DOCX and ODT. To
measure LibreOffice with long real documents, the three PDFs of
ci/fetch_corpus.py are turned into a DOCX and an ODT each, by a foreign tool
and not by the code under test (phase 4 pattern): LibreOffice of the test
image with its PDF import (writer_pdf_import, part of libreoffice-core-nogui),
unjailed, in a throwaway container with --network none (sandbox.yml). The
product path then reads them like any other upload.

Each conversion gets a fresh profile and a fresh output folder, its own
process group and a time limit; a timeout kills the whole group. What it made
is moved to <outdir>/<stem>_pdf.<docx|odt>; manifest.json there names every
attempt with source, format, size, number of images, time and result (ok,
timeout, exit <code>, no_output). A failed conversion is written down, not
hidden: the container test fails on it (test_container_corpus.py), so the
measurement never runs on a smaller set without saying so. The files stay in
RUNNER_TEMP of the runner and are never uploaded (the PDFs are runtime
downloads only, see ci/fetch_corpus.py).

Lines in the job log:

    CORPUS-CONVERT source=<pdf> format=<docx|odt> result=<word> bytes=<n> images=<n> ms=<n>

Standard library only (it runs with the interpreter of the image). Exit 2 for
wrong arguments, a missing or malformed manifest or a corpus without a PDF;
otherwise 0, whatever the conversions did.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

SOFFICE: Final = "/usr/bin/soffice"
TIMEOUT_S: Final = 600.0
MANIFEST: Final = "manifest.json"
PDF_IMPORT: Final = "writer_pdf_import"
# Target format, the export filter of LibreOffice, and the folder of the package that holds the images.
TARGETS: Final = (
    ("docx", "docx:MS Word 2007 XML", "word/media/"),
    ("odt", "odt:writer8", "Pictures/"),
)
SUFFIX: Final = "_pdf"


@dataclass(frozen=True, slots=True)
class Converted:
    name: str
    source: str
    format: str
    result: str
    bytes: int
    images: int
    ms: int


def derived_name(pdf_name: str, fmt: str) -> str:
    """sample.pdf as DOCX: sample_pdf.docx (the name the container test and ci/soffice_cap.py expect)."""
    stem = pdf_name.removesuffix(".pdf")
    return f"{stem}{SUFFIX}.{fmt}"


def command(pdf: Path, outdir: Path, profile: Path, export: str) -> list[str]:
    return [
        SOFFICE,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nologo",
        f"-env:UserInstallation=file://{profile}",
        f"--infilter={PDF_IMPORT}",
        "--convert-to",
        export,
        "--outdir",
        str(outdir),
        str(pdf),
    ]


def run_group(argv: list[str], timeout_s: float) -> str:
    """Run argv in its own process group: ok, timeout (group killed) or exit <code>."""
    process = subprocess.Popen(  # noqa: S603 - a fixed command, the paths come from this script
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )
    try:
        code = process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        kill_group(process.pid)
        process.wait()
        return "timeout"
    finally:
        # Whatever soffice left in its group goes with it.
        kill_group(process.pid)
    return "ok" if code == 0 else f"exit {code}"


def kill_group(pgid: int) -> None:
    if sys.platform == "win32":
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return


def count_images(path: Path, folder: str) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(1 for name in archive.namelist() if name.startswith(folder) and not name.endswith("/"))


Runner = Callable[[list[str], float], str]


def convert_one(pdf: Path, outdir: Path, target: tuple[str, str, str], run: Runner = run_group) -> Converted:
    fmt, export, images_folder = target
    name = derived_name(pdf.name, fmt)
    profile = Path(tempfile.mkdtemp(prefix="convert-profile-"))
    work = Path(tempfile.mkdtemp(prefix="convert-out-"))
    started = time.monotonic()
    try:
        result = run(command(pdf, work, profile, export), TIMEOUT_S)
        ms = int((time.monotonic() - started) * 1000)
        made = work / f"{pdf.stem}.{fmt}"
        if result == "ok" and not made.is_file():
            result = "no_output"
        if result != "ok":
            return Converted(name, pdf.name, fmt, result, 0, 0, ms)
        target_path = outdir / name
        shutil.move(made, target_path)
        try:
            images = count_images(target_path, images_folder)
        except zipfile.BadZipFile:
            target_path.unlink()
            return Converted(name, pdf.name, fmt, "not_a_package", 0, 0, ms)
        return Converted(name, pdf.name, fmt, "ok", target_path.stat().st_size, images, ms)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


class BadCorpus(Exception):
    """The corpus folder has no usable manifest or no PDF."""


def pdf_names(corpus: Path) -> list[str]:
    try:
        data = json.loads((corpus / MANIFEST).read_text(encoding="utf-8"))
        files = data["files"]
        names = [entry["name"] for entry in files if entry["format"] == "pdf"]
    except (OSError, ValueError, KeyError, TypeError):
        raise BadCorpus from None
    if not names or not all(isinstance(name, str) and "/" not in name and name.endswith(".pdf") for name in names):
        raise BadCorpus
    return names


def line(entry: Converted) -> str:
    return (
        f"CORPUS-CONVERT source={entry.source} format={entry.format} result={entry.result.replace(' ', '_')} "
        f"bytes={entry.bytes} images={entry.images} ms={entry.ms}"
    )


def main(argv: list[str], run: Runner = run_group) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -I convert_corpus.py <corpus> <outdir>\n")
        return 2
    corpus, outdir = Path(argv[0]), Path(argv[1])
    try:
        names = pdf_names(corpus)
    except BadCorpus:
        sys.stderr.write("the corpus has no usable manifest.json with a PDF\n")
        return 2
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for name in names:
        for target in TARGETS:
            entry = convert_one(corpus / name, outdir, target, run)
            print(line(entry), flush=True)
            made.append(asdict(entry))
    temporary = outdir / f"{MANIFEST}.tmp"
    temporary.write_text(json.dumps({"files": made}, indent=1), encoding="utf-8")
    os.replace(temporary, outdir / MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
