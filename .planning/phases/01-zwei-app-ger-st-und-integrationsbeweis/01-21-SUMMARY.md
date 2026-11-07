---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 21
subsystem: ci
tags: [push, phase-01, phpunit, ci]
requires: [01-08, 01-09, 01-10, 01-11, 01-12, 01-13, 01-14]
provides: [CI-Beleg für Wellen 5 und 6 auf phase-01]
affects: [01-15, 01-16, 01-17]
tech-stack:
  added: []
  patterns: []
key-files:
  created: [.planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-21-SUMMARY.md]
  modified: []
decisions:
  - "Zweiter früher Push auf phase-01 grün im ersten Lauf, keine Korrekturrunde nötig (234 PHPUnit-Tests)"
metrics:
  completed: 2026-11-07
  tasks: "3/3, ein Push mit Owner-Freigabe, Korrekturschleife nicht nötig"
---

# Phase 1 Plan 21: Zweiter früher Push auf phase-01 Summary

Stand nach Welle 6 (Queue, Gateway, Prüfseite, Benachrichtigung, Ablage, Lebenszyklus) liegt auf `phase-01`; python.yml, php.yml und deploy-harp stable33/34/35 sind auf 5a977f6 im ersten Lauf grün, PHPUnit mit 234 Tests.

## Task 1: Prüfungen vor dem Push

- Owner-Freigabe 07.11. im Claude-Code-Terminal: "Ja, auf phase-01 pushen" (genau ein Push).
- HEAD 5a977f6, lokaler Branch main, Arbeitsbaum sauber, origin/phase-01 auf 3fb9706, nichts hinter origin (fast-forward).
- 11 Commits voraus, ab 5722ebe (docs 01-09, nach dem letzten Push lokal entstanden) bis 5a977f6. Die Freigabefrage nannte 10 Commits; der elfte ist 5722ebe selbst, reine SUMMARY-Änderung (14 Zeilen), von der Freigabe "ab 5722ebe" gedeckt.
- Autor und Committer ausschließlich `street1983nk <k.cherif@outlook.de>`; Zähler verbotener Zeilen (Claude-Session, Co-Authored-By, closes/fixes/resolves #N): 0.
- `runner`-Kontext nur in Steps von docker.yml, nicht in Workflow-/Job-`env`.
- Lokale Gates: ruff check grün, ruff format 57 Dateien ok, pyright 0 Fehler, vulture grün, pytest 413 passed / 3 skipped (Windows, POSIX-Tests übersprungen), test_public_artifacts.py 4 passed, `npm ci --ignore-scripts`, `npm run typecheck`, `npm run build` grün. Diff-Scan auf Schlüssel/Token ohne Treffer.
- Remote vorher: main 1f95af7, phase-01 3fb9706.

## Task 2: Push und CI

`git push origin main:phase-01` einmal, ohne --force: `3fb9706..5a977f6  main -> phase-01`. `git ls-remote` danach: main 1f95af7 (unverändert), phase-01 5a977f6.

| Workflow | Job | Ergebnis | Dauer | Auszug | URL |
|---|---|---|---|---|---|
| PHP gates | PHPUnit over the PHP app | success | 48 s | `OK (234 tests, 1946 assertions)`, `the suite executed 234 tests` | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127692/job/128437817687 |
| PHP gates | php -l (mit tsc und Build) | success | 25 s | `> tsc --noEmit -p tsconfig.json`, `built in 4.00s` | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127692/job/128437817818 |
| PHP gates | composer validate and audit | success | 11 s | | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127692/job/128437817546 |
| Python gates | ruff, format, pyright, vulture, pytest, shellcheck | success | 32 s | `All checks passed!`, `416 passed in 8.02s` (inkl. POSIX) | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127667/job/128437817553 |
| Deploy through HaRP | stable33 | success | 1:52 | `registered forms: pii_redaction_backend:pii_redaction_backend_admin`, `unsigned /status: anonymous 404, admin login 404` | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127652/job/128437817810 |
| Deploy through HaRP | stable34 | success | 1:47 | wie stable33 | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127652/job/128437817608 |
| Deploy through HaRP | stable35 | success | 1:56 | wie stable33 | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42384127652/job/128437817936 |

PHPUnit: 234 Tests statt 132 beim letzten Push, also 102 neue (QueueController, GatewayController, ReviewController, Notifier, Suffix, PublishService, FileLifecycleListener).

Hinweis (kein Fehler): Der Build im PHPUnit-Job meldet `[WARNING] Cannot find base config file "@vue/tsconfig/tsconfig.json"`, weil der Build im nextcloud/server-Baum läuft; der Build ist grün, die Typprüfung läuft im Lint-Job. Beobachten in Plan 15.

## Task 3: Korrekturschleife

Nicht nötig, Task 2 war im ersten Lauf grün (Option "not-needed").

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

Keine.

## Threat Flags

Keine. T-01-21-01 bis -03 mitigiert (Owner-Freigabe, test_public_artifacts.py und Diff-Scan vorher, Ziel nur `main:phase-01`, kein --force, main unverändert 1f95af7).

## Self-Check: PASSED

- Commit 5a977f6 auf origin/phase-01 (ls-remote), main 1f95af7 unverändert.
- Runs 42384127692, 42384127667, 42384127652 alle success.
