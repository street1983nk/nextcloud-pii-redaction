---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 02
subsystem: dependencies
tags: [supply-chain, pins, torch-cpu, exclude-newer, pip-audit, markers]
requires: []
provides: [exakte Pins Erkennungsstapel + pikepdf/lxml, torch nur aus explizitem CPU-Index, exclude-newer 2026-11-03, Marker container/linux, python.yml -m "not container", pip-audit mit +cpu-Strip]
affects: [02-09, 02-10, 02-12, 02-13, 02-16]
tech-stack:
  added: [pikepdf 10.17.0, lxml 6.1.3, presidio-analyzer 2.2.366, spacy 3.8.18, gliner2 2.1.0, torch 2.15.0+cpu, transformers 5.22.1, huggingface-hub 2.4.0, tokenizers 0.23.3, safetensors 0.8.0, numpy 2.4.6]
  patterns: [feste exclude-newer-Grenze statt relativer Frist, Lock-Regeln als *_findings mit Selbsttest auf verfälschter Probe]
key-files:
  created:
    - backend/tests/test_dependencies.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - .github/workflows/python.yml
    - .github/workflows/security.yml
decisions:
  - "transformers 5.22.1 mit huggingface-hub 2.4.0 und tokenizers 0.23.3 statt Spike-Stand 4.57.6 (sechs Advisories in 4.57.6); Owner-Freigabe 1 vom 16./17.11.2026"
  - "Zwei-Wochen-Regel für alle Pakete über [tool.uv] exclude-newer = 2026-11-03T00:00:00Z (fester Zeitpunkt, reproduzierbar); Owner-Freigabe 2 (Option B) vom 17.11.2026"
  - "Kein exclude-newer-package für torch: der PyTorch-CPU-Index liefert upload-time je Wheel (torch 2.15.0: 28.10.2026), die Grenze greift dort genauso"
  - "security.yml streicht das +cpu-Suffix von torch zwischen uv export und pip-audit --strict, sonst bricht die Prüfung mit not found ab"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 02: Abhängigkeiten und Marker Summary

Erkennungsstapel (Presidio, spaCy, GLiNER2 ohne `[local]`, torch-CPU, transformers 5.22.1) und pikepdf/lxml exakt gepinnt, torch nur aus dem expliziten PyTorch-CPU-Index, das ganze Lock per `exclude-newer = 2026-11-03` auf Releases mit mindestens zwei Wochen Alter festgelegt; pip-audit und OSV ohne Treffer.

## Commits

| Schritt | Commit |
|---|---|
| Pins, CPU-Index, Marker, python.yml, Gate-Test | 255a92c |
| security.yml: pip-audit sieht torch ohne +cpu | 27e45d8 |
| exclude-newer 2026-11-03, Neu-Lock, Gate-Regel | c3a039d |

## Owner-Freigaben (Task 1, Package Legitimacy Gate)

1. **Direkte Pakete (16./17.11.2026):** freigegeben wie gelistet, mit einer Änderung: transformers auf 5.x. Gewählt 5.22.1 (30.10.2026, neueste 5.x mit mindestens zwei Wochen Alter, nicht zurückgezogen), dazu huggingface-hub 2.4.0 und tokenizers 0.23.3 nach deren requires_dist. CVE-Prüfung belegt, inklusive CVE-2026-80047 (Fix ab 5.17.0). Gate-Nachmessung mit 5.22.1: 7 Datensätze, 2969 Dokumente, Ergebnisse identisch zum 4.57.6-Stand.
2. **Lock-Diff (17.11.2026):** freigegeben mit Option B: `[tool.uv] exclude-newer = "2026-11-03T00:00:00Z"`, die Zwei-Wochen-Regel gilt damit für alle Pakete, direkt und transitiv. Direkte Pins blieben unverändert und alle auflösbar.

### Lock-Diff durch exclude-newer (c3a039d)

