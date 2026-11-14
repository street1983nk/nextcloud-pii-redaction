---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 16
subsystem: ci
tags: [playwright, ui-spec, screenshots, acceptance]
requires: [01-09, 01-11, 01-13, 01-14, 01-15, 01-21]
provides: [Abnahme-Suite ci/playwright mit 12 Projekten, Vertragstest test_playwright_contract.py]
affects: [01-17, 01-18, 01-20]
tech-stack:
  added: ["@playwright/test 1.65.0 (exakt, Lock)", "typescript 6.0.3 (exakt, wie php/)"]
  patterns:
    - "Screenshot-Name <projekt>__<fläche>__<zustand>.png über einen Helfer mit Bereitschaftsprüfung"
    - "Gefälschte Zustände: echte Prüfseite holen, nur Felder des Startzustands gegen Werte der geschlossenen Liste tauschen"
    - "Echte Server-Antworten für Toasts durch Umschreiben der fileId im Start-POST"
key-files:
  created:
    - ci/playwright/package.json
    - ci/playwright/package-lock.json
    - ci/playwright/tsconfig.json
    - ci/playwright/node-shim.d.ts
    - ci/playwright/playwright.config.ts
    - ci/playwright/helpers.ts
    - ci/playwright/fileaction.spec.ts
    - ci/playwright/review.spec.ts
    - ci/playwright/notification.spec.ts
    - ci/playwright/admin.spec.ts
    - backend/tests/test_playwright_contract.py
  modified: []
decisions:
  - "Kein @types/node: wenige Node-Schnittstellen in node-shim.d.ts deklariert, Paketliste bleibt bei den zwei freigegebenen Paketen"
  - "Lauf-, Fehler-, Abgelaufen- und Warteschlangenbilder über den echten Startzustand eines echten Auftrags, nur Werte aus php/lib/Model; der Vertragstest vergleicht die Listen Wert für Wert"
  - "Toasts 'nicht verfügbar', 'Format' und 'Download gesperrt' kommen vom Server (fileId im POST umgeschrieben), nur 'n davor', 'Backend nicht bereit' und 'allgemein' sind gefälscht"
  - "elke, fleur und greta werden im Admin-Spec per OCS in die Gruppe admin aufgenommen, damit die Admin-Bilder in DE/FR/du entstehen; die EN-alice-Projekte nutzen den Instanz-Admin"
  - "carol-ACL-Bild nur in den EN-Projekten (carol ist englisch); DE/FR zeigen dieselbe 404-Seite über 'fremd' und 'Freigabe entzogen'"
  - "Neuprüfung gescheitert im Hauptlauf per page.route mit der echten 503-Antwortform von SettingsController::state()"
metrics:
  duration: "ca. 70 min"
  completed: 2026-11-14
  tasks: 3
  files: 11
---

# Phase 1 Plan 16: Playwright-Abnahme-Suite Summary

Abnahme-Suite unter `ci/playwright/` nach dem UI-SPEC-Prüfvertrag: 12 Projekte (EN 375/768/1280 hell und dunkel plus Kontrast 1280 als dora, DE und FR je 375 hell und 1280 dunkel, de-du 375 hell), vier Specs für Dateiaktion, Prüfseite, Benachrichtigung und Admin, dazu ein Vertragstest in `backend/tests/`, der Raster, Pin, Drift-Tags und die geschlossenen Listen festhält. Lokal ist kein Browser gelaufen (Planvorgabe RAM); der echte Lauf kommt in Plan 20.

## Tasks

| Task | Name | Commit | Dateien |
|---|---|---|---|
| 1 | Paket, Projektraster, Helfer, Dateiaktions-Spec | 42216b4 | package.json, package-lock.json, tsconfig.json, node-shim.d.ts, playwright.config.ts, helpers.ts, fileaction.spec.ts |
| 2 | Prüfseiten- und Benachrichtigungs-Spec | dd66e9e | review.spec.ts, notification.spec.ts, helpers.ts (Listen) |
| 3 | Admin-Spec und Vertragstest | d3ff9da | admin.spec.ts, backend/tests/test_playwright_contract.py |

## Was die Suite belegt

