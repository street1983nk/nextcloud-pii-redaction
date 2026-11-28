"""The address space cap of soffice out of the measurements (D-02-13, plan 02-24, step 4).

usage: python3 ci/soffice_cap.py --arch <amd64|arm64> <measurements.json>
       python3 ci/soffice_cap.py <02-MEASUREMENTS.json> <YYYY-MM-DD>

The rule of the owner (28.11.2026): the cap is the smallest multiple of
256 MiB that is at least 1.5 times the highest VmPeak of soffice.bin over
amd64 and arm64, measured with the real corpus (ci/fetch_corpus.py, the PDFs
also as DOCX and ODT by ci/convert_corpus.py) through the product path, and
with the two made files of plan 02-21.

The first form reads tests/out/measurements.json of one container run
(sandbox.yml calls it after the upload) and prints the value of that
architecture alone. The second reads the merged file of plan 02-24
({"amd64": {...}, "arm64": {...}, "run": <url>, "sha": <sha>}), demands both
architectures with the whole set, and prints the cap together with the
comment for profiles.py: every value, the date and the run.

Refused (exit 2): a missing architecture, key or file of the set, a value
that is no positive whole number, a run where soffice was called but never
sampled, two architectures with different file lists. Incomplete (exit 3, only
the merged form): soffice ended without a PDF for a file of the set (time
limit or crash); its VmPeak is only a lower bound, so the cap would rest on
a guess, and the owner decides first (its sampled value still counts toward
the highest VmPeak, never against it). The one-architecture form prints the
same lines and exits 0 for an incomplete set, so the CI log shows it.

Lines:

    SOFFICE-CAP-VALUE arch=<a> doc=<name> vmpeak_kb=<n|-> vmhwm_kb=<n|-> ms=<n|-> pages=<n|-> result=<..> reason=<..>
    SOFFICE-CAP-INCOMPLETE arch=<a> doc=<name> soffice=<how it ended>
    SOFFICE-CAP mode=<arch|merged> max_vmpeak_kb=<n> at=<arch>/<doc> cap_bytes=<n> cap_mib=<n> values=<n>

Standard library only.
"""

import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Final

MIB: Final = 1024 * 1024
STEP: Final = 256 * MIB
# 1.5 as a fraction, so the rounding is exact.
FACTOR_NUM: Final = 3
FACTOR_DEN: Final = 2
ARCHES: Final = ("amd64", "arm64")
MADE_KEY: Final = "soffice_vmpeak_kb"
MADE_HWM_KEY: Final = "soffice_vmhwm_kb"
MADE_FILES: Final = ("harmless_docx", "docx_300_pages")
CORPUS_KEY: Final = "soffice_corpus"
SOFFICE_DONE: Final = "pdf"
FORMATS: Final = frozenset({"pdf", "docx", "odt"})
DATE: Final = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]")


class Refused(Exception):
    """The measurements cannot carry a cap; the message says why, with names and keys only."""