| Paket | vorher (Upload) | jetzt (Upload) | Art |
|---|---|---|---|
| httpx2 | 2.16.2 (16.11.) | 2.16.0 (21.10.) | transitiv (starlette.testclient) |
| httpcore2 | 2.16.2 (16.11.) | 2.16.0 (21.10.) | transitiv |
| regex | 2026.11.15 (15.11.) | 2026.9.29 (29.09.) | transitiv (Presidio) |
| smart-open | 9.0.4 (14.11.) | 9.0.1 (29.10.) | transitiv (spaCy) |
| typer | 0.29.1 (11.11.) | 0.27.3 (06.10.) | transitiv (spaCy) |
| markdown-it-py | 4.3.0 (10.11.) | 4.2.0 (07.05.) | transitiv |
| phonenumbers | 9.0.43 (06.11.) | 9.0.42 (27.10.) | transitiv (Presidio) |
| filelock | 4.2.9 (04.11.) | 4.2.7 (02.11.) | transitiv, Override `>=4.2.1` hält |
| typing-inspection | 0.4.5 (04.11.) | 0.4.4 (12.08.) | transitiv (pydantic) |
| srsly | 2.5.6 (03.11. 23:38) | 2.5.5 (25.10.) | transitiv (spaCy) |
| coverage | 7.17.1 (03.11. 12:38) | 7.17.0 (22.10.) | dev (pytest-cov) |

Keine Pakete hinzugekommen oder weggefallen (106 Einträge vorher und nachher). Kein Datei-Upload im Lock liegt am oder nach dem 03.11.2026; `[options] exclude-newer` steht im Lock.

**torch und der CPU-Index:** download.pytorch.org liefert je Wheel eine upload-time (torch 2.15.0: 28.10.2026, 13:17 bis 13:19 UTC), uv wendet die Grenze dort also genauso an wie auf PyPI. Eine Ausnahme per `exclude-newer-package` ist weder nötig noch erwünscht; das Gate verbietet sie.

## Prüfungen

- pip-audit wie security.yml (`uv export --frozen --no-dev`, +cpu-Strip, `uvx pip-audit --strict --disable-pip`): No known vulnerabilities found.
- OSV querybatch: 94 Laufzeit-Pins und 14 Dev-Pins, 0 Treffer.
- ruff check und ruff format (Vollsatz) grün, pyright latest 0 Fehler, vulture grün.
- Volle Suite: 703 passed, 7 skipped (vorher 701 + 2 neue exclude-newer-Tests), Coverage 90,37 % (Grenze 90).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pip-audit --strict scheitert an torch 2.15.0+cpu**
- **Found during:** Task 2
- **Issue:** uv export schreibt `torch==2.15.0+cpu`; PyPI kennt keine lokale Version, `--strict` bricht mit not found ab.
- **Fix:** Schritt in security.yml streicht das +cpu-Suffix vor dem Audit; Reihenfolge und sed-Ausdruck per Test gehalten.
- **Files modified:** .github/workflows/security.yml, backend/tests/test_dependencies.py
- **Commit:** 27e45d8

**2. [Owner-Entscheid] Versionen abweichend vom Plan-Kontext**
- transformers 5.22.1 / huggingface-hub 2.4.0 / tokenizers 0.23.3 statt 4.57.6 / 0.36.2 / 0.22.2 (Freigabe 1). STACK-Mapping in test_dependencies.py entsprechend.

**3. [Owner-Entscheid] exclude-newer im Lock**
- Nicht im Plan vorgesehen, aus Freigabe 2; elf transitive Pakete zurückgestuft (Tabelle oben), Gate-Regel mit fünf Selbstproben (fehlend, relativ, junger Upload, Lock ohne Grenze, Paket-Ausnahme).
- **Commit:** c3a039d

**4. Kein eigener RED-Commit**
- Task 2 war `tdd="true"`, Tests und Pins gingen in einem Commit (255a92c) ein, weil die Gate-Tests ohne Lock nicht sinnvoll rot laufen; jede Regel hat stattdessen einen Selbsttest auf eine verfälschte Probe.

## Requirements

RES-02 und SAFE-02 bleiben offen: dieser Plan legt nur die Pakete fest. RES-02 (versteckte Netzaufrufe abgestellt) braucht offline.py (02-10) und den `--network none`-Beweis im Image, SAFE-02 (Vorprüfung) kommt mit 02-09.

## Threat Flags

Keine neue Angriffsfläche über das Threat-Register hinaus (T-02-SC, T-02-34 mitigiert: exakte Pins, Hashes im Lock, torch-Index-Gate, gliner2-Extra-Gate, pip-audit, Zwei-Wochen-Grenze).

## Self-Check: PASSED
