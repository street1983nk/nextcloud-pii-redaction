---
phase: 1
slug: zwei-app-ger-st-und-integrationsbeweis
status: planned
nyquist_compliant: false
wave_0_complete: false
created: 2026-11-07
---

# Phase 1: Validation Strategy

> Vertrag für Rückmeldungen während der Ausführung. Grundlage: 01-RESEARCH.md "Validation Architecture", Pläne 01-01 bis 01-20.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.2.0 (backend, lokal und `python.yml`), phpunit 11.5.57 (nur CI, `php.yml` und `deploy-harp.yml`), Playwright 1.65.0 (nur CI, `ci/playwright/`), GitHub Actions mit HaRP (`deploy-harp.yml`, sechs Beine plus MariaDB-Bein, Upgrade-Job) |
| **Config file** | `backend/pyproject.toml`, `php/phpunit.xml`, `ci/playwright/playwright.config.ts` (alle in Phase 1 angelegt) |
| **Quick run command** | `cd backend && uv run pytest -q -x` |
| **Full suite command** | `cd backend && uv run ruff check . && uv run ruff format --check . && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright && uv run vulture && uv run pytest -q`, dazu `cd php && npm ci && npm run build`; PHP, Integration und Playwright nur in CI nach Owner-Freigabe |
| **Estimated runtime** | lokal ca. 30 bis 60 s; `php.yml` ca. 5 min; `deploy-harp.yml` ca. 30 bis 50 min je Bein |

---

## Sampling Rate