- **Dateiaktion:** Menü offen für PDF mit Bild, Eintrag sichtbar für DOCX und ODT, nicht für TXT und Ordner (je Projekt). Nur im Funktionsprojekt `en-w1280-light`: Mehrfachauswahl, Papierkorb, öffentliche Freigabeseite, bob auf der gesperrten Freigabe der Saat, dazu der Server-Start für bob mit 403 `download_blocked`. Toasts: "als Nächstes" und "läuft schon" aus echten Antworten (201 mit `ahead` 0, dann 200 mit derselben jobId), "Download gesperrt" (403), "nicht verfügbar" (404) und "Format" (415) echt vom Server, "n davor", "Backend nicht bereit" und "allgemein" gefälscht. Fehler-Toast nach 12 s noch sichtbar (`page.clock.fastForward`), Erfolgs-Toast mit Schließen-Knopf und Link auf `/apps/pii_redaction/review/{id}`. Kopien `_redacted`/`_geschwärzt`/`_caviardé` in NFC, zweite mit ` (2)`, Etag des Originals gleich.
- **Prüfseite:** Je Projekt 14 gefälschte Bilder (Warteschlange als Nächstes, n davor, mit Backend nicht bereit; waiting, fetching, converting, rendering mit Balken; sechs Fehlgründe; abgelaufen; bereit mit Backend nicht bereit) und echte Läufe für bereit PDF/DOCX/ODT, Seite nicht abrufbar (Bild-Route 502), Kopie wird angelegt und angelegt, Original geändert (PUT), gelöscht (DELETE), Download nachträglich gesperrt, nicht verfügbar (fremd, Freigabe entzogen, carol nach ACL `-read` per `occ`). Stand nicht aktualisiert (503) und Sitzung abgelaufen (401) per Status-Route. Erste Seite der Kopie über `/index.php/core/preview`.
- **Pflicht-Assertions:** kein Dateiname in DOM, `document.title` und dekodiertem Startzustand bei "nicht verfügbar" und "gelöscht"; `no-store` an Status und Bild, `nosniff` am Bild; Fokus in `#pii-review-state` nach dem Knopf; Kanarie nicht im DOM; Kartentext gleich `var(--color-main-text)`; 16 px Statusbereich bis nächster Block; 320 px ohne waagrechtes Scrollen.
- **Benachrichtigung:** `review_ready`, `job_failed` (kaputtes PDF, echtes `render_failed`), `job_stale`, `copy_created` aus echten Läufen; OCS ohne Dateinamen und Kanarie, je Auftrag genau ein Eintrag mit Link auf die Prüfseite; Popover-Bild; Klick führt zur Prüfseite.
- **Admin:** ok, Knopf während der Prüfung ("Wird geprüft…", disabled, aria-busy, danach Fokus auf `#pii-backend-state`), Neuprüfung gescheitert; mit Tags @patch, @drift, @missing, @disabled, @unreachable, @noappapi. In den fünf Fehlerzuständen: "Apps öffnen" sichtbar, per Tab erreicht, `href` 200 für den angemeldeten Admin und für dora (eigener Browser-Kontext). Bannertext gleich `var(--color-<status>-text)` und ungleich `--color-text-maxcontrast`, keine Versionsnummer im Banner, 16 px Banner bis Versionszeile.

## Belege (lokal, 14.11.2026)

- `npm ci --ignore-scripts`: "added 4 packages"; `npx tsc --noEmit -p tsconfig.json`: Exit 0. Positivkontrolle: eine Probedatei mit `const x: number = "a"` ergab `error TS2322`, Exit 2 (danach gelöscht).
- `npx playwright test --list`: "Total: 372 tests in 4 files"; mit `--grep-invert "@drift|@patch|@missing|@disabled|@unreachable|@noappapi"` (wie der Hauptschritt in deploy-harp.yml): 300. `--list | grep -cE "review|notification"`: 144.
- Akzeptanz-Greps: Pin 1, drei Projektnamen 3, `pii_redaction-start` 2, `trashbin|Papierkorb` 5, Kanarie 1, `document.title` 2, Fehlgründe 5, `nosniff` 3, `review_ready|copy_created` 6, Drift-Tags 12, `def test_self` 8.
- `uv run pytest -q tests/test_playwright_contract.py`: 15 passed. Gesamt `uv run pytest -q`: 449 passed, 3 skipped (vorher 434, plus 15). ruff check "All checks passed!", ruff format 61 Dateien ok, pyright 0 Fehler, vulture ohne Befund.
- Gegenprobe ohne das Muster der Umsetzung: Der Vertragstest liest die Werte der geschlossenen Listen aus `php/lib/Model/*.php` (nicht aus den Specs) und die Drift-Tags gegen die `--grep-invert`-Zeile in `deploy-harp.yml`. Dabei fiel auf, dass die erste Fassung der Liste in helpers.ts erfundene bzw. fehlende Werte hatte (`internal_error` statt `check_error`, `submitted` und `done` fehlten); korrigiert vor dem Commit von Task 2.
- Keine U+2013/U+2014 und keine CRLF in den neuen Dateien (python-Prüfung, Ausgabe "no dashes, LF").
- Commits: Autor und Committer `street1983nk <k.cherif@outlook.de>`, Treffer für claude/co-authored/closes/fixes in den Commit-Texten: 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tsconfig.json und node-shim.d.ts zusätzlich**
- `npx tsc --noEmit` braucht eine Konfiguration; die Helfer brauchen `node:fs`, `node:child_process` (cron.php, occ) und `node:url`. Statt `@types/node` (nicht freigegeben) deklariert `node-shim.d.ts` genau diese Funktionen. `package.json` hat dazu ein Skript `typecheck`.
- **Commit:** 42216b4

