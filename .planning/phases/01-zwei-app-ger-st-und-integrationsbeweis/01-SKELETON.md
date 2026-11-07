# Walking Skeleton und Schnittstellenvertrag: PII Redaction Phase 1

**Phase:** 1
**Erstellt:** 2026-11-07 (Planer)
**Zweck:** Ein Ort für alle Verträge, die mehrere Pläne teilen (IDs, Tabellen, Enums, Routen, JSON-Formen, Konstanten, Datei-Besitz). Jeder Plan liest diese Datei; Abweichungen sind nur mit Änderung hier erlaubt.

## Capability Proven End-to-End

Ein Admin installiert die PHP-App `pii_redaction` und die ExApp `pii_redaction_backend` auf NC 33, 34 oder 35 (amd64 oder arm64, HaRP). Ein Nutzer wählt in Dateien bei einer PDF-, DOCX- oder ODT-Datei "Schwärzen / Pseudonymisieren"; PHP prüft Rechte, Download-Sperre und Gegen-App und legt einen Auftrag an Datei-ID und Etag an. Der Container zieht den Auftrag über die Warteschlange (Lease, ein Auftrag zur Zeit, RAM-Zulassung), lädt die Datei über das auftragsgebundene Gateway, rendert Seite 1 im Kindprozess (DOCX/ODT vorher über LibreOffice), meldet `review`; der Nutzer bekommt eine Benachrichtigung ohne Dateinamen, öffnet die Platzhalter-Prüfseite und sieht Seite 1 als Bild über die PHP-App (Recheck je Anfrage). "Platzhalter-Kopie anlegen" erzeugt eine PDF ohne Originalinhalt, die PHP per `newFile()` als Auftraggeber neben das Original legt. Eine Kanarie aus dem Original taucht in keiner DB und keinem Log auf.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| App-Aufteilung | PHP-App `pii_redaction` (Namespace `OCA\PiiRedaction`): Dateiaktion, Aufträge, Rechte, Prüfseite, Benachrichtigung, Ablage, Admin, Gateway, Queue, Handshake. ExApp `pii_redaction_backend` (Python-Paket `pii_redaction_backend`): Download, Rendering, Konvertierung, Platzhalter-PDF | RESEARCH Architekturkarte |
| Repo-Layout | `php/`, `backend/` (alle Python-Gates, auch repo-weite, in `backend/tests/`), `ci/` (Saat, Fixtures, Skripte, `ci/playwright/`), `scripts/` (Repo-Werkzeuge), Doku an der Wurzel | AVS-Muster |
| Lockstep | Eine Version in `php/appinfo/info.xml`, `backend/appinfo/info.xml` (`<version>`, `<image-tag>`), `backend/pyproject.toml`, Git-Tag; Build-Gate exakt; Laufzeit Major.Minor ungleich Fehler, Patch ungleich Hinweis | PLAT-01 |
| Daten in Nextcloud | nur geschlossene Listen, Zahlen, IDs, Etag; kein Dateiname, Pfad, Mime, Text | RESEARCH Entscheid 3 |
| Warteschlange | Pull über OCS, Sperrzeile `pii_slot` (eine Zeile, bedingte `UPDATE`) für "ein Auftrag zur Zeit", Lease als `lease_until BIGINT`, einzige Uhr `ITimeFactory::getTime()` | Orchestrator-Entscheid 7; RESEARCH Pattern 2 Option "Sperrzeile" (dialektfrei, keine Selbstbezug-Unterabfrage, MariaDB-tauglich) |
| Gateway | auftragsgebunden: nur Datei des geleasten Auftrags, nur mit Claim-Token, nur als Auftraggeber, nur bei gleichem Etag | RESEARCH Entscheid 5 |
| Container-Routen | keine: `backend/appinfo/info.xml` trägt ein leeres `<routes/>`; Container wird nur signiert aus `ExAppService` gerufen | PLAT-05, Orchestrator-Entscheid 8 |
| HTTP im Container | ausschließlich `backend/src/pii_redaction_backend/nc.py` (Gate `test_boundary.py`) | Orchestrator-Entscheid 2 |
| Container-Aufruf aus PHP | ausschließlich `ExAppService::proxyRequest(string $route, string $userId, string $method, array $params, float $timeout, array $options = [])` (AVS-Signatur plus `$options`, übergibt `['timeout' => $timeout] + $options`); `exAppRequest(` steht genau einmal in `ExAppService.php` | Orchestrator-Entscheid 1 |
| Logging | Python: Allowlist für `extra`, kein Traceback, kein `LOGGER.exception`, Literal ohne Platzhalter; PHP: statischer Satz mit Präfix "PII Redaction: ", Kontext nur `jobId, fileId, status, reason, app, exception, class` | Orchestrator-Entscheid 5 |
| Download-Sperre | fail closed: jede Ausnahme oder unklare Lage gilt als gesperrt; keine Ausnahme für `shareapi_allow_view_without_download` | Orchestrator-Entscheid 6 |
| Benachrichtigung | eigener Notifier, kein Dateiname in Betreff/Nachricht, kein `getMessage()` im Log, kein `#[\Override]` | Orchestrator-Entscheid 4, Owner 07.11. |
| "Apps öffnen" | AVS-Form: `linkToRoute('appstore.page.viewApps')`, bei leerem String `linkToRoute('settings.AppSettings.viewApps')`; Playwright prüft in jedem Fehlerzustand Existenz, Tab-Erreichbarkeit und 200 | Orchestrator-Entscheid 3 (ersetzt UI-SPEC-Satz "Auswahl über Serverversion") |
| Seitenbild | Backend-PNG Seite 1 (PyMuPDF im Kindprozess, 120 dpi), über PHP-Proxy mit Recheck, `Cache-Control: private, no-store` | STACK, UI-SPEC Fläche 2 |
| Platzhalter-Kopie | einseitige PDF ohne Originalinhalt, Name mit echtem Zusatz je Sprache, Endung `.pdf` | Owner 07.11. |
| LibreOffice | ab Phase 1 im Image (`libreoffice-writer-nogui` + Schriften), Aufruf als Kindprozess mit leerer Umgebung, Profil je Auftrag, Zeitgrenze, Gruppen-Kill | Owner 07.11. |
| Lokal vs. CI | Lokal nur Python-Gates und `npm run build`; PHP, Docker, HaRP, Playwright nur in CI; Push nur nach Owner-Freigabe auf `phase-01` | Owner-Regeln, RAM |