- **After every task commit:** `cd backend && uv run pytest -q -x` (enthält die statischen PHP-, Log-, Sprach-, Workflow- und Asset-Gates)
- **After every plan wave:** volle Python-Gates plus `npm run build`
- **CI-Stichproben (je Push eine Owner-Freigabe):** nach Welle 3 (Plan 07: `php.yml`, `python.yml` mit POSIX-Tests), nach Welle 8 (Plan 20: alle Workflows)
- **Before `/gsd:verify-work`:** alle Workflows auf `phase-01` grün, Owner-Abnahme per Playwright
- **Max feedback latency:** lokal unter 60 s; PHP-Verhalten der Wellen 5 und 6 erst in Plan 20 (siehe Sign-Off)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | PLAT-01 | T-01-SC | Pakete vor Installation freigegeben | manual-gate | `npm view @nextcloud/files@4.1.1 repository.url` | n. a. | ⬜ pending |
| 1-01-02 | 01 | 1 | PLAT-01, PLAT-05 | T-01-01-03 | leeres `<routes/>` | unit | `cd backend && uv run pytest -q --ignore=tests/test_workflows.py` | ✅ vorhanden, verschoben | ⬜ pending |
| 1-01-03 | 01 | 1 | PLAT-03 | T-01-01-01 | Actions per SHA | unit | `cd backend && uv run pytest -q` | ✅ erweitern | ⬜ pending |
| 1-01-04 | 01 | 1 | PLAT-01 | T-01-01-02 | Lockstep-Gate mit Selbsttest | unit | `uv run pytest -q tests/test_lockstep_versions.py tests/test_workflows.py -x` | ❌ W0 im Task | ⬜ pending |
| 1-02-01 | 02 | 2 | JOB-04 | T-01-02-01 | keine Klartextspalten | unit (php, CI) | `uv run pytest -q -x` lokal; `ModelTest` in CI | ❌ im Task | ⬜ pending |
| 1-02-02 | 02 | 2 | JOB-06 | T-01-02-05 | höchstens ein aktiver Lease | unit (php, CI) | `QueueMapperTest` in `php.yml` | ❌ im Task | ⬜ pending |
| 1-03-01 | 03 | 2 | JOB-02 | T-01-03-05 | Kataloge ohne Namensplatzhalter | unit | `uv run python ../scripts/l10n_js.py --root ../php/l10n --check` | ❌ im Task | ⬜ pending |
| 1-03-02 | 03 | 2 | PLAT-05 | T-01-03-01..04 | Recheck-, Transport-, Log-Gates | unit | `uv run pytest -q tests/test_php_gates.py tests/test_log_calls.py -x` | ❌ im Task | ⬜ pending |
| 1-03-03 | 03 | 2 | JOB-02 | T-01-03-06 | U+00A0, keine Striche/Emojis | unit | `uv run pytest -q tests/test_trilingual.py tests/test_public_texts.py -x` | ✅ erweitern | ⬜ pending |
| 1-04-01 | 04 | 2 | JOB-03 | T-01-04-01, -02 | Recheck, Download-Sperre fail closed | unit (php, CI) | `FileAccessTest`; lokal `test_php_gates.py` | ❌ im Task | ⬜ pending |
| 1-04-02 | 04 | 2 | PLAT-02 | T-01-04-03 | sieben Zustände, PNG-Magic, Deckel | unit (php, CI) | `BackendStateTest`, `ExAppServiceTest` | ❌ im Task | ⬜ pending |
| 1-04-03 | 04 | 2 | PLAT-02 | T-01-04-04 | Fremd-ExApp 403 | unit (php, CI) | `HandshakeControllerTest` | ❌ im Task | ⬜ pending |
| 1-05-01 | 05 | 2 | JOB-02 | T-01-05-01, -02 | Kind ohne Geheimnis, Gruppen-Kill | unit (POSIX in CI) | `uv run pytest -q tests/test_child.py tests/test_sniff.py -x` | ❌ im Task | ⬜ pending |
| 1-05-02 | 05 | 2 | JOB-02 | T-01-05-04 | Platzhalter ohne Originalinhalt | unit | `uv run pytest -q tests/test_render.py tests/test_placeholder.py tests/test_store_schema.py -x` | ❌ im Task | ⬜ pending |
| 1-05-03 | 05 | 2 | PLAT-03 | T-01-05-05 | LibreOffice ohne Java | unit | `uv run pytest -q tests/test_dockerfile.py -x` | ✅ erweitern | ⬜ pending |
| 1-06-01 | 06 | 3 | JOB-02 | T-01-06-01 | Logs ohne Traceback/Kanarie | unit | `uv run pytest -q tests/test_logs.py tests/test_model.py tests/test_config.py -x` | ✅ erweitern | ⬜ pending |
| 1-06-02 | 06 | 3 | PLAT-02 | T-01-06-02, -03 | Feldprüfung, Größendeckel, 409 stale | unit | `uv run pytest -q tests/test_nc.py tests/test_companion.py tests/test_handshake.py tests/test_boundary.py -x` | ❌ im Task | ⬜ pending |
| 1-06-03 | 06 | 3 | JOB-06 | T-01-06-05 | unlesbarer Kopfraum lässt nichts zu | unit | `uv run pytest -q tests/test_memory_guard.py -x` | ❌ im Task | ⬜ pending |
| 1-07-01..03 | 07 | 4 | PLAT-01, PLAT-05 | T-01-07-01..03 | Push nur auf phase-01 nach Freigabe | CI | `gh run list --branch phase-01` | n. a. | ⬜ pending |
| 1-08-01 | 08 | 5 | JOB-03, JOB-04, JOB-06 | T-01-08-01..04 | Start/Status nur nach Recheck, Etag | unit (php, CI) | `JobServiceTest`, `EtagBindingTest`; lokal `test_php_gates.py` | ❌ im Task | ⬜ pending |
| 1-08-02 | 08 | 5 | JOB-01 | T-01-08-05, -06 | Codes laut UI-SPEC, no-store | unit (php, CI) | `JobControllerTest` | ❌ im Task | ⬜ pending |
| 1-09-01 | 09 | 5 | JOB-01 | T-01-09-01..04 | Aktion nur für erlaubte Knoten | build + e2e | `cd php && npm ci && npm run build` | ❌ im Task | ⬜ pending |
| 1-09-02 | 09 | 5 | JOB-02 | T-01-09-01 | kein v-html, ehrlicher Fortschritt | build + e2e | `npm run build && uv run pytest -q tests/test_trilingual.py -x` | ❌ im Task | ⬜ pending |
| 1-09-03 | 09 | 5 | PLAT-02 | T-01-09-01 | kein innerHTML | unit | `uv run pytest -q tests/test_ui_assets.py -x` | ✅ AVS-Kopie | ⬜ pending |
| 1-10-01 | 10 | 5 | JOB-06, JOB-02 | T-01-10-03, -04 | Semaphore 1, admit vor claim | unit | `uv run pytest -q tests/test_runner.py -x` | ❌ im Task | ⬜ pending |
| 1-10-02 | 10 | 5 | PLAT-05 | T-01-10-01, -02, -05 | nur signierte Endpunkte, kein Zugriffslog | unit | `uv run pytest -q tests/test_api_routes.py tests/test_main.py tests/test_store_metadata.py -x` | ❌ im Task | ⬜ pending |
| 1-11-01 | 11 | 5 | PLAT-02 | T-01-11-02, -03 | Banner ohne Inhalte, Apps-Link | unit (php, CI) | `AdminSettingsTest`; lokal Gates | ❌ im Task | ⬜ pending |
| 1-11-02 | 11 | 5 | PLAT-02 | T-01-11-01 | Route nur für Admins | unit (php, CI) | `SettingsControllerTest` | ❌ im Task | ⬜ pending |
| 1-12-01 | 12 | 6 | JOB-06, JOB-02, JOB-04 | T-01-12-01, -03 | Token, Listen, Etag beim ack | unit (php, CI) | `QueueControllerTest` | ❌ im Task | ⬜ pending |
| 1-12-02 | 12 | 6 | JOB-03, JOB-04 | T-01-12-02, -05 | Gateway auftragsgebunden | unit (php, CI) | `GatewayControllerTest` | ❌ im Task | ⬜ pending |
| 1-13-01 | 13 | 6 | PLAT-05, JOB-03, JOB-04 | T-01-13-01..07 | Recheck je Anfrage, no-store, nosniff | unit (php, CI) | `ReviewControllerTest` | ❌ im Task | ⬜ pending |
| 1-14-01 | 14 | 6 | JOB-02 | T-01-14-01 | Benachrichtigung ohne Namen | unit (php, CI) | `NotifierTest`, `SuffixTest` | ❌ im Task | ⬜ pending |
| 1-14-02 | 14 | 6 | JOB-02 | T-01-14-02..04 | sha256, newFile, kein Überschreiben | unit (php, CI) | `PublishServiceTest` | ❌ im Task | ⬜ pending |
| 1-14-03 | 14 | 6 | JOB-04 | T-01-14-05 | Schreiben/Löschen macht ungültig | unit (php, CI) | `FileLifecycleListenerTest` | ❌ im Task | ⬜ pending |
| 1-15-01 | 15 | 7 | JOB-02 | T-01-15-01 | Kanarie nur im Textkörper | unit | `uv run pytest -q tests/test_ci_fixtures.py -x` | ❌ im Task | ⬜ pending |
| 1-15-02 | 15 | 7 | JOB-01, JOB-02 | T-01-15-04 | Kernweg je Format | integration | `bash -n ci/seed.sh ci/flow.sh`; echt in `deploy-harp.yml` | ❌ im Task | ⬜ pending |
| 1-15-03 | 15 | 7 | PLAT-03, JOB-06 | T-01-15-02, -03 | sieben Beine, MariaDB | unit + integration | `uv run pytest -q tests/test_workflows.py tests/test_lockstep_versions.py -x` | ✅ erweitern | ⬜ pending |
| 1-16-01..03 | 16 | 7 | JOB-01, JOB-02, JOB-03, PLAT-02 | T-01-16-01..03 | UI-SPEC-Pflicht-Assertions | e2e (CI) | `npx playwright test --list`; `uv run pytest -q tests/test_playwright_contract.py -x` | ❌ im Task | ⬜ pending |
| 1-17-01 | 17 | 7 | JOB-03, JOB-04, JOB-06 | T-01-17-04, -05 | Rechte, Etag, Einzelauftrag im Lauf | integration (CI) | `bash -n ci/rights.sh ci/stale.sh ci/queue.sh` | ❌ im Task | ⬜ pending |
| 1-17-02 | 17 | 7 | PLAT-05, (Krit. 5) | T-01-17-01..03 | keine Browser-Route, Kanarie mit Positivkontrolle, Messung | integration (CI) | `bash -n ci/routes.sh ci/canary.sh ci/measure.sh` | ❌ im Task | ⬜ pending |
| 1-17-03 | 17 | 7 | PLAT-05 | T-01-17-01 | Gates auf Skripte und Dateibaum | unit | `cd backend && uv run pytest -q` | ❌ im Task | ⬜ pending |
| 1-18-01 | 18 | 8 | PLAT-01, PLAT-02 | T-01-18-03, -04 | Upgrade, Drift, Companion | integration (CI) | `uv run pytest -q tests/test_workflows.py -x` | ✅ erweitern | ⬜ pending |
| 1-18-02 | 18 | 8 | PLAT-01 | T-01-18-01, -02 | zwei Archive, Pins | unit | `uv run pytest -q tests/test_release_archives.py -x` | ❌ im Task | ⬜ pending |
| 1-19-01 | 19 | 8 | PLAT-01, PLAT-02 | T-01-19-01, -02 | Doku dreisprachig | unit | `uv run pytest -q tests/test_public_texts.py tests/test_trilingual.py -x` | ✅ erweitern | ⬜ pending |
| 1-19-02 | 19 | 8 | (Sprache) | T-01-19-01 | Umlaut-Audit mit Positivkontrolle | audit + unit | `cd backend && uv run pytest -q` | n. a. | ⬜ pending |
| 1-20-01..04 | 20 | 9 | alle | T-01-20-01..04 | voller CI-Beweis, Abnahme | CI + manual | `gh run list --branch phase-01 ...` | n. a. | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement Coverage

