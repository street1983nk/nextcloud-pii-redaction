"""ci/soffice_cap.py: the cap rule, the comment for profiles.py, and every way the measurements are refused.

The rounding is checked against a float computation written here, not with
the integer formula of the script.
"""

import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import REPO_ROOT, ci_module

MIB = 1024 * 1024
STEP = 256 * MIB
MEASUREMENTS = REPO_ROOT / ".planning" / "phases" / "02-sicherer-dateieingang-und-kindprozess-sandbox"
RUN = "https://github.com/example/run/1"
SHA = "4fd4b05da277ab5d1cde3ee13e3f5cd0bb033685"


def sc() -> ModuleType:
    return ci_module("soffice_cap")


def by_float(vmpeak_kb: int) -> int:
    return math.ceil(vmpeak_kb * 1024 * 1.5 / STEP) * STEP


def entry(fmt: str, peak: int | None = 400_000, **change: object) -> dict[str, object]:
    ran = fmt != "pdf" and peak is not None
    base: dict[str, object] = {
        "format": fmt,
        "herkunft": "original",
        "bytes": 1000,
        "ergebnis": "review",
        "grund": None,
        "soffice_ende": "pdf" if ran else None,
        "soffice_vmpeak_kb": peak if ran else None,
        "soffice_vmhwm_kb": peak // 2 if ran and peak else None,
        "samples": 12 if ran else 0,
        "ms": 1500,
        "seiten": 3,
    }
    base.update(change)
    return base


def arch_data(peak: int = 400_000, override: dict[str, dict[str, object]] | None = None) -> dict[str, Any]:
    corpus = {}
    for name in sorted(sc().expected_names()):
        fmt = name.rsplit(".", 1)[-1]
        corpus[name] = (override or {}).get(name, entry(fmt, peak))
    return {
        "soffice_vmpeak_kb": {"harmless_docx": 368924, "docx_300_pages": 368924},
        "soffice_vmhwm_kb": {"harmless_docx": 221120, "docx_300_pages": 221008},
        "soffice_corpus": corpus,
    }


def merged(amd64: dict[str, Any] | None = None, arm64: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"amd64": amd64 or arch_data(), "arm64": arm64 or arch_data(), "run": RUN, "sha": SHA}


def _write(tmp_path: Path, data: object, name: str = "m.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# -- the rule ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vmpeak_kb",
    [1, 368924, 373608, 174762, 174763, 349525, 349526, 4_600_000, 2_796_202, 2_796_203],
)
def test_the_cap_is_the_smallest_256_mib_step_at_least_1_5_times_the_peak(vmpeak_kb: int) -> None:
    cap = sc().cap_for(vmpeak_kb)
    assert cap == by_float(vmpeak_kb)
    assert cap % STEP == 0
    assert cap >= vmpeak_kb * 1024 * 1.5
    assert cap - STEP < vmpeak_kb * 1024 * 1.5


def test_exactly_on_a_step_stays_on_it() -> None:
    # 1.5 x 349525.333 kB is 512 MiB; 349525 kB lies just below, so 512 MiB is enough.
    assert sc().cap_for(349525) == 2 * STEP
    assert sc().cap_for(349526) == 3 * STEP
    # The synthetic run of 02-24 (373608 kB on arm64) alone would give 768 MiB.
    assert sc().cap_for(373608) == 3 * STEP


@pytest.mark.parametrize("bad", [0, -1])
def test_a_peak_that_is_not_positive_is_refused(bad: int) -> None:
    with pytest.raises(sc().Refused):
        sc().cap_for(bad)


def test_the_set_is_the_ten_files_and_the_six_derived() -> None:
    names = sc().expected_names()
    assert len(names) == 16
    assert {"sh-1.docx", "sh-7.docx", "1913500.pdf", "1913500_pdf.docx", "1913500_pdf.odt"} <= names
    assert "BMBF_BuFI-2024_Hauptband_pdf.odt" in names


# -- the merged form -------------------------------------------------------------------------


