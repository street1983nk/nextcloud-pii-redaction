---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 04
subsystem: php-services
tags: [recheck, download-block, appapi, exapp-state, handshake]
requires: [01-01]
provides:
  - "FileAccess (Dienst): recheck, recheckForStart, resolve, downloadBlocked; statisch readableFile/readableNode"
  - "ReaderContext::actAs (AVS-Kopie)"
  - "Model\\Recheck: ok, missing, download_blocked, changed"
  - "ExAppService: backendState(bool $fresh), startAllowed, status, page, output, proxyRequest(..., array $options)"
  - "HandshakeController: OCS GET /api/v1/handshake -> {version}"
affects: [01-08, 01-11, 01-12, 01-13, 01-14]
tech-stack:
  added: []
  patterns:
    - "Download-Sperre fail closed: hideDownload oder Attribut permissions/download === false oder Ausnahme"
    - "Ein Transport: proxyRequest mit ['timeout' => $t] + $options; Seite gepuffert und gedeckelt, Ausgabe als stream"
    - "Test-Trait ExAppServiceFactory doppelt nur exAppInfo und proxyRequest"
key-files:
  created:
    - php/lib/Service/FileAccess.php
    - php/lib/Service/ReaderContext.php
    - php/lib/Service/ExAppService.php
    - php/lib/Model/Recheck.php
    - php/lib/Controller/HandshakeController.php
    - php/tests/Unit/FileAccessTest.php
    - php/tests/Unit/BackendStateTest.php
    - php/tests/Unit/ExAppServiceTest.php
    - php/tests/Unit/ExAppServiceFactory.php
    - php/tests/Unit/HandshakeControllerTest.php
  modified: []
key-decisions:
  - "backendState(bool $fresh) prüft unter dem ersten aktiven Admin und merkt sich das Urteil 60 s; ohne Admin gilt no_app_api, also kein Start (fail closed)"
  - "Handshake antwortet {version} (SKELETON), nicht companionVersion wie AVS"
  - "status() liest version/ready/companion/busy/lastChild feldweise; lastChild.kind nur render, soffice, placeholder"
  - "Logkontext nur jobId, status, class, fileId (Gate-Regel 14); AVS-Schlüssel route, innerMs, error entfallen"
requirements-completed: []  # PLAT-02, PLAT-05, JOB-03 erst mit Controllern (Plan 08 bis 13) und CI-Lauf belegt
metrics:
  duration: "ca. 35 min"
  completed: 2026-11-07
  tasks: 3
  files: 10
---

# Phase 1 Plan 04: Recheck, Gegen-App-Zustände und Handshake Summary

Ob ein Nutzer eine Datei lesen darf, entscheidet jetzt nur noch `FileAccess::recheck`, und zwar bei jeder Anfrage: lesbar, keine Download-Sperre, gleicher Etag. Die Download-Sperre gilt im Zweifel (fail closed). `ExAppService` ist der einzige Weg zum Container: sieben Gegen-App-Zustände, `startAllowed`, Seitenbild als gedeckeltes PNG, Ausgabe als Strom. Der Handshake antwortet nur dem Backend.

## Ergebnis

- **Task 1 (`7a60237`):** `FileAccess` ist ein injizierbarer Dienst (`IRootFolder`, `ReaderContext`, Logger); die statischen Helfer bleiben statisch. `recheck` baut auf `recheckForStart` auf (lesbar, dann Sperre) und vergleicht danach den Etag. Jede Ausnahme ergibt `Missing` bzw. bei der Sperre `DownloadBlocked`. `FileAccessTest` hat 13 Fälle, darunter Ordner statt Datei, `getShare()` wirft und `getUserFolder` wirft.
- **Task 2 (`898f599`):** Die Zustandslogik ist aus AVS übernommen, die Suchteile sind weggelassen. `page` liest höchstens 16 MiB plus 1 Byte, auch aus einem Strom, und verlangt Status 200 und PNG-Magic. `output` fragt mit `['timeout' => 120.0, 'stream' => true]`. `BackendStateTest` hat 13 Testmethoden (davon eine mit 6 Datensätzen): alle sieben Zustände, Zwischenspeicher 60 s, `startAllowed` je Zustand und Companion, Feldprüfung von `/status`. `ExAppServiceTest` hat 10.
- **Task 3 (`31c21b4`):** Der AVS-Controller und sein Test sind mit neuen IDs übernommen. Die Antwort heißt `{version}`, der Satz der 403 und die Logzeile tragen das Präfix "PII Redaction".

Gates in `backend/`: ruff, ruff format --check, pyright 0 Fehler, vulture leer, pytest 205 passed (seriell). Damit laufen auch die PHP-Gates 1 bis 20 über die neuen Dateien: ein `exAppRequest(`, Knotensuche nur in FileAccess, kein `ViewOnly`/`shareapi_allow_view_without_download`, Logkontext erlaubt. phpunit läuft in CI (Plan 07).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2] Signatur backendState ohne uid**
- **Issue:** AVS nimmt `backendState(string $uid)`, die Plan-Schnittstelle verlangt `backendState(bool $fresh = false)` mit den Schlüsseln `state, ownVersion, backendVersion, checkedAt, companion`.
- **Fix:** Die Prüfung läuft unter `firstAdmin()`. Ohne aktiven Admin bleibt der Zustand `no_app_api`, also gibt es keinen Start (fail closed; AVS ließ die Suche in diesem Fall offen).
- **Commit:** 898f599

**2. [Rule 3] Gemeinsamer Test-Trait**
- **Fix:** `php/tests/Unit/ExAppServiceFactory.php` baut den Dienst für beide Testklassen. Die Datei endet nicht auf `Test.php` und wird darum von phpunit nicht als Testklasse geladen; der Autoloader findet sie über `autoload-dev`.
- **Commit:** 898f599

## Hinweise für spätere Pläne

- Plan 08 (Start) nutzt `recheckForStart` und danach `$file->getEtag()`/`getMimeType()`. Plan 12/13 nutzen `recheck(uid, fileId, etag)`.
- `ExAppService::status()` ohne uid fragt unter dem ersten Admin. Der Admin-Controller (Plan 11) kann den eigenen uid übergeben.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außer der geplanten OCS-Route `handshake` (T-01-04-04, mitigiert).

## Self-Check: PASSED

- Dateien vorhanden: php/lib/Service/FileAccess.php, php/lib/Service/ExAppService.php, php/lib/Controller/HandshakeController.php, php/lib/Model/Recheck.php, vier Testklassen und der Trait
- Commits vorhanden: 7a60237, 898f599, 31c21b4