**2. [Rule 1 - Bug] Geschlossene Listen nicht wie der Server**
- Erste Fassung kannte `internal_error` (gibt es nicht) und nicht `submitted`, `done`, `encrypted_pdf`, `too_many_pages`, `leak_detected`, `check_error`. Jetzt exakte Spiegel von `Status.php`, `Stage.php`, `Reason.php`; "sonstiger Grund" ist `check_error`. Der Vertragstest hält das fest.
- **Commit:** dd66e9e

**3. Abweichende Herstellung einzelner Bilder (dokumentiert, keine Vertragslücke im Bild):**
- "n davor" und "Backend nicht bereit" als Toast per `page.route` statt mit angehaltenem Backend: der Hauptlauf darf das Backend nicht abschalten, andere Tests brauchen es. Werte aus der geschlossenen Liste, jobId eines echten Auftrags.
- Warteschlange, Lauf, Fehlgründe und Abgelaufen über den echten Startzustand der Prüfseite mit getauschten Feldern (UI-SPEC erlaubt `page.route` bzw. Initialzustand per Saat).
- carol-ACL nur in den EN-Projekten; DE/FR/du zeigen dieselbe 404-Karte über "fremd" und "Freigabe entzogen".
- Für die nicht englischen Projekte ist die Freigebende alice, für die alice-Projekte dora.

## Offen für den echten Lauf (Plan 20)

- Nichts davon ist gegen einen Browser gelaufen. Selektoren der Dateien-App (`data-cy-files-list-row-actions`, `-row-checkbox`, `-selection-actions`, Trashbin-Zeilenname mit `^=`), Toastify-Klassen (`.toastify.on`, `toast-success` usw.), Glocke und Einträge der Notifications-App sind aus der Server-Struktur abgeleitet und können je NC 33/34/35 abweichen.
- Laufzeit: ca. 15 echte Aufträge je Projekt (DOCX/ODT mit LibreOffice), mal 12 Projekte und sieben Beine. Das Job-Timeout von 90 min in deploy-harp.yml kann knapp werden; in Plan 20 messen.
- `/index.php/core/preview` für PDF braucht einen aktiven PDF-Vorschau-Anbieter (imagick/ghostscript). Fehlt er im Runner, scheitert das Bild "kopie/erste-seite" mit klarer Meldung; dann Vorschau im Workflow einschalten oder Kopie anders rendern.
- `request.get(href)` als dora läuft über einen eigenen Browser-Kontext mit Anmeldung (keine Basic-Auth auf eine HTML-Seite).
- Admin-Fehlerzustände laufen erst mit den Drift-Schritten aus Plan 18 (`PII_BACKEND_VERSION`).

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche. T-01-16-01: Pin 1.65.0 exakt in package.json und Lock, vom Vertragstest geprüft. T-01-16-02: nur synthetische Fixtures, Kanarie-Assertion im DOM und in OCS. T-01-16-03: Fälschungen nur mit Werten der Liste aus php/lib/Model (Laufzeitprüfung in `forgeState`/`forgeStatus`, Vertragstest), echte Läufe für bereit, Kopie und Rechte.

## Self-Check: PASSED

- Alle elf Dateien vorhanden; Commits 42216b4, dd66e9e, d3ff9da in `git log`.
- Docker wurde nicht benutzt (Planvorgabe: lokal kein Browser, kein Stack); `docker ps` meldet keinen laufenden Daemon.