def test_positive_control_both_architectures_give_the_cap_and_the_comment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arm = arch_data()
    arm["soffice_corpus"]["1800107_pdf.docx"] = entry("docx", 3_000_000)
    path = _write(tmp_path, merged(arm64=arm))

    assert sc().main([str(path), "2026-11-29"]) == 0

    out = capsys.readouterr().out.splitlines()
    summary = [line for line in out if line.startswith("SOFFICE-CAP ")]
    assert summary == [
        (
            f"SOFFICE-CAP mode=merged max_vmpeak_kb=3000000 at=arm64/1800107_pdf.docx cap_bytes={by_float(3_000_000)} "
            f"cap_mib={by_float(3_000_000) // MIB} values=36"
        )
    ]
    comment = [line for line in out if line.startswith("#")]
    assert comment[0] == f"# RLIMIT_AS of soffice (D-02-13), measured 2026-11-29 in sandbox run {RUN} (4fd4b05):"
    assert "VmPeak" in comment[1]
    assert any(line == "#   1800107_pdf.docx: 400000 / 200000 | 3000000 / 1500000" for line in comment)
    assert any(line.startswith("#   1913500.pdf: no soffice (") for line in comment)
    # Every file of the set and both made files stand in the comment.
    for name in [*sc().expected_names(), "harmless_docx", "docx_300_pages"]:
        assert any(line.startswith(f"#   {name}: ") for line in comment), name


def test_the_made_files_count_toward_the_highest_peak(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, merged(arch_data(peak=100_000), arch_data(peak=100_000)))
    assert sc().main([str(path), "2026-11-29"]) == 0
    assert "max_vmpeak_kb=368924 at=amd64/harmless_docx" in capsys.readouterr().out


def test_a_refusal_of_the_precheck_is_a_result_not_a_gap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    refused = entry("docx", None, ergebnis="failed", grund="too_large", samples=0)
    data = merged(arch_data(override={"sh-3.docx": refused}), arch_data(override={"sh-3.docx": refused}))
    assert sc().main([str(_write(tmp_path, data)), "2026-11-29"]) == 0
    out = capsys.readouterr().out
    assert "doc=sh-3.docx vmpeak_kb=- vmhwm_kb=- ms=1500 pages=3 result=failed reason=too_large" in out
    assert "#   sh-3.docx: no soffice (too_large) | no soffice (too_large)" in out


def test_negative_soffice_without_a_pdf_makes_the_merged_set_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    timeout = entry("odt", 2_000_000, ergebnis="failed", grund="render_failed", soffice_ende="timeout")
    data = merged(arm64=arch_data(override={"1800107_pdf.odt": timeout}))

    assert sc().main([str(_write(tmp_path, data)), "2026-11-29"]) == 3

    captured = capsys.readouterr()
    assert "SOFFICE-CAP-INCOMPLETE arch=arm64 doc=1800107_pdf.odt soffice=timeout" in captured.out
    # Its sampled value still counts toward the highest peak, never against it.
    assert "max_vmpeak_kb=2000000 at=arm64/1800107_pdf.odt" in captured.out
    assert "# RLIMIT_AS" not in captured.out
    assert "owner decides" in captured.err


def test_the_one_architecture_form_reports_an_incomplete_set_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    crash = entry("docx", 500_000, ergebnis="failed", grund="render_failed", soffice_ende="exit=1 signal=None")
    path = _write(tmp_path, arch_data(override={"sh-2.docx": crash}))
    assert sc().main(["--arch", "amd64", str(path)]) == 0
    out = capsys.readouterr().out
    assert "SOFFICE-CAP-INCOMPLETE arch=amd64 doc=sh-2.docx soffice=exit=1_signal=None" in out
    assert "SOFFICE-CAP mode=arch max_vmpeak_kb=500000 at=amd64/sh-2.docx" in out
    assert "# RLIMIT_AS" not in out


# -- refusals ---------------------------------------------------------------------------------


def _refused(tmp_path: Path, data: object, capsys: pytest.CaptureFixture[str], *args: str) -> str:
    path = _write(tmp_path, data)
    argv = [*args, str(path)] if args else [str(path), "2026-11-29"]
    assert sc().main(argv) == 2
    return capsys.readouterr().err


