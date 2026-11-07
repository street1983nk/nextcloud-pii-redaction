---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 08
subsystem: php-jobs
tags: [job-service, etag, notification, controller, idempotence]
requires: [01-02, 01-04, 01-07]
provides:
  - "JobService: start, view, forMember, recheckMember, toReview, toFailed, toStale, toCancelled, toApproved, toVerified, toPublished, toPurged"
  - "NotificationSender: notify(job, Subject), dismiss(job)"
  - "JobController: POST /api/v1/jobs, GET /api/v1/jobs/{jobId}"
  - "Test-Trait JobServiceFactory (echte CI-DB, Dateibaum/Backend/Sprache/Benachrichtigung gedoppelt)"
affects: [01-12, 01-13, 01-14, 01-16]
tech-stack:
  added: []
  patterns:
    - "Jede Zustandsänderung über JobService: Statusprüfung, updated_at aus ITimeFactory, Ereignis, Lease-Freigabe, Benachrichtigung, purge nach Endzustand"
    - "404 ohne Körper für fremd, unbekannt und unlesbar (nicht unterscheidbar)"
    - "Benachrichtigung ist Komfort: Fehler nur mit Klasse geloggt, Übergang läuft weiter"
key-files:
  created:
    - php/lib/Service/JobService.php
    - php/lib/Service/NotificationSender.php
    - php/lib/Controller/JobController.php
    - php/tests/Unit/JobServiceFactory.php
    - php/tests/Unit/JobServiceTest.php
    - php/tests/Unit/EtagBindingTest.php
    - php/tests/Unit/JobControllerTest.php
  modified: []
key-decisions:
  - "Erster Leser eines vom Mapper aufgegebenen Auftrags (failed/repeatedly_stuck) schreibt das Ereignis failed und sendet job_failed genau einmal (Hinweis aus 01-02)"
  - "toPurged schreibt kein Ereignis: 'purged' steht in keiner geschlossenen Liste der Ereignistabelle"
  - "toCancelled entfernt alte Benachrichtigungen des Auftrags (dismiss), sendet aber keine neue"
  - "Etag leer oder länger als 40 Zeichen ergibt not_readable beim Start (Spalte und Container-Vertrag)"
requirements-completed: []  # JOB-01/03/04/06 erst mit Dateiaktion (09), Container (10), CI-PHPUnit und Playwright belegt
metrics:
  duration: "ca. 30 min"
  completed: 2026-11-07
  tasks: 2
  files: 7
---

# Phase 1 Plan 08: Start, Status und Zustandsübergänge Summary

Start und Status eines Auftrags sind jetzt rechte- und etaggebunden: `POST /api/v1/jobs` prüft als der Nutzer (lesbar, keine Download-Sperre, PDF/DOCX/ODT, Backend bereit), legt idempotent an und meldet die echte Position; `GET /api/v1/jobs/{jobId}` zeigt nur dem Auftraggeber Codes und Zähler und macht einen offenen Auftrag bei geändertem Etag sofort `stale(original_changed)`. Alle Übergänge laufen über `JobService`.

## Ergebnis

- **Task 1 (`e6c9b19`):** `JobService::start` prüft in der Reihenfolge Backend, Recheck, Mime, Etag und sucht dann in einer Transaktion den offenen Auftrag (gleiche Datei, gleicher Etag, gleicher Nutzer), sonst `enqueue` mit `Mode::Redact` und Sprache aus `IL10NFactory::getUserLanguage`. Gespeichert werden nur IDs, Etag, Modus, Sprache. Acht Übergänge mit Ausgangszustand-Prüfung (`\LogicException` mit statischem Text), Lease-Freigabe über das Claim-Token, Ereignis und Benachrichtigung laut SKELETON (`review_ready`, `job_failed`, `job_stale`, `copy_created`, keine bei `cancelled`). `NotificationSender` setzt App, Nutzer, Objekt `('job', id)`, Betreff ohne Parameter und Zeit; vor jedem `notify` ein `dismiss`. Tests: `JobServiceTest` 18, `EtagBindingTest` 6.
- **Task 2 (`664c95f`):** `JobController::create` ruft `recheckForStart` und reicht das Ergebnis an `start` (keine doppelte Prüfung); 201 neu, 200 offen, 503/403/404/415 mit `{reason}`. `show` ruft `recheckMember`, dann `view` mit dem schon bekannten Urteil; Antwort nur mit den SKELETON-Feldern. Alle Antworten `Cache-Control: private, no-store`; 404 ohne Körper. `JobControllerTest` 11 Tests.