## IDs und Konstanten

| Name | Wert | Ort |
|---|---|---|
| `Application::APP_ID` | `pii_redaction` | `php/lib/AppInfo/Application.php` |
| `Application::BACKEND_APP_ID` | `pii_redaction_backend` | dito |
| Python `APP_ID` | `pii_redaction_backend` | `backend/src/pii_redaction_backend/__init__.py` |
| Image | `ghcr.io/street1983nk/pii_redaction_backend` | `backend/appinfo/info.xml`, `docker.yml` |
| Env-Präfix Container | `PII_REDACTION_` (z. B. `PII_REDACTION_LOG_LEVEL`) | `backend/appinfo/info.xml`, `config.py` |
| Lease (vorläufig) | analyze 120 s, apply 300 s, purge 60 s; Verlängerung bei jedem `progress` | `php/lib/Db/JobMapper.php` Konstanten `LEASE_ANALYZE`, `LEASE_APPLY`, `LEASE_PURGE` |
| Höchstversuche | 3 Ausgaben ohne `ack` ergibt `failed(repeatedly_stuck)` | `JobMapper::MAX_ATTEMPTS` |
| Größendeckel | Quelle 256 MiB (`MAX_SOURCE_BYTES`, Python), PNG 16 MiB (`ExAppService::MAX_PAGE_BYTES`), Ausgabe 32 MiB (`PublishService::MAX_OUTPUT_BYTES`) | vorläufig, Phase 2 härtet |
| Timeouts `exAppRequest` | `/status` 1,5 s, Seite 10 s, Ausgabe 120 s | `ExAppService` |
| RAM-Bedarf (vorläufig) | `render` 512 MiB, `soffice` 1 GiB, Reserve 256 MiB | `backend/.../resources/memory_guard.py` Konstanten mit Kommentar "vorläufig, nach Messung Phase 1/2 festschreiben" |
| Kanarie | `PIIKANARIE7Q4XZ9` | `ci/make_fixtures.py`, Kanarien-Schritt |
| Abfrage Prüfseite | 3 s, Rückoff 3, 6, 12, 30 s | `php/src/ReviewPlaceholder.vue` |
| Container-Polling | 1 s nach Arbeit, bis 10 s im Leerlauf | `backend/.../runner/runner.py` |

## Logging-Allowlists

- Python `extra`-Schlüssel (`ALLOWED_EXTRA` in `logs.py`, gleiche Menge als Literal in `backend/tests/test_log_calls.py`): `job_id, task, stage, status, reason, pages, bytes, duration_ms, attempt, http_status, exc_type, where, child, rss_kb, version, binding, enabled, companion, cancelled_tasks`. `where` ist `modul:zeile` des innersten eigenen Rahmens.
- PHP-Kontextschlüssel in Logger-Aufrufen: `jobId, fileId, status, reason, app, exception, class`.

