---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 11
subsystem: php-jobs
tags: [job-05, e2e, signature, events]
requires: [02-05]
provides: [FileAccess::inE2eFolder, JobService::toConfirm/confirmSignature/declineSignature/recordAckFlags, JobEventMapper::hasAction, view macrosRemoved/signatureConfirmed]
affects: [02-15, 02-18, 02-20]
key-files:
  modified:
    - php/lib/Service/FileAccess.php
    - php/lib/Service/JobService.php
    - php/lib/Db/JobEventMapper.php
    - php/tests/Unit/FileAccessTest.php
    - php/tests/Unit/JobServiceTest.php
    - php/tests/Unit/JobServiceFactory.php
    - backend/tests/test_php_gates.py
decisions:
  - "E2E-Prüfung über Node::isEncrypted() am Ordner (Node erweitert FileInfo); getFileInfo() gibt es an Node nicht"
  - "Abbruch des Aufstiegs bei Pfad /<uid>/files, '/' oder leer; mehr als 256 Ebenen oder jede Ausnahme gilt als E2E (fail closed)"
  - "confirmSignature und declineSignature verlangen den Auftraggeber (expectInitiator), zusätzlich zur Rechteprüfung der Controller"
  - "toConfirm schreibt das Status-Event confirm (über finish) plus signature_notice; confirmSignature schreibt signature_confirmed vor dem Status-Event queued"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 11: E2E-Ablehnung und Signatur-Bestätigung (PHP) Summary

`FileAccess::inE2eFolder` lehnt Dateien unter einem E2E-Ordner ab (SSE-Datei nicht, Ausnahme = fail closed), `JobService` bekommt die blockierende Signatur-Bestätigung als Zustandsfolge analyzing -> confirm -> queued bzw. cancelled(signature_declined) ohne Benachrichtigung, `recordAckFlags` und `hasAction` liefern Makro-Hinweis und Bestätigung in `view()`; ein Python-Gate hält fest, dass Events nur zusammen mit ihrem Auftrag gelöscht werden dürfen.

## Commits

| Schritt | Commit |
|---|---|
| Task 1 Tests | f885e3b |
| Task 1 Umsetzung | 2f22050 |
| Task 2 Tests und Gate | 5203a6f |
| Task 2 Umsetzung | 382ea12 |

## Prüfung

- Suite 931 passed, 14 skipped; PHP-Gates (inkl. neues Event-Gate mit Selbsttest: deleteOlderThan feuert, deleteForJob nicht, vier fremde Löschwege feuern), ruff, pyright, vulture grün.
- PHPUnit-Fälle (E2E am Elternordner und höher, SSE-Datei, Positivkontrolle ohne Flag, Stopp am Benutzerordner, Ausnahme, Endloskette; Start mit e2e_encrypted ohne Benachrichtigung; alle Bestätigungsübergänge, Bestätigung bleibt über review/approved sichtbar, Ack-Flags, hasAction gegen Fremdwort) laufen erst in php.yml nach dem Push-Tor 02-16. Lokal kein PHP: Syntax nur durch Lesen geprüft.

## Deviations from Plan

- [Rule 2] Initiator-Prüfung auch in confirmSignature (Plan nannte sie nur implizit über das Muster).
- JobServiceFactory (Testhelfer) erweitert um Ordner-Flag, Datei-Flag und Pfade der Elternordner; Datei war nicht in files_modified.
- `getFileInfo()->isEncrypted()` aus dem Plan durch `isEncrypted()` am Ordnerknoten ersetzt (OCP Node erweitert FileInfo).

## Threat Flags

Keine.

## Self-Check: PASSED