def test_negative_the_measurements_of_today_have_no_corpus_yet(capsys: pytest.CaptureFixture[str]) -> None:
    # The file of run 46123496042 holds only the two made files: no cap may come out of it.
    assert sc().main([str(MEASUREMENTS / "02-MEASUREMENTS.json"), "2026-11-29"]) == 2
    assert "soffice_corpus missing" in capsys.readouterr().err


def test_negative_one_architecture_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = merged()
    del data["arm64"]
    assert "architecture arm64 missing" in _refused(tmp_path, data, capsys)


def test_negative_a_file_of_the_set_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    arm = arch_data()
    del arm["soffice_corpus"]["BMBF_BuFI-2024_Hauptband_pdf.docx"]
    err = _refused(tmp_path, merged(arm64=arm), capsys)
    assert "arm64: corpus files missing: BMBF_BuFI-2024_Hauptband_pdf.docx" in err


def test_negative_the_architectures_measured_different_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arm = arch_data()
    arm["soffice_corpus"]["extra.docx"] = entry("docx")
    assert "different files" in _refused(tmp_path, merged(arm64=arm), capsys)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"soffice_vmpeak_kb": 0}, "vmpeak is no positive whole number"),
        ({"soffice_vmpeak_kb": True}, "vmpeak is no positive whole number"),
        ({"soffice_vmpeak_kb": "400000"}, "vmpeak is no positive whole number"),
        ({"soffice_vmpeak_kb": None}, "vmpeak is no positive whole number"),
        ({"soffice_vmhwm_kb": -5}, "vmhwm is no positive whole number"),
        ({"samples": 0}, "samples is no positive whole number"),
        ({"samples": None}, "never sampled"),
        ({"ms": -1}, "ms is no whole number"),
        ({"seiten": 1.5}, "pages is no whole number"),
        ({"format": "rtf"}, "no known format"),
        ({"ergebnis": None}, "has no result"),
        ({"grund": 7}, "has no result"),
        ({"soffice_ende": 3}, "soffice_ende is no word"),
    ],
)
def test_negative_a_malformed_corpus_value_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, object], message: str
) -> None:
    data = merged(arch_data(override={"sh-1.docx": entry("docx") | change}))
    err = _refused(tmp_path, data, capsys)
    assert "amd64/sh-1.docx" in err
    assert message in err


def test_negative_a_pdf_that_went_to_soffice_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pdf = entry("pdf", None, soffice_ende="pdf", soffice_vmpeak_kb=1, soffice_vmhwm_kb=1, samples=1)
    data = merged(arch_data(override={"1913500.pdf": pdf}))
    assert "never sends a PDF to soffice" in _refused(tmp_path, data, capsys)


@pytest.mark.parametrize("key", ["soffice_vmpeak_kb", "soffice_vmhwm_kb"])
def test_negative_the_made_files_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str) -> None:
    amd = arch_data()
    del amd[key]
    assert "missing" in _refused(tmp_path, merged(amd), capsys)
    amd = arch_data()
    del amd[key]["docx_300_pages"]
    assert "made file docx_300_pages missing" in _refused(tmp_path, merged(amd), capsys)


def test_negative_a_merged_file_without_a_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = merged()
    del data["run"]
    assert "names no run" in _refused(tmp_path, data, capsys)


def test_negative_unreadable_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert sc().main([str(bad), "2026-11-29"]) == 2
    assert sc().main([str(tmp_path / "missing.json"), "2026-11-29"]) == 2
    assert sc().main(["--arch", "amd64", str(bad)]) == 2
    assert "cannot be read" in capsys.readouterr().err
    assert "no measurements" in _refused(tmp_path, [1], capsys, "--arch", "amd64")


@pytest.mark.parametrize(
    "argv",
    [[], ["--arch", "x86", "m.json"], ["m.json"], ["m.json", "29.11.2026"], ["--arch", "amd64"], ["-x", "2026-11-29"]],
)
def test_wrong_arguments_are_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert sc().main(argv) == 2
    assert "usage" in capsys.readouterr().err
