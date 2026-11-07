---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 13
subsystem: php-review
tags: [review-page, page-image, placeholder, recheck, initial-state]
requires: [01-04, 01-08, 01-09]
provides:
  - "ReviewController: GET /review/{jobId}, GET /review/{jobId}/page/{n}, POST /review/{jobId}/placeholder"
  - "templates/review.php: nur #pii-review"
  - "GET /api/v1/jobs/{jobId} trägt zusätzlich recheck"
  - "JobServiceFactory: $exApp, $pagePng, $pageCalls"
affects: [01-15, 01-16, 01-17]
tech-stack:
  added: []
  patterns:
    - "Jede Antwort der Bildroute mit private, no-store und nosniff, auch Fehler"
    - "Initialzustand state: job | blocked | unavailable; fileName nur nach bestandenem Recheck und nicht bei cancelled"
key-files:
  created:
    - php/lib/Controller/ReviewController.php
    - php/templates/review.php
    - php/tests/Unit/ReviewControllerTest.php
  modified:
    - php/lib/Controller/JobController.php
    - php/tests/Unit/JobControllerTest.php
    - php/tests/Unit/JobServiceFactory.php
    - php/src/ReviewPlaceholder.vue
    - .planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-SKELETON.md
key-decisions:
  - "Download-Sperre nach dem Laden der Seite: Status-Route meldet recheck, die Prüfseite wechselt dann (und bei 409 download_blocked des Platzhalters) in die Sperrkarte"
  - "cancelled(original_deleted) zeigt die Hinweiskarte mit 200 ohne Namen, obwohl der Recheck Missing ergibt; jeder andere Missing-Fall bleibt 404 'nicht verfügbar'"
  - "Platzhalter außerhalb von review: 409 mit {status}, nicht mit einem Grund aus der Liste"
requirements-completed: []  # PLAT-05, JOB-02/03/04 erst mit CI-PHPUnit und Playwright (Plan 16) belegt
metrics:
  duration: "ca. 30 min"
  completed: 2026-11-07
  tasks: 1
  files: 8
---

# Phase 1 Plan 13: Prüfseite auf der PHP-Seite Summary

Die Prüfseite hat jetzt ihre PHP-Hälfte: Template mit Initialzustand, Seitenbild-Proxy mit Recheck bei jeder Anfrage und die Aktion "Platzhalter-Kopie anlegen". Eine nachträgliche Download-Sperre erreicht die geöffnete Seite jetzt auch über die Status-Abfrage.

## Ergebnis

- **Task 1 (`8345436`):** `ReviewController` mit drei `FrontpageRoute`-Methoden, jede ruft zuerst `recheckMember`.
  - `page`: 404 mit `{state: 'unavailable'}` und Titel "Prüfung" für fremd, unbekannt und unlesbar. Sonst Initialzustand mit den UI-SPEC-Feldern plus `recheck`, `fileName` nur nach bestandenem Recheck, `image` nur in `review` ohne Sperre, Zustand `blocked` bei Sperre. `cancelled(original_deleted)` zeigt 200 ohne Namen. Beim Öffnen `NotificationSender::dismiss`. Skript `pii_redaction-review`, Stil `review`, Seitentitel über `pageTitle` (AVS-Weg) "Prüfung: {Name}" bzw. "Prüfung".
  - `pageImage`: Missing 404, Changed 409 (Auftrag wird stale), Sperre 403, nicht `review` oder `n != 1` 404, kein PNG aus dem Container 502, sonst `image/png`. Alle Antworten mit `Cache-Control: private, no-store` und `X-Content-Type-Options: nosniff`.
  - `placeholder` (POST mit CSRF): Changed 409 `original_changed`, Sperre 409 `download_blocked`, nicht `review` 409 `{status}`, Backend nicht bereit 409 `backend_unavailable`, sonst `toApproved` plus Ereignis `placeholder_requested`, 202 `{status: 'approved'}`.
  - `templates/review.php`: nur `<div id="pii-review" class="pii-review"></div>`.
  - `ReviewControllerTest`: 19 Tests.
- **Nachtrag (`ebebb4d`):** Status-Route meldet `recheck`, `ReviewPlaceholder.vue` wechselt bei `download_blocked` in die Sperrkarte, auch nach einem 409 des Platzhalters; bei `original_changed` fragt sie sofort den Status ab. Neuer Test in `JobControllerTest`, SKELETON-Zeile ergänzt.

Gates in `backend/` vor jedem Commit: ruff, ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 413 passed / 3 skipped; `npm run typecheck` und `npm run build` grün. Akzeptanz-greps: `FrontpageRoute` 3, `recheckMember(` 3, `nosniff` und `no-store` vorhanden, `<script` im Template 0, 19 Testmethoden.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2] Download-Sperre nach dem Laden (Hinweis aus 01-09)**
- **Issue:** Die Status-Route meldete keine Sperre; ein Bildfehler zeigte dann nur "Seite nicht abrufbar", erst ein Neuladen die Sperrkarte (UI-SPEC verlangt den Wechsel).
- **Fix:** Feld `recheck` in `GET /api/v1/jobs/{jobId}` (aus `JobService::view`, gab es schon), Auswertung in der Vue-Komponente, SKELETON angepasst.
- **Commit:** ebebb4d

**2. [Rule 1] Gelöschtes Original hätte 404 ergeben**
- **Issue:** Nach dem Löschen ergibt der Recheck immer Missing, die UI-SPEC verlangt für `cancelled(original_deleted)` aber 200 mit Hinweiskarte ohne Namen.
- **Fix:** Bei Missing prüft `page` den Auftrag des Aufrufers auf genau diesen Zustand; alles andere bleibt 404.
- **Commit:** 8345436

**3. [Rule 3] Test-Trait um `page()` ergänzt**
- **Fix:** `$exApp` als Eigenschaft, `page()` liefert `$pagePng` und merkt sich die Aufrufe.
- **Commit:** 8345436

## Known Stubs

Keine. Die Prüfseite zeigt bewusst "Vorschau ohne Erkennung" (Owner-Entscheid Phase 1).

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-13-01 bis -07 mitigiert (recheckMember je Anfrage mit einheitlichem 404, kein gespeichertes Recht, 403 bei Sperre, private no-store, nosniff plus PNG-Magic in ExAppService, POST mit CSRF, Template ohne Nutzerdaten).

## Self-Check: PASSED

- Dateien vorhanden: php/lib/Controller/ReviewController.php, php/templates/review.php, php/tests/Unit/ReviewControllerTest.php
- Commits vorhanden: 8345436, ebebb4d