## Geschlossene Listen (PHP string-backed `enum` in `php/lib/Model/`, Python `StrEnum` in `backend/src/pii_redaction_backend/model.py`)

- `Status`: `queued, analyzing, review, submitted, approved, applying, verified, published, failed, stale, cancelled, expired`
- `Reason`: `encrypted_pdf, unsupported_format, too_many_pages, out_of_memory, repeatedly_stuck, leak_detected, check_error, original_changed, original_deleted, target_not_writable, backend_state_lost, download_blocked, not_readable, render_failed, backend_unavailable`
- `Stage`: `waiting, fetching, converting, rendering, done`
- `Task`: `analyze, apply, purge`
- `Mode`: `redact, pseudonymize`
- `Subject` (Benachrichtigung): `review_ready, job_failed, job_stale, copy_created`
- `Lang`: `de, en, fr` (Ableitung: Nutzersprache beginnt mit `de` ergibt `de`, mit `fr` ergibt `fr`, sonst `en`)
- `AckResult` (nur Python und QueueController): `review, verified, purged, failed`
- `Recheck` (nur PHP, `php/lib/Model/Recheck.php`): `ok, missing, download_blocked, changed`

## Tabellen (Migration `php/lib/Migration/Version000100Date20261107000000.php`)

`pii_jobs`: `id` BIGINT PK autoincrement, `file_id` BIGINT, `initiator_uid` STRING(64), `file_etag` STRING(40), `mode` STRING(16), `lang` STRING(8), `status` STRING(16), `reason` STRING(32) NULL, `task` STRING(16) NULL, `stage` STRING(16) NULL, `pages_done` INT NULL, `pages_total` INT NULL, `claim_token` STRING(64) NULL, `lease_until` BIGINT NOT NULL default 0, `attempts` SMALLINT NOT NULL default 0, `revision` INT NULL, `revision_hash` STRING(64) NULL, `output_sha256` STRING(64) NULL, `output_size` BIGINT NULL, `output_file_id` BIGINT NULL, `image_width` INT NULL, `image_height` INT NULL (Pixelmaß von Seite 1, für `width`/`height` des Bildes), `created_at` BIGINT, `updated_at` BIGINT, `expires_at` BIGINT. Indizes `pii_jobs_file` (`file_id`), `pii_jobs_queue` (`task`, `status`, `id`), `pii_jobs_uid` (`initiator_uid`).

`pii_job_events`: `id` BIGINT PK, `job_id` BIGINT, `uid` STRING(64), `action` STRING(32) (Werte aus `Status`/`Subject`/`placeholder_requested`), `at` BIGINT. Index `pii_events_job` (`job_id`).

`pii_slot`: `id` SMALLINT PK (immer 1), `job_id` BIGINT NULL, `claim_token` STRING(64) NULL, `lease_until` BIGINT NOT NULL default 0. Zeile 1 wird von `JobMapper::ensureSlot()` angelegt (Insert, eindeutige Verletzung wird geschluckt).

Verboten in allen `pii_*`-Tabellen (Gate in `test_php_gates.py`): Spaltennamen, die `name`, `path`, `mime`, `text`, `value`, `snippet`, `title`, `comment`, `content` enthalten.

## PHP-Routen

