---
quick_id: 261128-omr
phase: quick-261128-omr
plan: 01
type: tdd
date: 2026-11-28
requirements: [QUICK-261128-omr]
key-files:
  modified:
    - ci/convert_corpus.py
    - backend/tests/test_ci_convert_corpus.py
    - .planning/STATE.md
commits:
  red: 0b2709d
  green: 3602363
status: done, push pending
---

# Quick 261128-omr: convert_corpus time limit 1800 s for the arm64 BuFI conversion

## Was geändert wurde

- `ci/convert_corpus.py`: `TIMEOUT_S` von `600.0` auf `1800.0`, darüber ein kurzer englischer Kommentar mit Lauf, Messwerten und Budget. Sonst keine Codeänderung, `sandbox.yml` (`timeout-minutes: 120`) unverändert.
- `backend/tests/test_ci_convert_corpus.py`: neuer Test `test_the_time_limit_fits_the_arm64_bufi_conversion` pinnt `TIMEOUT_S == 1800.0`.

## Warum (Befund A)

CI-Lauf 46150036977 (Commit bddb6a1, Branch phase-02): auf arm64 lief die Umwandlung von `BMBF_BuFI-2024_Hauptband.pdf` (451 Seiten) für DOCX und ODT in die 600-s-Grenze. amd64 brauchte 190 s und 226 s. Schritt "Convert the PDFs": 14,5 min auf amd64, 43 min auf arm64 (darin zweimal 600 s). Faktor arm64/amd64 ca. 3, BuFI auf arm64 also ca. 10 bis 11 min je Format.

Budget im realistischen schlechtesten Fall (nur die zwei BuFI-Umwandlungen an der Grenze): ca. 23 + 60 + 3 Build + 8 Tests = ca. 95 min, unter 120 min.

## Commits

| Schritt | Hash | Nachricht |
|---------|------|-----------|
| RED | 0b2709d | test(quick-261128-omr): convert_corpus time limit 1800 s (RED) |
| GREEN | 3602363 | fix(quick-261128-omr): convert_corpus time limit 1800 s for the arm64 BuFI conversion |

RED-Fehler: `AssertionError: assert 600.0 == 1800.0`.

## Gates (aus backend/)

- ruff check und ruff format --check: sauber
- pyright (latest): 0 errors
- vulture: sauber
- Volle Suite: 1633 passed, 74 skipped

## Offen

- Push ausstehend (Owner fragen).
- Nachweis im nächsten CI-Lauf: arm64 wandelt BuFI nach docx und odt mit result=ok um, Job unter 120 min.