| Req | Unit (lokal) | Unit (PHP, CI) | Integration (CI) | e2e (Playwright) |
|-----|--------------|----------------|------------------|------------------|
| PLAT-01 | test_lockstep_versions, test_release_archives | - | Upgrade-Job 0.0.1 nach 0.1.0 | - |
| PLAT-02 | test_companion, test_handshake | BackendStateTest, AdminSettingsTest, SettingsControllerTest | Drift 1 bis 6, Companion missing | admin.spec @patch @drift @missing @disabled @unreachable @noappapi |
| PLAT-03 | test_workflows, test_dockerfile | - | sechs Beine plus MariaDB | alle Projekte je Bein |
| PLAT-05 | test_store_metadata, test_api_routes, test_php_gates (Regeln 3, 12) | ReviewControllerTest | ci/routes.sh (auch nach Upgrade) | review.spec (no-store, nosniff) |
| JOB-01 | test_trilingual (Texte) | JobControllerTest | ci/flow.sh pdf/docx/odt | fileaction.spec |
| JOB-02 | test_runner, test_placeholder, test_render | NotifierTest, PublishServiceTest, QueueControllerTest | ci/flow.sh (Benachrichtigung, Kopie, (2)) | review.spec, notification.spec |
| JOB-03 | - | FileAccessTest, GatewayControllerTest, ReviewControllerTest | ci/rights.sh (fremd, ACL, Entzug, Sperre) | review.spec "nicht verfügbar" |
| JOB-04 | - | EtagBindingTest, QueueControllerTest, FileLifecycleListenerTest, PublishServiceTest | ci/stale.sh | review.spec "Original geändert", "gelöscht" |
| JOB-06 | test_memory_guard, test_runner | QueueMapperTest | ci/queue.sh (SQLite und MariaDB) | fileaction.spec Toast "n davor" |
| Krit. 5 | test_logs, test_log_calls, test_php_gates (13, 14, 15) | ModelTest | ci/canary.sh mit Positivkontrolle | review.spec "Kanarie nicht im DOM" |

