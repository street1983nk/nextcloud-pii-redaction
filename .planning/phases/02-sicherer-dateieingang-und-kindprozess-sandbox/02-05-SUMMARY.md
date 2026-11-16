---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 05
subsystem: model
tags: [closed-lists, lockstep, job-05, php, python]
requires: [02-04]
provides: [Reason e2e_encrypted..signature_declined, Status confirm (offen), AckResult confirm, Stage checking, JobEventMapper-Aktionen]
affects: [02-11, 02-15, 02-18, 02-19]
tech-stack:
  added: []
  patterns: [Wörter nur am Listenende anhängen, Lockstep Python/PHP/Playwright im selben Commit]
key-files:
  created: []
  modified:
    - backend/src/pii_redaction_backend/model.py
    - php/lib/Model/Reason.php
    - php/lib/Model/Status.php
    - php/lib/Model/Stage.php
    - php/lib/Controller/QueueController.php
    - php/lib/Db/JobEventMapper.php
    - php/tests/Unit/ModelTest.php
    - php/tests/Unit/QueueControllerTest.php
    - backend/tests/test_model.py
    - backend/tests/test_php_schema.py
    - backend/tests/test_playwright_contract.py
    - ci/playwright/helpers.ts
decisions:
  - "ack mit result confirm antwortet bis 02-15 mit 400; der match in QueueController::ack hat jetzt einen expliziten purged-Arm, default ist 400"
  - "Stage checking steht zwischen fetching und converting; Status confirm am Listenende, in isOpen()"
metrics:
  completed: 2026-11-16
  tasks: "2/2"
---

# Phase 2 Plan 05: Geschlossene Listen Summary

Neue Wörter im Gleichschritt in Python, PHP und den Playwright-Helfern: sieben Ablehnungsgründe, Status/AckResult `confirm`, Stage `checking`, fünf Protokoll-Aktionen; alle in den Spaltenlängen (längstes Wort `owner_protection_dropped`, 24 Zeichen).

## Commits

| Task | Commit |
|---|---|
| 1 Enums, Lockstep, ack-Absicherung | 5361313 |
| 2 JobEventMapper-Aktionen, Längen-Gate | 52a61c8 |

## Prüfung

Suite 628 passed, 7 skipped; ruff, pyright, vulture grün. Zusatztest: jedes Verdict aus intake.verdict außer ok ist ein Reason-Wert (02-04 lag schon vor, kein Skip nötig). PHPUnit (ModelTest, QueueControllerTest) läuft erst in php.yml beim Push 02-16, lokal kein PHP.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] confirm wäre im ack auf den Purge-Zweig gefallen**
- Found during: Task 1
- Issue: `match ($result)` in QueueController::ack hatte `default => ackPurged`. Mit 'confirm' in RESULTS hätte ein confirm-ack den Auftrag beendet und gelöscht.
- Fix: expliziter Arm `'purged' => ackPurged`, `default => badRequest()`; PHPUnit-Fall testAConfirmIsNotYetHandledAndNeverPurges (Status bleibt analyzing, Task analyze).
- Commit: 5361313

**2. [Rule 3 - Blocking] Playwright-Helfer spiegeln die Listen**
- ci/playwright/helpers.ts (STATUSES, STAGES, REASONS) und der Selbsttest in test_playwright_contract.py mussten mitziehen, sonst rot.
- Commit: 5361313

- PHPUnit-Fall für isAllowedAction liegt in php/tests/Unit/ModelTest.php (kein eigener Mapper-Test vorhanden).

## Known Stubs

- Frontend kennt `confirm` noch nicht (ReviewPlaceholder.vue fällt in den default-Zweig); die Karte kommt in 02-18.

## Self-Check: PASSED
