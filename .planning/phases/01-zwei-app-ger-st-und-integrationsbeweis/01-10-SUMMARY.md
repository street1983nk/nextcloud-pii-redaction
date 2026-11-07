---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 10
subsystem: backend-runner
tags: [runner, semaphore, memory-guard, heartbeat, signed-routes, lifespan]
requires: [01-05, 01-06, 01-07]
provides:
  - "runner/runner.py: Runner (Semaphore(1), run, run_once), next_delay, last_child, ChildRun, PAGE_FILE, OUTPUT_FILE"
  - "nc.Outcome (ok, refused, unreachable), nc.progress_outcome, nc.ack_outcome; progress/ack bleiben bool"
  - "store/repo.py: set_source, set_output"
  - "api/: build_router, GET /status, GET /jobs/{job_id}/pages/{n}.png, GET /jobs/{job_id}/output"
  - "main.py: Companion-Prüfung und Runner im Lifespan, Router, access_log=False"
affects: [01-12, 01-13, 01-14, 01-15, 01-17]
tech-stack:
  added: []
  patterns:
    - "Runner-Seams als Schlüsselwort-Argumente mit echten Standardwerten; Tests ersetzen nc, Kind, LibreOffice, Uhr"
    - "Herzschlag als eigene Aufgabe neben dem Auftrag; Ablehnung bricht per cancel ab, das killt die Kindgruppe"
    - "Abgelehnter Bericht beendet den Auftrag, fehlende Antwort nicht (ack bis dreimal)"
key-files:
  created:
    - backend/src/pii_redaction_backend/runner/__init__.py
    - backend/src/pii_redaction_backend/runner/runner.py
    - backend/src/pii_redaction_backend/api/__init__.py
    - backend/src/pii_redaction_backend/api/status.py
    - backend/src/pii_redaction_backend/api/pages.py
    - backend/src/pii_redaction_backend/api/output.py
    - backend/tests/test_runner.py
    - backend/tests/test_api_routes.py
  modified:
    - backend/src/pii_redaction_backend/nc.py
    - backend/src/pii_redaction_backend/store/repo.py
    - backend/src/pii_redaction_backend/main.py
    - backend/tests/test_main.py
key-decisions:
  - "nc.Outcome unterscheidet Ablehnung (409/400, Auftrag endet) von fehlender Antwort (Lease kann noch leben, ack wird bis zu dreimal mit 2 s/4 s Pause wiederholt)"
  - "Gateway ohne Antwort oder mit 5xx: kein ack, Ordner weg; der Lease läuft ab und PHP gibt den Auftrag erneut aus (Deckel 3 Versuche). 403/404 und sonstige Ablehnungen: failed(not_readable)"
  - "Nach dem Rendern bleiben nur page-1.png und meta.json; Quelle und umgewandelte PDF werden gelöscht"
  - "start.sh bleibt byteweise HaRP-Vorlage; der Zugriffslog ist über run_app(access_log=False) aus"
requirements-completed: []  # PLAT-05, JOB-02, JOB-06 erst mit Container-Lauf in CI (Plan 15) belegt
metrics:
  duration: "ca. 45 min"
  completed: 2026-11-07
  tasks: 2
  files: 12
---

# Phase 1 Plan 10: Runner und signierte Container-Endpunkte Summary

Der Container arbeitet jetzt: ein Runner mit `asyncio.Semaphore(1)` fragt nur nach Arbeit, wenn die PHP-App den Handshake beantwortet hat und der RAM-Wächter `admit("soffice")` zulässt. Er erledigt analyze, apply und purge mit ehrlichen Stufen und einem Herzschlag, der den Lease verlängert. Die drei Container-Endpunkte sind nur signiert erreichbar und liefern nur Seite 1, eine geprüfte Ausgabe und Zahlen.

## Ergebnis