| Verb | URL | Attribut | Antwort |
|---|---|---|---|
| POST | `/apps/pii_redaction/api/v1/jobs` `{fileId}` | `FrontpageRoute`, `NoAdminRequired` | 201 neu / 200 offen: `{jobId, status, ahead, reviewUrl}`; Fehler `{reason}` mit 503 `backend_unavailable`, 403 `download_blocked`, 404 `not_readable`, 415 `unsupported_format` |
| GET | `/apps/pii_redaction/api/v1/jobs/{jobId}` | `FrontpageRoute`, `NoAdminRequired`, `NoCSRFRequired` | `{jobId, status, stage, reason, ahead, pagesDone, pagesTotal, backendReady, outputFileId, outputName}` mit `Cache-Control: private, no-store`; 404 ohne Namen |
| GET | `/apps/pii_redaction/review/{jobId}` | `FrontpageRoute`, `NoAdminRequired`, `NoCSRFRequired` | `TemplateResponse('pii_redaction', 'review')` + `IInitialState` `review`; 404-Zustand ohne Dateinamen |
| GET | `/apps/pii_redaction/review/{jobId}/page/{n}` | dito, `n` `\d{1,3}` | PNG, `no-store`, `nosniff`; 404/403/409/502 |
| POST | `/apps/pii_redaction/review/{jobId}/placeholder` | `FrontpageRoute`, `NoAdminRequired` | 202 `{status: approved}`; 409 `{reason}` wenn nicht `review` oder Backend nicht bereit |
| GET | `/apps/pii_redaction/admin/state` | `FrontpageRoute` (Admin) | Zustand wie AVS `SettingsController::state` |
| POST | `/ocs/v2.php/apps/pii_redaction/api/v1/queue/claim` | `ApiRoute`, `ExAppRequired`, `NoCSRFRequired` | `{jobId, task, token, fileId, userId, etag, leaseSeconds}` oder `{}` |
| POST | `/ocs/v2.php/apps/pii_redaction/api/v1/queue/{jobId}/progress` `{token, stage, pagesDone, pagesTotal}` | dito | `{ok: true}`; 409 bei fremdem Token oder ungültigem Auftrag; 400 bei Wert außerhalb der Liste |
| POST | `/ocs/v2.php/apps/pii_redaction/api/v1/queue/{jobId}/ack` `{token, result, reason?, pagesTotal?, etagSeen?, image?: {width, height}, output?: {sha256, size}}` | dito | `{ok: true}`; 409/400 wie oben |
| GET | `/ocs/v2.php/apps/pii_redaction/api/v1/handshake` | dito | `{version}` (AVS) |
| GET | `/ocs/v2.php/apps/pii_redaction/api/v1/files/{jobId}?token=` | dito | Datei-Strom, Header `X-Pii-Etag`; 403 fremde ExApp, 404 Auftrag/Token/Lease ungültig, 409 Etag geändert |

Jede `ExAppRequired`-Methode beginnt mit `$foreign = $this->rejectForeignCaller();` (Gate-Regel 1).

## Signierte Container-Endpunkte (nicht in `info.xml`)

| Verb | Pfad | Antwort |
|---|---|---|
| GET | `/status` | `{version, ready, companion, busy, lastChild: {kind, rssKb, ms} \| null}` |
| GET | `/jobs/{job_id}/pages/{n}.png` | PNG oder 404 |
| GET | `/jobs/{job_id}/output` | PDF-Strom oder 404 (nur Zustand `verified`) |

## Zustandsübergänge (nur über `JobService`, `php/lib/Service/JobService.php`)

`queued -claim-> analyzing -ack(review)-> review -placeholder-> approved -claim-> applying -ack(verified)-> verified -PublishJob-> published`; Seitenwege: `failed(reason)`, `stale(original_changed)`, `cancelled(original_deleted)`; nach jedem Endzustand außer `review` setzt `JobService` `task = purge`. Benachrichtigungen: `review` ergibt `review_ready`, `failed` ergibt `job_failed`, `stale` ergibt `job_stale`, `published` ergibt `copy_created`, `cancelled` keine.

## Python-Module (`backend/src/pii_redaction_backend/`)

`__init__.py`, `main.py`, `config.py`, `settings.py`, `logs.py`, `model.py`, `nc.py` (einziger HTTP-Ort: `claim`, `progress`, `ack`, `handshake`, `fetch_source`), `companion.py`, `resources/{hardware,memory_guard}.py`, `workers/{child,render,soffice,placeholder,sniff}.py`, `store/{schema.sql,repo.py}`, `runner/runner.py`, `api/{__init__,status,pages,output}.py`.

## Testnutzer (CI-Saat)

`alice` (en, Auftraggeberin), `bob` (en, fremd), `carol` (en, Gruppenordner mit ACL `-read`), `dora` (en, Admin), `elke` (`de_DE`), `greta` (`de`), `fleur` (`fr`); Freigabe von alice an bob mit Download-Sperre.

## Stack Touched in Phase 1

- [ ] Gerüst: `php/` (composer, phpunit, Vite), `backend/` (uv, ruff, pyright, vulture, pytest), Workflows
- [ ] Routen: PHP-Seiten und OCS wie oben; Container nur signiert
- [ ] Datenbank: Migration, Claim mit Sperrzeile, Ereignisse; Container `state.db` ohne Text
- [ ] UI: Dateiaktion, Platzhalter-Prüfseite, Benachrichtigung, Admin-Statusbereich
- [ ] Deployment: `deploy-harp.yml` 6 Beine + MariaDB-Bein, Upgrade, Drift, Kanarie, Messung

## Out of Scope

Echte Erkennung, Positionsindex, Sandbox in voller Härte und Ablehnung mit Grund (JOB-05), Vier-Augen, TTL-Durchsetzung, Protokoll, Netzfreiheitsbeweis, Store-Upload.
