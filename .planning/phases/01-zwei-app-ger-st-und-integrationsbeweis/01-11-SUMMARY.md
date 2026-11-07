---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 11
subsystem: php-admin
tags: [admin-section, banner, apps-link, settings-controller]
requires: [01-04, 01-07, 01-09]
provides:
  - "Settings\\Section (pii_redaction, Priorität 75, app-dark.svg) und Settings\\Admin (Formular, RENDER_AS_BLANK)"
  - "templates/admin.php: sieben Banner mit data-state, Warnbanner Neuprüfung, Versionszeile, Prüfzeit, Knopf"
  - "css/admin.css: pii-banner-Regeln und Admin-Zusätze"
  - "GET /apps/pii_redaction/admin/state (nur Admins)"
  - "info.xml: <settings> mit Admin und Section"
affects: [01-16, 01-17]
tech-stack:
  added: []
  patterns:
    - "Apps-Link in AVS-Form: appstore.page.viewApps, bei leerem String settings.AppSettings.viewApps (Template und Controller gleich)"
    - "Template-Test in PHPUnit: Datei mit $_ und gedoppeltem $l einbinden, per DOMXPath prüfen"
key-files:
  created:
    - php/lib/Settings/Section.php
    - php/lib/Settings/Admin.php
    - php/lib/Controller/SettingsController.php
    - php/templates/admin.php
    - php/css/admin.css
    - php/tests/Unit/AdminSettingsTest.php
    - php/tests/Unit/SettingsControllerTest.php
  modified:
    - php/appinfo/info.xml
    - backend/tests/test_ui_assets.py
    - .planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-UI-SPEC.md
key-decisions:
  - "Das Admin-Formular reicht seinen IURLGenerator als Template-Parameter weiter; das Template fällt nur ohne ihn auf Server::get zurück (testbar ohne laufenden Server)"
  - "admin/state fragt /status (lastChild) nur in den Zuständen ok und version_patch_differs; sonst kein zweiter Aufruf mit Zeitgrenze"
requirements-completed: []  # PLAT-02 erst mit Playwright in den Fehlerzuständen auf NC 33 bis 35 belegt (Plan 16)
metrics:
  duration: "ca. 25 min"
  completed: 2026-11-07
  tasks: 2
  files: 10
---

# Phase 1 Plan 11: Admin-Statusbereich Summary

Der Admin sieht jetzt in der eigenen Sektion "PII Redaction" genau ein Banner für den Zustand der Gegen-App, die Versionen beider Apps und den Zeitpunkt der letzten Prüfung. In den fünf Fehlerzuständen steht "Apps öffnen" in der CI-erprobten AVS-Form. "Erneut prüfen" fragt über eine reine Admin-Route frisch ab.

## Ergebnis

- **Task 1 (`c770fb9`):** `Section` und `Admin` aus AVS mit neuen IDs und ohne Debug-Block. Das Template rendert alle sieben Banner serverseitig (aktuelles sichtbar, Rest `hidden`) plus das versteckte Warnbanner für eine gescheiterte Neuprüfung, Versionszeile und Prüfzeit über Platzhalter-Spans, Knopf `#pii-recheck` mit `#pii-recheck-label`. Das passt zum DOM-Vertrag aus `src/admin.ts` (Plan 09). Alle Texte über `$l->t()` mit vorhandenen Katalogschlüsseln, alle Werte über `p()`. `info.xml` trägt den `<settings>`-Block. In der UI-SPEC sind beide Sätze zur Link-Auswahl auf Orchestrator-Entscheid 3 umgestellt. `AdminSettingsTest` (8 Methoden, eine mit 5 Datensätzen): Link in jedem Fehlerzustand, keiner in `ok`/`version_patch_differs`, Rückfall bei leerem `linkToRoute`, nur ein Banner sichtbar, unbekannter Zustand wird `backend_unreachable`, Formularparameter, Ausnahmeweg, Section-Werte. `test_ui_assets.py` hat zusätzlich einen Vertragstest für Template und CSS.
- **Task 2 (`ea60de1`):** `SettingsController::state` mit `FrontpageRoute` und sonst keinem Attribut, Antwort `backendState(true)` plus `checkedAtText`, `lastChild`, `appsUrl`; Ausnahme ergibt 503 `{state: 'recheck_failed'}`, Log nur mit `class`. `SettingsControllerTest` (5 Tests) mit Reflection-Prüfung.

Gates in `backend/` vor jedem Commit: ruff, ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 413 passed / 3 skipped. PHP lokal nur statisch (Gates 1 bis 20, `test_ui_assets.py`); PHPUnit in CI nach dem nächsten Owner-freigegebenen Push.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3] URL-Generator als Template-Parameter**
- **Issue:** AVS holt den Generator im Template über `\OCP\Server::get`; damit ließe sich der Rückfall in PHPUnit nicht prüfen.
- **Fix:** `Admin::getForm()` übergibt seinen `IURLGenerator`; das Template nutzt `Server::get` nur, wenn der Parameter fehlt. Die beiden `linkToRoute`-Aufrufe stehen weiter genau einmal im Template.
- **Commit:** c770fb9

**2. Antwortfelder von admin/state**
- Statt AVS-Feldnamen `own`/`backend` die Schlüssel aus `backendState` (`ownVersion`, `backendVersion`), so wie `src/admin.ts` sie liest; zusätzlich `companion`.

Keine weiteren Abweichungen.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-11-01 bis -03 mitigiert (kein lockerndes Attribut plus Reflection-Test, nur Zustand und Versionen, Ausgabe über `p()` ohne Inline-Skript mit Gate).

## Self-Check: PASSED

- Dateien vorhanden: php/lib/Settings/{Section,Admin}.php, php/lib/Controller/SettingsController.php, php/templates/admin.php, php/css/admin.css, zwei Testklassen
- Commits vorhanden: c770fb9, ea60de1