- **Task 1 (TDD, RED `6847a3c`, GREEN `bfad9ef`):** analyze meldet `fetching`, bei DOCX/ODT `converting`, dann `rendering(0, None)` und `rendering(1, n)`, danach `ack(review, pagesTotal, etagSeen, image)`. Quelle wird nach Magic-Bytes zu `src.<format>` umbenannt (LibreOffice braucht die Endung), Arbeitsordner mit 0700. Gateway 409: kein ack, Ordner weg. 404: `failed(not_readable)`. Unbekanntes Format: `failed(unsupported_format)`. `ChildTimeout`/`ChildFailed`/`ConversionFailed`/kaputtes `meta.json`: `failed(render_failed)`. apply: Platzhalter-Kind, sha256 und Größe, `set_output`, `ack(verified)`. purge: Ordner und `state.db`-Zeile weg, `ack(purged)`. Nach jedem Kind stehen Art, Spitzen-RSS und Dauer in `last_child()`. 19 Tests, einer davon rendert über den echten Kindprozess.
- **Task 2 (`7d1d85c`):** `api/` mit `build_router`; `/status` liefert `{version, ready, companion, busy, lastChild}`; Seite nur für `n == 1` und positive Job-ID aus festem Dateinamen, mit `no-store` und `nosniff`; Ausgabe nur, wenn `state.db` `output_sha256` trägt. `main.py` startet Companion-Prüfung und Runner im Lifespan und stoppt beide geordnet; die alte Admin-`/status`-Route mit Einstellungen ist ersetzt. `test_api_routes.py` (8 Tests): genau die drei Vertragsrouten plus `/heartbeat`, `/init`, `/enabled`, `/l10n`; jede eigene Route ohne oder mit falscher Signatur 401; Seite 2, Job 0, fremder Job 404; Ausgabe 404 bis verified.

Gates in `backend/` vor jedem Commit: ruff, ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 412 passed / 3 skipped (seriell). Neue Pakete: keine.

## TDD Gate Compliance

`test(01-10)` (`6847a3c`) liegt vor `feat(01-10)` (`bfad9ef`). Die Tests entstanden zusammen mit der Umsetzung; der RED-Lauf wurde nachträglich belegt, indem das Paket `runner/` kurz aus dem Baum genommen wurde (Sammelfehler beim Import), dann zurückgelegt.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2] `nc.Outcome` statt bool für Bericht und Abschluss**
- **Issue:** Hinweis aus 01-06: `progress`/`ack` lieferten False für 409 und für Netzfehler gleich.
- **Fix:** `progress_outcome`/`ack_outcome` liefern `ok`, `refused` oder `unreachable`; die bool-Funktionen bleiben unverändert für bestehende Tests.
- **Commit:** bfad9ef

**2. Stufe `rendering(0, None)` statt `rendering(0, n)`**
- **Issue:** Die Seitenzahl kennt erst das Render-Kind; im Serverprozess öffnet niemand die fremde Datei.
- **Fix:** Erst `rendering(0, None)` (kein Balken), nach dem Kind `rendering(1, n)`. Die Prüfseite zeigt ohne bekannte Seitenzahl bewusst keinen Balken.

**3. `docker/start.sh` unverändert**
- **Issue:** Die Datei ist laut Kopf die byteweise HaRP-Vorlage.
- **Fix:** `run_app(..., access_log=False)` in `main.py` (Akzeptanz erlaubt beides); `logs.py` schaltet `uvicorn.access` zusätzlich ab.

**4. `test_store_metadata.py` unverändert**
- Die Regel "genau ein leeres `<routes/>`" mit Selbsttest gab es schon aus 01-01.

**5. [Rule 2] Gateway ohne Antwort oder mit 5xx ergibt kein ack**
- **Issue:** Der Plan nennt nur 404/403 und 409. Ein vorübergehender Netzfehler als `not_readable` wäre ein falscher Endzustand.
- **Fix:** Kein ack, Ordner weg; der Auftrag kommt nach Lease-Ablauf wieder (höchstens 3 Ausgaben).

**6. `/l10n` in der Routenliste**
- `nc_py_api.set_handlers` hängt den Ordner `l10n` als statische Route ein; sie liegt hinter derselben Signaturprüfung. Im Gate als Lebenszyklus-Route geführt.

## Hinweise für spätere Pläne

- **Plan 12 (QueueController):** Ein `progress` nach Lease-Ablauf ergibt 409 und beendet den Auftrag im Container. Der Herzschlag sendet alle 30 s die aktuelle Stufe mit denselben Zählern.
- **Plan 15:** Ein Lauf im echten Container belegt LibreOffice, `peak_child_rss_kb` und die RAM-Zulassung.
- Läuft der Herzschlag ab, während ein Datei-Schritt im Thread hängt (`asyncio.to_thread`), kann der Ordner nach dem Löschen wieder entstehen; der nächste purge räumt ihn.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-10-01 bis -06 mitigiert (keine Route in `info.xml`, Middleware, 401-Test; int-IDs und fester Dateiname; Semaphore plus PHP-Sperrzeile; `admit` vor claim; Zugriffslog aus; Ausgabe nur mit `output_sha256`).

## Self-Check: PASSED

- Dateien vorhanden: runner/runner.py, api/{__init__,status,pages,output}.py, test_runner.py, test_api_routes.py
- Commits vorhanden: 6847a3c, bfad9ef, 7d1d85c