---

## Wave 0 Requirements

Kein eigener Wave-0-Plan: jede Testdatei entsteht im Task, der das Verhalten liefert (Pläne 01 bis 19, Spalte "File Exists" = "im Task"). Vorab nötig und in Plan 01 enthalten:

- [ ] `backend/` mit `pyproject.toml` und `tests/conftest.py` (`BACKEND_ROOT`, `REPO_ROOT`)
- [ ] `php/composer.json`, `php/phpunit.xml`, `php/tests/bootstrap.php` (AVS-Kopie, Backslash-Regel)
- [ ] `.github/workflows/php.yml` (phpunit in CI)
- [ ] Owner-Freigabe der Pakete (Plan 01 Task 1)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Paket-Legitimität | PLAT-01 (Lieferkette) | Owner-Regel, nie automatisch freigebbar | Plan 01 Task 1 |
| Push und Korrektur-Pushes | alle | Owner-Regel "vor jedem Push fragen" | Plan 07 und Plan 20 |
| UI-Abnahme gemeinsam | JOB-01, JOB-02, PLAT-02 | Owner-Regel, Screenshots aus CI | Plan 20 Task 4, Raster laut UI-SPEC |
| Zertifikatsstatus #1419 | PLAT-01 | nur lesen, kein Kommentar | Plan 20 Task 2 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (Testdateien entstehen im jeweiligen Task)
- [x] No watch-mode flags
- [ ] Feedback latency < 60 s für PHP-Verhalten: **nicht erfüllt.** PHP läuft lokal nicht; Verhalten der Wellen 2 und 3 wird in Plan 07 gesampelt, das der Wellen 5 und 6 (Pläne 08, 11 bis 14) erst in Plan 20. Lokal greifen nur die statischen PHP-Gates. Option für den Owner: zusätzlicher früher Push nach Welle 6 (gleiche Form wie Plan 07).
- [ ] `nyquist_compliant: true`: bewusst `false`, Grund siehe vorige Zeile.

**Approval:** pending
