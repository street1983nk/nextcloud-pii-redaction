---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 03
subsystem: l10n, gates
tags: [l10n, trilingual, gates, logging, php-static]
requires: [01-01]
provides:
  - "php/l10n/{de,de_DE,en,fr}.json/.js mit 94 Einträgen aus dem UI-SPEC-Textvertrag"
  - "backend/tests/test_php_gates.py: Regeln 1 bis 20 mit je einem Selbsttest"
  - "backend/tests/test_log_calls.py: AST-Gate für Python-Logaufrufe, extra-Allowlist aus dem SKELETON"
  - "test_trilingual.py: Gleichstand, de == de_DE, Platzhalter, U+00A0, Kürze (3 Sätze/240 Zeichen), Banner ohne Versionen, t()/n()-Abgleich"
  - "test_public_texts.py: php/l10n im Umlaut-Gate, Ersatzwort schwaerz, Reichweite des Strich-Scans"
affects: [01-04, 01-06, 01-08, 01-09, 01-11, 01-12, 01-13, 01-14, 01-17, 01-19, 01-20]
tech-stack:
  added: []
  patterns:
    - "Gate iteriert über vorhandene Dateien, Vollständigkeit prüft Plan 17"
    - "Regel 12: Methodenrumpf bis zur eigenen schließenden Klammer, Aufruf recheck\\w*("
    - "Python-Logs: Literal ohne % und {, kein exception, extra nur als Dict-Literal mit erlaubten Schlüsseln"
key-files:
  created:
    - php/l10n/{de,de_DE,en,fr}.json
    - php/l10n/{de,de_DE,en,fr}.js
    - backend/tests/test_php_gates.py
    - backend/tests/test_log_calls.py
  modified:
    - backend/tests/test_trilingual.py
    - backend/tests/test_public_texts.py
    - backend/tests/test_main.py
    - backend/src/pii_redaction_backend/main.py
    - backend/src/pii_redaction_backend/nc.py
key-decisions:
  - "AVS-Regeln 12 (Mounts) und 13 (verbotene Schlüssel an den Container) entfallen; die Nummern 12 bis 20 tragen die PII-Regeln des Plans"
  - "Regel 3 verlangt zusätzlich genau einen exAppRequest-Aufruf in ExAppService.php, sobald die Datei existiert"
  - "Regel 20 zählt auch \\time(); getTime() und microtime() zählen nicht"
  - "Logzeile in enabled_handler ohne %s: 'enable state changed' mit extra enabled"
requirements-completed: []  # PLAT-05 und JOB-02 nur als Gates vorbereitet; Erfüllung durch Controller/Notifier in Plan 08 bis 14
metrics:
  duration: "ca. 45 min"
  completed: 2026-11-07
  tasks: 3
  files: 15
---

# Phase 1 Plan 03: Kataloge und Gates Summary

Alle Texte der Phase stehen jetzt in vier Katalogen (de, de_DE, en, fr), 94 Einträge je Sprache. Dazu kommen statische PHP-Gates 1 bis 20, ein AST-Gate für Python-Logaufrufe und ein erweitertes Dreisprachigkeits-Gate. Jede Regel hat einen Selbsttest.

## Ergebnis

- **Task 1 (`132284d`):** Die Texte sind wörtlich aus dem UI-SPEC-Textvertrag übernommen (Fläche 1, 2, 3, 5 und die Fehlertexte je Grund), ohne eigene Ergänzungen. Plural läuft über zwei `_%n …_::_%n …_`-Schlüssel. Im Französischen steht U+00A0 vor `:`, innerhalb `« »` und in der Versionszeile. Die Namenszusätze der Kopie sind keine Katalogeinträge (Plan 14). Die `.js`-Zwillinge kommen aus `scripts/l10n_js.py --root ../php/l10n`.
- **Task 2 (`3e82198`):** `test_php_gates.py` hat 20 Regeln und 20 `test_self_rule*`. `test_log_calls.py` hat 6 Selbsttests. Dazu kommt ein Test, der die Allowlist mit `logs.ALLOWED_EXTRA` abgleicht, sobald Plan 06 sie anlegt. Ein Produkt-Fix im Skeleton entfernt `LOGGER.exception` und `%s` aus `main.py`; `error_type` heißt jetzt `exc_type` (main.py, nc.py, test_main.py).
- **Task 3 (`25f19ee`):** `test_trilingual.py` prüft `php/l10n` in allen genannten Punkten. Die Platzhalter- und U+00A0-Regeln gelten auch für `backend/l10n`. `test_public_texts.py` nimmt `php/l10n/de*.json` ins Umlaut-Gate auf, ergänzt `schwaerz` und prüft, dass der Strich-Scan `php/`, `backend/l10n/`, die READMEs, `docs/` und `CHANGELOG.md` erreicht.

Gates in `backend/`: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture leer, pytest 205 passed (seriell). Die Akzeptanz-greps treffen (20 Selbsttests, 6 Log-Selbsttests, U+00A0, de_DE, 240, four_sentences, 4 Selbsttests in trilingual).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Weitere Platzhalter-Logzeile im Skeleton**
- **Found during:** Task 2
- **Issue:** `main.py` hatte neben `LOGGER.exception` auch `LOGGER.info("app %s", ...)`. Das neue AST-Gate verbietet beides.
- **Fix:** `LOGGER.info("enable state changed", extra={"enabled": enabled})`.
- **Commit:** 3e82198

**2. [Rule 3 - Blocking] test_main.py las das Feld error_type**
- **Fix:** Der Test liest jetzt `exc_type`.
- **Commit:** 3e82198

**3. [Rule 2] Gate-Abweichungen von der AVS-Vorlage**
- Regel 4 kennt zusätzlich `->getById(`. Regel 11 lässt `#pii-admin` und `#pii-review` zu (die AVS-Regel nahm jede ID). Regel 1 bis 11 laufen auch ohne `php/css` und ohne Controller, weil diese erst später entstehen. Der AVS-Anti-Vakuum-Test auf ExAppService/FileAccess/Gateway ist durch "Application.php und Migration vorhanden" ersetzt; die volle Prüfung kommt in Plan 17.
- **Commit:** 3e82198

Kein UI-Text weicht vom UI-SPEC ab. Die Admin-Banner haben dort nur einen Satz je Zustand, der Katalog übernimmt das so.

## Known Stubs

Keine. Die Gates für Controller, Notifier, PublishService und CSS laufen auf leeren Mengen, bis die Pläne 04, 08, 11, 13 und 14 die Dateien anlegen. Das ist so gewollt; Plan 17 prüft die Vollständigkeit.

## Threat Flags

Keine neue Fläche. T-01-03-01 bis -06 sind mitigiert, jeweils mit Selbsttest.

## Self-Check: PASSED

- Dateien vorhanden: php/l10n/fr.json, php/l10n/de_DE.js, backend/tests/test_php_gates.py, backend/tests/test_log_calls.py
- Commits vorhanden: 132284d, 3e82198, 25f19ee