def _sibling(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"soffice_cap_{name}", Path(__file__).with_name(f"{name}.py"))
    if spec is None or spec.loader is None:
        msg = f"ci/{name}.py cannot be loaded"
        raise Refused(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_names() -> frozenset[str]:
    """The originals of ci/fetch_corpus.py and, for each PDF, its DOCX and ODT of ci/convert_corpus.py."""
    fetch, convert = _sibling("fetch_corpus"), _sibling("convert_corpus")
    names = {document.name for document in fetch.DOCUMENTS}
    for document in fetch.DOCUMENTS:
        if document.format == "pdf":
            names |= {convert.derived_name(document.name, fmt) for fmt, _, _ in convert.TARGETS}
    return frozenset(names)


@dataclass(frozen=True, slots=True)
class Value:
    arch: str
    doc: str
    vmpeak_kb: int | None
    vmhwm_kb: int | None
    ms: int | None
    pages: int | None
    result: str
    reason: str | None
    soffice: str | None


def _count(value: object, where: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{where} is no positive whole number"
        raise Refused(msg)
    return value


def _whole(value: object, where: str) -> int | None:
    """A count that may be 0 (time in ms) or missing."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{where} is no whole number"
        raise Refused(msg)
    return value


def _made_values(arch: str, data: Mapping[str, Any]) -> list[Value]:
    peaks, hwms = data.get(MADE_KEY), data.get(MADE_HWM_KEY)
    if not isinstance(peaks, dict) or not isinstance(hwms, dict):
        msg = f"{arch}: {MADE_KEY} or {MADE_HWM_KEY} missing"
        raise Refused(msg)
    values = []
    for name in MADE_FILES:
        if name not in peaks or name not in hwms:
            msg = f"{arch}: made file {name} missing"
            raise Refused(msg)
        values.append(
            Value(
                arch,
                name,
                _count(peaks[name], f"{arch}/{name} vmpeak"),
                _count(hwms[name], f"{arch}/{name} vmhwm"),
                None,
                None,
                "made",
                None,
                SOFFICE_DONE,
            )
        )
    return values


def _corpus_value(arch: str, name: str, entry: object) -> Value:
    where = f"{arch}/{name}"
    if not isinstance(entry, dict):
        msg = f"{where} is no object"
        raise Refused(msg)
    fmt = entry.get("format")
    if fmt not in FORMATS:
        msg = f"{where} has no known format"
        raise Refused(msg)
    soffice = entry.get("soffice_ende")
    if soffice is not None and not isinstance(soffice, str):
        msg = f"{where} soffice_ende is no word"
        raise Refused(msg)
    result, reason = entry.get("ergebnis"), entry.get("grund")
    if not isinstance(result, str) or (reason is not None and not isinstance(reason, str)):
        msg = f"{where} has no result"
        raise Refused(msg)
    ran = soffice is not None
    if ran and fmt == "pdf":
        msg = f"{where}: the product never sends a PDF to soffice"
        raise Refused(msg)
    if ran and not _count(entry.get("samples"), f"{where} samples", optional=True):
        msg = f"{where}: soffice ran but was never sampled"
        raise Refused(msg)
    return Value(
        arch,
        name,
        _count(entry.get("soffice_vmpeak_kb"), f"{where} vmpeak", optional=not ran),
        _count(entry.get("soffice_vmhwm_kb"), f"{where} vmhwm", optional=not ran),
        _whole(entry.get("ms"), f"{where} ms"),
        _whole(entry.get("seiten"), f"{where} pages"),
        result,
        reason,
        soffice,
    )


def values_of(arch: str, data: object, expected: frozenset[str]) -> list[Value]:
    """Every soffice value of one architecture: the made files and the whole corpus set."""
    if not isinstance(data, dict):
        msg = f"{arch}: no measurements"
        raise Refused(msg)
    corpus = data.get(CORPUS_KEY)
    if not isinstance(corpus, dict):
        msg = f"{arch}: {CORPUS_KEY} missing"
        raise Refused(msg)
    missing = sorted(expected - set(corpus))
    if missing:
        msg = f"{arch}: corpus files missing: {', '.join(missing)}"
        raise Refused(msg)
    values = _made_values(arch, data)
    values += [_corpus_value(arch, name, corpus[name]) for name in sorted(corpus)]
    return values


def cap_for(vmpeak_kb: int) -> int:
    """The smallest multiple of 256 MiB that is at least 1.5 times vmpeak_kb KiB."""
    if vmpeak_kb <= 0:
        msg = "vmpeak must be positive"
        raise Refused(msg)
    need = vmpeak_kb * 1024 * FACTOR_NUM
    steps = -(-need // (FACTOR_DEN * STEP))
    return steps * STEP


@dataclass(frozen=True, slots=True)
class Cap:
    cap_bytes: int
    highest: Value
    values: tuple[Value, ...]
    incomplete: tuple[Value, ...]


def derive(per_arch: Mapping[str, object], arches: tuple[str, ...], expected: frozenset[str]) -> Cap:
    values: list[Value] = []
    names: dict[str, set[str]] = {}
    for arch in arches:
        if arch not in per_arch:
            msg = f"architecture {arch} missing"
            raise Refused(msg)
        found = values_of(arch, per_arch[arch], expected)
        names[arch] = {value.doc for value in found}
        values += found
    if len({frozenset(found) for found in names.values()}) > 1:
        msg = "the architectures measured different files"
        raise Refused(msg)
    # The made files always carry a value, so there is at least one.
    highest = max(values, key=lambda value: value.vmpeak_kb or 0)
    if highest.vmpeak_kb is None:
        msg = "no soffice value at all"
        raise Refused(msg)
    incomplete = tuple(value for value in values if value.soffice not in {None, SOFFICE_DONE})
    return Cap(cap_for(highest.vmpeak_kb), highest, tuple(values), incomplete)


def _dash(value: object) -> str:
    return "-" if value is None else str(value).replace(" ", "_")


def lines(cap: Cap, mode: str) -> list[str]:
    out = [
        f"SOFFICE-CAP-VALUE arch={v.arch} doc={v.doc} vmpeak_kb={_dash(v.vmpeak_kb)} vmhwm_kb={_dash(v.vmhwm_kb)} "
        f"ms={_dash(v.ms)} pages={_dash(v.pages)} result={_dash(v.result)} reason={_dash(v.reason)}"
        for v in cap.values
    ]
    out += [f"SOFFICE-CAP-INCOMPLETE arch={v.arch} doc={v.doc} soffice={_dash(v.soffice)}" for v in cap.incomplete]
    top = cap.highest
    out.append(
        f"SOFFICE-CAP mode={mode} max_vmpeak_kb={top.vmpeak_kb} at={top.arch}/{top.doc} "
        f"cap_bytes={cap.cap_bytes} cap_mib={cap.cap_bytes // MIB} values={len(cap.values)}"
    )
    return out


def comment(cap: Cap, run: str, sha: str, date: str) -> list[str]:
    """The comment for PROFILES["soffice"] in sandbox/profiles.py: every value, the date and the run."""
    top = cap.highest
    out = [
        f"# RLIMIT_AS of soffice (D-02-13), measured {date} in sandbox run {run} ({sha[:7]}):",
        f"# highest VmPeak {top.vmpeak_kb} kB ({top.arch}, {top.doc}); 1.5 x that, rounded up to",
        f"# a multiple of 256 MiB: {cap.cap_bytes // MIB} MiB. VmPeak / VmHWM in kB, amd64 | arm64:",
    ]
    docs = sorted({value.doc for value in cap.values})
    by_key = {(value.arch, value.doc): value for value in cap.values}
    for doc in docs:
        cells = []
        for arch in ARCHES:
            value = by_key.get((arch, doc))
            if value is None or value.vmpeak_kb is None:
                cells.append(f"no soffice ({_dash(value.reason if value else None)})")
            else:
                cells.append(f"{value.vmpeak_kb} / {value.vmhwm_kb}")
        out.append(f"#   {doc}: {' | '.join(cells)}")
    return out


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        msg = "the measurement file cannot be read"
        raise Refused(msg) from None


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 3 and argv[0] == "--arch" and argv[1] in ARCHES:
            cap = derive({argv[1]: _load(Path(argv[2]))}, (argv[1],), expected_names())
            print("\n".join(lines(cap, "arch")))
            return 0
        if len(argv) == 2 and not argv[0].startswith("-") and DATE.fullmatch(argv[1]):
            merged = _load(Path(argv[0]))
            if not isinstance(merged, dict) or not isinstance(merged.get("run"), str):
                msg = "the merged file names no run"
                raise Refused(msg)
            cap = derive(merged, ARCHES, expected_names())
            print("\n".join(lines(cap, "merged")))
            if cap.incomplete:
                sys.stderr.write("soffice ended without a PDF for a file of the set: the owner decides first\n")
                return 3
            print("\n".join(comment(cap, merged["run"], str(merged.get("sha", "")), argv[1])))
            return 0
    except Refused as refused:
        sys.stderr.write(f"refused: {refused}\n")
        return 2
    sys.stderr.write(
        "usage: python3 ci/soffice_cap.py --arch <amd64|arm64> <measurements.json>\n"
        "       python3 ci/soffice_cap.py <02-MEASUREMENTS.json> <YYYY-MM-DD>\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
