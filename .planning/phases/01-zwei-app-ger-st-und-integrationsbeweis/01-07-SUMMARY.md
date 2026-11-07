---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 07
subsystem: ci
tags: [push, ci, phpunit, posix, deploy-harp]
status: wartet-auf-owner
requires: [01-02, 01-03, 01-04, 01-05, 01-06]
provides:
  - "origin/phase-01 auf ec50bef (Stand nach Welle 3), main auf GitHub unverändert (1f95af7)"
  - "python.yml grün auf Linux inklusive POSIX-Tests (364 passed)"
  - "lokal vorbereitete Korrekturen 8f06c86 (01-02) und ad2c4b8 (01-01), NICHT gepusht"
affects: [01-02, 01-01, 01-08]
key-files:
  created: []
  modified:
    - php/lib/Migration/Version000100Date20261107000000.php
    - php/lib/Db/JobMapper.php
    - .github/workflows/deploy-harp.yml
decisions:
  - "expires_at bekommt Datenbank-Default 0 wie lease_until und attempts (Produkt-Fix in der Migration statt Test-Anpassung)"
  - "deploy-harp: sqlite3 mit Busy-Timeout 15 s statt sofortigem Abbruch bei Schreibsperre"
metrics:
  completed: 2026-11-07
  tasks: "Task 1 und 2 erledigt, Task 3 wartet auf Owner-Freigabe"
---

# Phase 1 Plan 07: Früher Push auf phase-01 Summary

Stand nach Welle 3 liegt auf `phase-01`; Python-Gates grün, PHPUnit rot wegen fehlendem Datenbank-Default für `expires_at` (Korrektur lokal fertig, wartet auf Owner-Freigabe für den zweiten Push).

## Task 1: Prüfungen vor dem Push

- Owner-Freigabe 07.11.: "Ja, auf phase-01 pushen" (genau ein Push).
- 49 Commits vor origin/main, Autor und Committer ausschließlich `street1983nk <k.cherif@outlook.de>`.
- Zähler verbotener Zeilen (Claude-Session, Co-Authored-By, closes/fixes/resolves #N): 0.
- Workflows auf `runner`-Kontext in workflow-/job-level `env` geprüft: nur in Steps von docker.yml (läuft auf phase-01 nicht), kein Befund.
- Lokale Gates: ruff check grün, ruff format 48 Dateien ok, pyright 0 Fehler, vulture grün, pytest 361 passed / 3 skipped (POSIX), test_public_artifacts.py 4 passed, Diff-Scan auf Schlüssel/Token ohne Treffer.
- origin hatte vorher keinen Branch phase-01.

## Task 2: Push und CI

`git push origin main:phase-01` einmal, ohne --force: `* [new branch] main -> phase-01`, HEAD ec50bef. `git ls-remote` danach: main 1f95af7 (unverändert), phase-01 ec50bef.

| Workflow | Job | Ergebnis | Dauer | URL |
|---|---|---|---|---|
| Python gates | ruff, format, pyright, vulture, pytest, shellcheck | success (364 passed, POSIX-Tests liefen) | 27 s | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377238300/job/128417251782 |
| PHP gates | php -l | success | 7 s | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377237827/job/128417250761 |
| PHP gates | composer validate and audit | success | 8 s | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377237827/job/128417250949 |
| PHP gates | PHPUnit over the PHP app | **failure** | 32 s | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377237827/job/128417250492 |
| Deploy through HaRP | stable33 | success | 2:00 | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377237730/job/128417251132 |
| Deploy through HaRP | stable34 | success | 2:00 | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377237730/job/128417251621 |
| Deploy through HaRP | stable35 | failure (nur Information) | 2:09 | https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/42377237730/job/128417250914 |

### Rot 1: PHPUnit (Plan 01-02)

Logbeleg: `Tests: 80, Assertions: 292, Errors: 13.`; alle 13 Fehler in `QueueMapperTest` mit
`SQLSTATE[23000]: Integrity constraint violation: 19 NOT NULL constraint failed: oc_pii_jobs.expires_at`, Aufrufstelle `apps/pii_redaction/lib/Db/JobMapper.php:85` (insert in `enqueue`).

Ursache (belegt am Server-Quelltext stable34, `lib/public/AppFramework/Db/Entity.php:95`): `if ($args[0] === $this->$name) { return; }` markiert das Feld nicht als geändert, wenn der Wert dem Property-Default gleicht. `Job::$expiresAt` ist mit `0` vorbelegt, `setExpiresAt(0)` fällt also aus dem INSERT. `lease_until` und `attempts` haben in der Migration `default => 0`, `expires_at` nicht, daher nur diese Spalte.

Korrektur lokal, Commit `8f06c86` `fix(01-02): expires_at bekommt Datenbank-Default 0`: Migration `expires_at` mit `'default' => 0` und erklärendem Kommentar; Kommentar in `JobMapper::enqueue` richtiggestellt. Test unverändert. Die Migration ist noch nirgends ausgeliefert (nur CI-Instanzen), Änderung in place ist daher unbedenklich. Lokal kein PHP/Docker-Daemon, PHPUnit-Nachweis steht erst nach dem nächsten Push.

### Rot 2: deploy-harp stable35 (Skeleton-Schritt, Plan 01-01)

Logbeleg im Schritt "The settings form is registered and no browser route reaches the container": `Error: in prepare, database is locked (5)` aus `sqlite3 data/owncloud.db "SELECT ... FROM oc_ex_settings_forms"`. stable33 und stable34 grün mit demselben Schritt: Wettlauf mit einer Schreibsperre des laufenden Servers, kein App-Fehler. deploy-harp ist in diesem Stand kein Gate.

Korrektur lokal, Commit `ad2c4b8` `fix(01-01): sqlite3-Abfrage in deploy-harp wartet auf Schreibsperre`: `sqlite3 -cmd '.timeout 15000'`.

## Task 3: Korrekturschleife

Stand: **wartet auf Owner-Freigabe** für genau einen weiteren Push `git push origin main:phase-01` (ec50bef..ad2c4b8, fast-forward, 2 Commits). Kein zweiter Push ohne neue Freigabe. Beide Commits als street1983nk, ohne verbotene Zeilen (Zähler 0); lokale Gates nach den Korrekturen: pytest 361 passed / 3 skipped.

## Deviations from Plan

- deploy-harp-Korrektur ist keine Pflicht des Plans (nur Information), aber billig und verhindert Fehlalarme; als eigener Commit mit Plan-Bezug 01-01.

## Self-Check: PASSED

- FOUND: 8f06c86, ad2c4b8 (lokal), ec50bef (origin/phase-01)
- FOUND: php/lib/Migration/Version000100Date20261107000000.php, php/lib/Db/JobMapper.php, .github/workflows/deploy-harp.yml