Gates in `backend/` vor jedem Commit: ruff (inkl. `../scripts`), ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 361 passed / 3 skipped. PHP-Gates 1 bis 20 grün (Gate 12 sieht `recheckForStart(` und `recheckMember(`). PHP lokal nur statisch; PHPUnit läuft nach dem nächsten Owner-freigegebenen Push in CI.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3] `IUserManager` im Konstruktor von JobService**
- **Issue:** `getUserLanguage` braucht ein `IUser`, der Plan nennt nur die uid.
- **Fix:** zusätzlicher Konstruktorparameter `IUserManager`.
- **Commit:** e6c9b19

**2. [Rule 2] `view(..., ?Recheck $known = null)`**
- **Issue:** Der Controller ruft laut Plan erst `recheckMember`, dann `view`; ohne Parameter liefe der Recheck doppelt.
- **Fix:** optionales Urteil; ohne Parameter prüft `view` selbst.
- **Commit:** e6c9b19

**3. [Rule 2] Benachrichtigung für vom Mapper aufgegebene Aufträge**
- **Issue:** `JobMapper::giveUp` setzt `failed(repeatedly_stuck)` ohne Benachrichtigung (Hinweis 01-02).
- **Fix:** `view` holt Ereignis und `job_failed` genau einmal nach (Test).
- **Commit:** e6c9b19

**4. [Rule 2] Etag-Länge beim Start geprüft**
- **Issue:** Spalte und Container-Vertrag erlauben höchstens 40 Zeichen; ein längerer Etag ließe jeden Download scheitern.
- **Fix:** leer oder über 40 Zeichen ergibt `not_readable`.
- **Commit:** e6c9b19

**5. [Rule 3] Test-Trait `JobServiceFactory`**
- **Issue:** `JobService`, `JobMapper` und `FileAccess` sind `final` und lassen sich nicht doppeln.
- **Fix:** echte Dienste gegen die CI-Datenbank (wie `QueueMapperTest`), gedoppelt nur Dateibaum, `ExAppService::startAllowed`, Sprache und `IManager`.
- **Commit:** e6c9b19

Kleinere Ergänzungen: `view` liefert zusätzlich `fileId`, `createdAt`, `image` und `outputName` für Plan 13; `toVerified`/`toPublished` prüfen sha256-Form, Größe und Datei-ID; `create` und `show` antworten ohne Sitzung selbst mit 401.

## Hinweise für spätere Pläne

- **Plan 12 (QueueController):** `toReview`, `toFailed`, `toVerified`, `toPurged` geben den Lease mit dem im Entity stehenden Claim-Token frei; der Controller muss den Auftrag mit dem Token des Containers laden (oder vorher vergleichen).
- **Plan 13:** `reviewUrl` nutzt die Route `pii_redaction.review.page` (Methode `page` im `ReviewController`).
- **Plan 14 (Notifier):** Objekt `job`, Betreff = `Subject`-Wert, keine Parameter.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-08-01 bis -07 mitigiert (Recheck als Nutzer, einheitliches 404, `download_blocked` fail closed, Etag-Bindung, CSRF an, no-store, Idempotenz in Transaktion).

## Self-Check: PASSED

- Dateien vorhanden: JobService.php, NotificationSender.php, JobController.php, vier Testdateien
- Commits vorhanden: e6c9b19, 664c95f
