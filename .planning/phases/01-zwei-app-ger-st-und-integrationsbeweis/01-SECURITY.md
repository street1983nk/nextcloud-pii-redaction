---
phase: 01
slug: zwei-app-ger-st-und-integrationsbeweis
status: open
threats_open: 0
asvs_level: 2
created: 2026-11-15
audited_commit: 7f71f9e
branch: main
---

# Phase 01: Security

> Sicherheitsvertrag der Phase: Bedrohungsregister, akzeptierte Risiken und Prüfverlauf.
> Rückwirkendes Audit gegen HEAD 7f71f9e (Branch main, identisch mit origin/phase-01). Plan 01-20 (Abnahme) läuft noch.
> Die Pläne deklarieren ASVS L1 mit block_on high; dieses Audit prüft mit asvs_level 2 laut Auftrag.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Paketregister nach Build | PyPI, npm, Packagist liefern Code in Image und CI | Fremdcode (hoch) |
| CI-Workflows nach Repo | Workflows laufen mit Repo-Rechten, Release mit Signaturschlüsseln | Secrets, Signaturen (hoch) |
| Browser nach PHP | Sitzung plus CSRF, `fileId` und `jobId` vom Nutzer | Auftrags-IDs, Dateiname nur für den Auftraggeber (mittel) |
| PHP nach Container | signierte AppAPI-Aufrufe; Antworten sind nicht vertrauenswürdig | PNG, Ausgabe-PDF, Status-JSON (hoch) |
| Container nach PHP-OCS | signierte, aber nicht vertrauenswürdige Meldungen; Claim, Lease und Token entscheidet nur PHP | Dokumentinhalt über das Gateway (hoch) |
| Fremde ExApp nach PHP-OCS | andere ExApps derselben Instanz können OCS-Routen mit eigener Signatur rufen | Dokumentinhalt (hoch) |
| Fremde Datei nach Parser | PDF/DOCX/ODT aus Nutzerdaten erreichen C-Code (MuPDF, LibreOffice) im Kindprozess | Dokumentinhalt (hoch) |
| Quelltext nach Logs | Python- und PHP-Logzeilen verlassen die Anwendung | nur IDs, Klassen, Zustände (hoch) |
| PHP nach Push-Proxy | Benachrichtigungstext verlässt den Server | nur feste Sätze (mittel) |
| Artefakte nach GitHub | Logs, Screenshots, Messwerte aus CI | synthetische Daten (mittel) |
| Lokales Repo nach GitHub | Push veröffentlicht Code | Quelltext, mögliche Geheimnisse (hoch) |

---

## Threat Register

Beleg-Konvention: Pfade relativ zum Repo-Wurzelverzeichnis, `Datei:Zeile`. Lokal gelaufen am 2026-11-15: 312 Gate- und Einheitstests aus `backend/tests` grün, 3 übersprungen (Prozessgruppen nur POSIX, laufen in CI).

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-SC | Tampering (high) | npm-, PyPI-, Packagist-Pakete | mitigate | npm: exakte Pins plus `php/package-lock.json`, `ci/playwright/package-lock.json`, `npm ci --ignore-scripts` (`.github/workflows/php.yml:57`, `deploy-harp.yml:248`, `release.yml:186`); PyPI: `backend/uv.lock`, `uv run --frozen`. Packagist seit 15.11.2026 mit eingecheckter Lockdatei `php/composer.lock` (27 Dev-Pakete, 0 Laufzeitpakete); php.yml erzwingt den Lock (validate --strict, install --dry-run, audit --locked), phpunit-Job installiert dagegen; dazu exakter Pin `phpunit/phpunit 11.5.57` und `--no-scripts` | closed |
| T-01-01-01 | Tampering | php.yml, docker.yml | mitigate | alle `uses:` per 40-stelligem SHA mit Versionskommentar (grep über `.github/workflows/*.yml` ohne Treffer für bewegliche Referenzen), Gate `backend/tests/test_workflow_pins.py:283` | closed |
| T-01-01-02 | Elevation of Privilege | Workflows | mitigate | `permissions: contents: read` in `php.yml:27`, `python.yml:15`, `deploy-harp.yml:50`, `docker.yml:24`, `security.yml:12`, `release.yml:34`; Test-Workflows ohne `secrets.`; `packages: write` nur in `docker.yml:39-41` (Build/Push, nur main, Tags, Zeitplan) | closed |
| T-01-01-03 | Elevation of Privilege | Container-Routen | mitigate | `backend/appinfo/info.xml:75` `<routes/>`, Gate `backend/tests/test_store_metadata.py:135` plus Selbsttest `:144` | closed |
| T-01-01-04 | Information Disclosure | Repo | mitigate | `backend/tests/test_public_artifacts.py:37,43,53` (grün), `.gitignore:26-31` (`*.key`, `*.pem`, `*.p12`, `*.csr`, `.env*`), Build-Ausgaben `.gitignore:12-22` | closed |
| T-01-02-01 | Information Disclosure | pii_* Tabellen | mitigate | `php/lib/Migration/Version000100Date20261107000000.php:45-111` ohne Namens-, Pfad-, Text- oder MIME-Spalte; Gates `backend/tests/test_php_schema.py:157` und `test_php_gates.py:567` (Regel 13) | closed |
| T-01-02-02 | Tampering | Status-/Grundwerte | mitigate | `php/lib/Db/Job.php:114-116` wirft bei fremdem Wert; `tryFrom` für Reason/Task/Stage/Mode/Lang `Job.php:123-149` | closed |
| T-01-02-03 | Denial of Service | Warteschlange | mitigate | `php/lib/Db/JobMapper.php:47` `MAX_ATTEMPTS = 3`, `:187-188` giveUp, `:414-427` `repeatedly_stuck`, Lease-Bedingungen `:290,306,388` | closed |
| T-01-02-04 | Spoofing | Claim-Token | mitigate | `php/lib/Db/JobMapper.php:448-450` `bin2hex(random_bytes(16))`; Token als Mapper-Bedingung `:220,239,435`; `hash_equals` in `QueueController.php:276`, `GatewayController.php:134` | closed |
| T-01-02-05 | Tampering | zwei gleichzeitige Claims | mitigate | bedingtes UPDATE der Sperrzeile und der Auftragszeile mit `lease_until <= now` (`JobMapper.php:373-393`), Rücklesen per Token `JobMapper.php:429-437` | closed |
| T-01-03-01 | Information Disclosure (high) | Python-Logs | mitigate | AST-Gate `backend/tests/test_log_calls.py:140` mit Selbsttests `:161,168,173,179`; Formatter schreibt nur Literal, Allowlist und `exc_type`/`where` (`backend/src/pii_redaction_backend/logs.py:80-98`) | closed |
| T-01-03-02 | Information Disclosure | PHP-Logs | mitigate | Regeln 6, 14, 15 in `backend/tests/test_php_gates.py:514,572,577`; 0 Treffer für `getMessage(` und `'exception' =>` in `php/lib`. Siehe Escalation E-01 zur Allowlist | closed |
| T-01-03-03 | Elevation of Privilege (high) | Routen ohne Recheck | mitigate | Regel 12 `test_php_gates.py:308-309,558` mit Selbsttest `:724`; jede FrontpageRoute ruft `recheck*` (`JobController.php:67,103`, `ReviewController.php:73,136,169`), Gateway `GatewayController.php:79` | closed |
| T-01-03-04 | Elevation of Privilege | Container-Aufruf außerhalb ExAppService | mitigate | Regel 3 `test_php_gates.py:500`, Selbsttest `:641`; einziger `exAppRequest` in `php/lib/Service/ExAppService.php:452` | closed |
| T-01-03-05 | Information Disclosure | Benachrichtigungstext | mitigate | Regel 17 `test_php_gates.py:585`; feste Sätze ohne Platzhalter `php/lib/Notification/Notifier.php:52-57` | closed |
| T-01-03-06 | Repudiation | Gate ohne Wirkung | mitigate | Selbsttest je Regel `test_php_gates.py:627-782` (`test_self_rule1` bis `rule20`), `test_log_calls.py:155-183` | closed |
| T-01-04-01 | Elevation of Privilege (high) | FileAccess::recheck | mitigate | `php/lib/Service/FileAccess.php:90-135`: `actAs($uid)` plus `readableFile` im Nutzerordner je Anfrage, nichts gespeichert | closed |
| T-01-04-02 | Information Disclosure (high) | Download-Sperre | mitigate | `FileAccess.php:69-85`: `ISharedStorage`, `getHideDownload()`, Attribut `permissions/download`, jede Ausnahme ergibt gesperrt (`:81-83`) | closed |
| T-01-04-03 | Tampering (high) | Container-Antworten | mitigate | `ExAppService.php:55-58` Deckel 16 MiB bzw. 1 MiB und PNG-Magic, Status 200 `:154,189`, Magic-Prüfung `:160`, JSON-Objektprüfung `:501-503`, `boundedBody` `:521` | closed |
| T-01-04-04 | Spoofing (high) | Handshake | mitigate | `php/lib/Controller/HandshakeController.php:41` `ExAppRequired`, `:58-69` Vergleich `EX-APP-ID === BACKEND_APP_ID` | closed |
| T-01-04-05 | Denial of Service | Container hängt | mitigate | `ExAppService.php:48,50,52` (1,5 s / 10 s / 120 s), übergeben als `timeout` `:458` | closed |
| T-01-04-06 | Information Disclosure | Logs | mitigate | ExAppService-Logs nur `jobId`, `status`, `class` (`ExAppService.php:151-190,269,492-504`) | closed |
| T-01-05-01 | Information Disclosure (high) | Kindumgebung | mitigate | `backend/src/pii_redaction_backend/workers/child.py:24-29` `SAFE_ENV`, Allowlist `:33`, `env=child_env(...)` `:80`; Test liest `os.environ` im Kind `backend/tests/test_child.py:53` | closed |
| T-01-05-02 | Denial of Service | hängender Parser | mitigate | `child.py:84` `start_new_session=True`, `:87` `wait_for(timeout)`, `:105` `os.killpg(SIGKILL)`; Enkelprozess-Test `test_child.py:48-77` (POSIX, läuft in CI) | closed |
| T-01-05-03 | Tampering | falsch benannte Datei | mitigate | `backend/src/pii_redaction_backend/workers/sniff.py:22-40` Magic-Bytes; Aufruf `runner/runner.py:413` | closed |
| T-01-05-04 | Information Disclosure (high) | Platzhalter mit Originalinhalt | mitigate | `workers/placeholder.py:1-6,31-33`: Argumente nur Ausgabepfad und Auftragsnummer, keine Quelle; Aufruf `runner/runner.py:327`; Test `backend/tests/test_placeholder.py` | closed |
| T-01-05-05 | Elevation of Privilege | LibreOffice-Makros/Netz | accept | siehe Accepted Risks AR-01; Nicht-Root belegt `backend/Dockerfile:95` `USER 10001:10001`, leere Umgebung `child.py:24-29` | closed |
| T-01-05-06 | Information Disclosure | Kind-Ausgaben in Logs | mitigate | `child.py:81-83` stdin/stdout/stderr `DEVNULL`; `ChildFailed` trägt nur den Exit-Code `child.py:41-46` | closed |
| T-01-06-01 | Information Disclosure (high) | logs.py | mitigate | `logs.py:31-53` Allowlist, `:86` nur Literal, `:92-97` nur Typ und Rahmen; Kanarien-Test `backend/tests/test_logs.py:108`, `formatException` nie gerufen `:149` | closed |
| T-01-06-02 | Tampering | Claim-Antwort | mitigate | `backend/src/pii_redaction_backend/nc.py:171-195,244-247` Typ-, Enum-, Längen- und Tokenprüfung (`_TASKS`, `_TOKEN.fullmatch`, `_ETAG_MAX`, `_USER_MAX`) | closed |
| T-01-06-03 | Denial of Service | Quelldownload | mitigate | `nc.py:521-537` `.part` plus `os.replace`, `max_bytes` gegen `config.MAX_SOURCE_BYTES` (`config.py:28`, `runner.py:271`), `follow_redirects=False` `nc.py:163,270,488,553` | closed |
| T-01-06-04 | Information Disclosure (high) | APP_SECRET | mitigate | nur in `app_api_headers` `nc.py:141-146`; nicht in `ALLOWED_EXTRA` (`logs.py:31-53`); Kinder ohne Secret `child.py:24-29`, Test `test_child.py:37` | closed |
| T-01-06-05 | Denial of Service | RAM | mitigate | `backend/src/pii_redaction_backend/resources/memory_guard.py:98-110` unlesbar ergibt nein; Aufruf vor Claim `runner.py:172` | closed |
| T-01-07-01 | Information Disclosure (high) | Push | mitigate | `test_public_artifacts.py` grün auf 7f71f9e; keine Schlüsseldateien im Index (`.gitignore:26-31`); Owner-Freigabe ist Prozess, im Repo nicht prüfbar (SUMMARY-Beleg) | closed |
| T-01-07-02 | Repudiation | Commit-Identität | mitigate | `git log`: 136 Commits `street1983nk <k.cherif@outlook.de>`, sonst nur dependabot; 0 Claude-Session-/Co-Authored-By-Zeilen | closed |
| T-01-07-03 | Tampering | main | mitigate | Reflog `origin/phase-01`: 17 Updates, alle Fast-Forward (`git merge-base --is-ancestor`), kein Force; origin/main nur durch zwei Owner-Commits vom 09.11. (Fast-Forward von 1f95af7) | closed |
| T-01-08-01 | Elevation of Privilege (high) | Start mit fremder fileId | mitigate | `php/lib/Controller/JobController.php:67` `recheckForStart($uid, ...)`, `FileAccess.php:109-135` | closed |
| T-01-08-02 | Information Disclosure (high) | IDOR auf `/jobs/{id}` | mitigate | `JobService.php:166-176` nur Auftraggeber; `JobController.php:103-110,128-132` einheitliches 404 ohne Body | closed |
| T-01-08-03 | Information Disclosure (high) | Kopie trotz Download-Sperre | mitigate | `JobService.php:75-77` Start mit `download_blocked` abgelehnt; fail closed `FileAccess.php:81-83` | closed |
| T-01-08-04 | Tampering | veraltetes Original | mitigate | Etag beim Start `JobService.php:84,111`; Abweichung ergibt `stale` `JobService.php:283-288` | closed |
| T-01-08-05 | Spoofing | CSRF auf Start | mitigate | `JobController.php:59-60` POST ohne `NoCSRFRequired`; Frontend `php/src/startToast.ts:5,71` `@nextcloud/axios` | closed |
| T-01-08-06 | Information Disclosure | Statusantwort im Cache | mitigate | `JobController.php:139-142` `Cache-Control: private, no-store` | closed |
| T-01-08-07 | Denial of Service | Doppelstarts | mitigate | `JobService.php:103-115` `RetriedTransaction` mit `findOpenFor` | closed |
| T-01-09-01 | Tampering | XSS über Dateinamen | mitigate | kein `v-html`/`innerHTML`/`isHTML`/`eval` in `php/src` (grep 0 Treffer); Toast aus Textknoten `startToast.ts:24-34`; Gate `backend/tests/test_ui_assets.py:159,163` mit Selbsttest `:328` | closed |
| T-01-09-02 | Spoofing | CSRF Start und Platzhalter | mitigate | `@nextcloud/axios` in `startToast.ts:5`, `ReviewPlaceholder.vue:145,431` | closed |
| T-01-09-03 | Information Disclosure | Dateiname in Toast | mitigate | Toast-Sätze ohne Namen `startToast.ts:47-61,83,90` | closed |
| T-01-09-04 | Tampering | Lieferkette npm | mitigate | exakte Pins `php/package.json`, `ci/playwright/package.json:11`, Lockdateien, `npm ci --ignore-scripts` (s. T-01-SC) | closed |
| T-01-09-05 | Elevation of Privilege | Aktion als Sicherheitsgrenze | accept | siehe AR-02; PHP prüft erneut `JobController.php:67` | closed |
| T-01-10-01 | Elevation of Privilege (high) | Container-Endpunkte | mitigate | `backend/appinfo/info.xml:75` `<routes/>`; `main.py:110` `AppAPIAuthMiddleware`; Test 401 `backend/tests/test_api_routes.py:73-74`; Smoke-Test `docker.yml` erwartet 401 auf unsigniertes `/status` | closed |
| T-01-10-02 | Tampering (high) | Pfad-Traversal `job_id`/`n` | mitigate | `backend/src/pii_redaction_backend/api/pages.py` int-Parameter, `n != 1` ergibt 404, fester `PAGE_FILE`; `api/output.py` int `job_id`, fester `OUTPUT_FILE` | closed |
| T-01-10-03 | Denial of Service | zwei Aufträge gleichzeitig | mitigate | `runner/runner.py:126` `asyncio.Semaphore(1)`; PHP-Sperrzeile `JobMapper.php:177-178` | closed |
| T-01-10-04 | Denial of Service | Speicher | mitigate | `runner.py:172` `admit("soffice")` vor Claim | closed |
| T-01-10-05 | Information Disclosure | Zugriffslog mit Pfaden | mitigate | `main.py:126` `access_log=False`; `logs.py:112-114` Logger deaktiviert; Test `test_logs.py:175` | closed |
| T-01-10-06 | Information Disclosure (high) | Ausgabe vor Prüfung | mitigate | `api/output.py` `_verified_output`: nur mit `output_sha256` in `state.db` | closed |
| T-01-11-01 | Elevation of Privilege | `/admin/state` | mitigate | `php/lib/Controller/SettingsController.php:50` ohne `NoAdminRequired`; Reflection-Test `php/tests/Unit/SettingsControllerTest.php:112-117` | closed |
| T-01-11-02 | Information Disclosure | Banner | mitigate | `php/templates/admin.php`: nur Zustand, Versionen, Prüfzeit | closed |
| T-01-11-03 | Tampering | XSS im Template | mitigate | `admin.php` gibt nur über `p()` aus, kein Inline-Skript; Gate `test_ui_assets.py:142,150` | closed |
| T-01-12-01 | Spoofing (high) | fremde ExApp | mitigate | `rejectForeignCaller()` als erste Anweisung jeder ExApp-Route: `QueueController.php:76,108,159,318-329`, `GatewayController.php:66,163-175`, `HandshakeController.php:45`; Regel 1 `test_php_gates.py:491` | closed |
| T-01-12-02 | Elevation of Privilege (high) | übernommener Container liest fremde Dateien | mitigate | `GatewayController.php:124-141` Token per `hash_equals`, Zustand `analyzing`, lebende Lease; `:79` Recheck als Auftraggeber mit gespeichertem Etag; nur `fopen('rb')` `:103` | closed |
| T-01-12-03 | Tampering | gefälschte Status/Gründe/Zähler | mitigate | `QueueController.php:113-115` `Stage::tryFrom`, `:239-241` `Reason::tryFrom`, Bereiche `:283-293`, 400 `:295-297` | closed |
| T-01-12-04 | Tampering (high) | gefälschte Ausgabe-Prüfsumme | mitigate | `QueueController.php:224-226` sha256-Form und Größendeckel; `PublishService.php:73-77` Vergleich des Stroms gegen `ack` | closed |
| T-01-12-05 | Information Disclosure | Dateiname in Gateway-Kopfzeilen | mitigate | `GatewayController.php:114-117` nur `Content-Type` und `X-Pii-Etag`; kein `Content-Disposition` in `php/lib` (grep 0) | closed |
| T-01-12-06 | Tampering | veraltetes Original | mitigate | Gateway 409 und `stale` `GatewayController.php:90-93`; ack `QueueController.php:197-207` | closed |
| T-01-13-01 | Information Disclosure (high) | IDOR auf Prüfseite/Bild | mitigate | `ReviewController.php:73-75,136-138` `recheckMember` je Anfrage, einheitliches 404 `:238-243,262-266` | closed |
| T-01-13-02 | Elevation of Privilege (high) | entzogenes Recht | mitigate | kein gespeichertes Recht; `JobService.php:183-186,283-288` Recheck je Anfrage | closed |
| T-01-13-03 | Information Disclosure (high) | Bild trotz Download-Sperre | mitigate | `ReviewController.php:143-145` 403 bei `DownloadBlocked` | closed |
| T-01-13-04 | Information Disclosure | Bild im Browser-Cache | mitigate | `ReviewController.php:277-281` `private, no-store` | closed |
| T-01-13-05 | Tampering | Content-Sniffing | mitigate | `ReviewController.php:279` `nosniff`; PNG-Magic `ExAppService.php:160` | closed |
| T-01-13-06 | Spoofing | CSRF auf Platzhalter | mitigate | `ReviewController.php:165-166` POST ohne `NoCSRFRequired` | closed |
| T-01-13-07 | Tampering | XSS | mitigate | `php/templates/review.php` nur Mountpunkt ohne Nutzerdaten; Titel über `l10n->t` im Layout; Gate `test_ui_assets.py:142,150,159` | closed |
| T-01-14-01 | Information Disclosure (high) | Benachrichtigung über Push | mitigate | `Notifier.php:52-59` feste Sätze; Regel 17 `test_php_gates.py:585`; `php/tests/Unit/NotifierTest.php`; Playwright `ci/playwright/notification.spec.ts:84` | closed |
| T-01-14-02 | Tampering | ausgetauschte Ausgabe | mitigate | `PublishService.php:32,139-175` Deckel 32 MiB, Hash beim Kopieren, `:73-77` Abgleich gegen `ack` | closed |
| T-01-14-03 | Tampering (high) | Überschreiben fremder Dateien | mitigate | `PublishService.php:114-118` `getNonExistingName` plus `newFile`; Regel 18 `test_php_gates.py:590` | closed |
| T-01-14-04 | Elevation of Privilege (high) | Ablage ohne Recht | mitigate | `PublishService.php:96-113` `resolve` als Auftraggeber, `actAs`, Download-Sperre, `isCreatable()` | closed |
| T-01-14-05 | Tampering | geändertes Original | mitigate | `php/lib/AppInfo/Application.php:39-40` Listener; `PublishService.php:104-106` Etag-Prüfung vor der Ablage | closed |
| T-01-14-06 | Denial of Service | gekoppelte Laufzeiten | mitigate | `QueueController.php:233-234` `jobList->add(PublishJob::class)` statt Schreiben im `ack` | closed |
| T-01-15-01 | Information Disclosure | Artefakte | mitigate | synthetische Fixtures `ci/make_fixtures.py`; Kanarien-Schritt vor dem Upload (`deploy-harp.yml` Kopfkommentar und Schrittfolge), Upload ohne Dumps `deploy-harp.yml:684-694` | closed |
| T-01-15-02 | Tampering | Actions, Dienstcontainer | mitigate | Actions per SHA (s. T-01-01-01); MariaDB per Digest `deploy-harp.yml:126` | closed |
| T-01-15-03 | Elevation of Privilege | Workflow-Rechte | mitigate | `deploy-harp.yml:50-51` `contents: read`, keine `secrets.` in `deploy-harp.yml` | closed |
| T-01-15-04 | Repudiation | stiller Fehlschlag | mitigate | `set -euo pipefail` in allen 11 `ci/*.sh` | closed |
| T-01-16-01 | Tampering | `@playwright/test` | mitigate | `ci/playwright/package.json:11` `1.65.0` exakt, Lockdatei, `npm ci --ignore-scripts` `deploy-harp.yml:432` | closed |
| T-01-16-02 | Information Disclosure | Screenshots | mitigate | `ci/playwright/helpers.ts:17` Kanarie; Assertionen in `notification.spec.ts:8,84` | closed |
| T-01-16-03 | Repudiation | geschönte Screenshots | mitigate | `helpers.ts:587-615` `forgeState`/`forgeStatus` mit Laufzeitprüfung gegen die geschlossene Liste; Vertragstest `backend/tests/test_playwright_contract.py` | closed |
| T-01-17-01 | Repudiation | wertloser Kanarien-Scan | mitigate | `ci/canary.sh:5-8,60` Positivkontrolle zuerst | closed |
| T-01-17-02 | Information Disclosure (high) | Klartext in DB/Logs | mitigate | `ci/canary.sh:19-23` Dumps, state.db, Logs, Kopien | closed |
| T-01-17-03 | Elevation of Privilege (high) | Browser-Route am Container | mitigate | `ci/routes.sh:4-6,9,25-28` 404 als alice und dora, unsigniert nicht 200, Positivkontrolle; `deploy-harp.yml:385-386,424` | closed |
| T-01-17-04 | Elevation of Privilege (high) | Rechte nach Entzug | mitigate | `ci/rights.sh:7-16,109,118` ACL, Sperre, Entzug im echten Lauf | closed |
| T-01-17-05 | Tampering | zwei Aufträge gleichzeitig | mitigate | `ci/queue.sh:8-11,26` Stichproben auf SQLite und MariaDB | closed |
| T-01-17-06 | Information Disclosure | Dumps als Artefakt | mitigate | `deploy-harp.yml:691-692,1129-1130` Ausschluss `*.sql`, `*-dump.*` | closed |
| T-01-18-01 | Information Disclosure (high) | Signaturschlüssel | mitigate | `release.yml:213,294` nur aus Secret, `umask 077`, unter `RUNNER_TEMP`; Löschschritt `if: always()` `release.yml:349-356`, `store-submit.yml:140-142`; `.gitignore:26-29`; Gate `test_public_artifacts.py:37` | closed |
| T-01-18-02 | Tampering | Archiv-Inhalt | mitigate | `scripts/release/store-archive.sh:84` `cmp` Backend-info.xml; `release.yml:214-218` `integrity:sign-app`; Tag-Prüfung `release.yml:129-140` | closed |
| T-01-18-03 | Elevation of Privilege | alte Routen nach Update | mitigate | `<routes/>` (s. T-01-01-03); `deploy-harp.yml:1094` `ci/routes.sh` nach dem Upgrade | closed |
| T-01-18-04 | Denial of Service | Upgrade löscht Zustand | mitigate | `deploy-harp.yml:1012-1013,1065-1086` Volume-CreatedAt, Inode, `cmp` von Auftragszeile und Volume | closed |
| T-01-18-05 | Spoofing | Lockstep als Schutz | accept | siehe AR-03; Schutz über `AppAPIAuthMiddleware` (`main.py:110`) und `ExAppRequired` plus `EX-APP-ID` (T-01-12-01) | closed |
| T-01-19-01 | Information Disclosure | Doku | mitigate | `test_public_artifacts.py` grün auf 7f71f9e | closed |
| T-01-19-02 | Repudiation | falsche Produktversprechen | mitigate | `README.md:12,19` Stand 0.1.0 ohne Erkennung und ohne Schwärzung | closed |
| T-01-20-01 | Information Disclosure (high) | Push | mitigate | wie T-01-07-01; Stand 7f71f9e auf origin/phase-01 ohne Schlüsselmaterial (Gate grün). Plan 01-20 läuft noch | closed |
| T-01-20-02 | Repudiation | Commit-Identität | mitigate | wie T-01-07-02 (geprüft bis 7f71f9e) | closed |
| T-01-20-03 | Tampering | main | mitigate | wie T-01-07-03; kein Merge von Phase-Commits nach origin/main | closed |
| T-01-20-04 | Tampering | heruntergeladene Artefakte | mitigate | Prozessregel `01-20-PLAN.md:43`; keine Artefakte im Index (`git status` sauber außer `.planning/debug/`); Ausführung im Repo nicht prüfbar | closed |
| T-01-21-01 | Information Disclosure (high) | Push | mitigate | wie T-01-07-01 | closed |
| T-01-21-02 | Repudiation | Commit-Identität | mitigate | wie T-01-07-02; Zähler verbotener Zeilen 0 | closed |
| T-01-21-03 | Tampering | main | mitigate | wie T-01-07-03 | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

Alle drei Einträge sind **abgeleitet aus Planfreigabe, Owner-Bestätigung ausstehend**. Sie stehen so in den freigegebenen Plänen (Severity medium bzw. low, also unter block_on high zulässig), eine ausdrückliche Bestätigung des Owners in dieser Datei fehlt noch.

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-05-05 | LibreOffice läuft in Phase 1 ohne vorbelegtes Profil (Makros, externe Verknüpfungen) und ohne eigene Netzsperre; volle Härtung ist Phase 2 (SAFE-01 bis SAFE-04). Phase 1 nur auf Testinstanzen, kein Store-Release, Nicht-Root, leere Umgebung. | Planfreigabe 01-05; Owner bestätigt 15.11.2026 | 2026-11-15 |
| AR-02 | T-01-09-05 | `enabled()` der Dateiaktion ist nur Komfort; jede Grenze prüft PHP erneut (Plan 08). | Planfreigabe 01-09; Owner bestätigt 15.11.2026 | 2026-11-15 |
| AR-03 | T-01-18-05 | Gleiche Versionsnummern beider Apps sind keine Authentisierung; der Schutz liegt in den signierten AppAPI-Aufrufen. | Planfreigabe 01-18; Owner bestätigt 15.11.2026 | 2026-11-15 |

---

## Unregistered Flags

Keine. Alle `## Threat Flags` der SUMMARYs 01-01 bis 01-19 und 01-21 melden keine neue Fläche oder verweisen auf registrierte IDs. 01-07-SUMMARY hat keinen Abschnitt `## Threat Flags`; 01-20-SUMMARY existiert noch nicht.

---

## Escalations (außerhalb des Registers)

Geprüft gegen die zwei Muster aus Audio & Video Search: (a) Python-Logs nie mit Exception-Text, (b) PHP-Logs nie mit `['exception' => $e]`, nur `['class' => $e::class]`.

- Muster (a): eingehalten. `logs.py:92-97` schreibt nur `exc_type` und `where`; kein `str(exc)`, `print`, `logger.exception` oder f-String mit Ausnahme in `backend/src` (grep 0).
- Muster (b): im Code eingehalten (0 Treffer für `'exception' =>`, `getMessage(`, `getTraceAsString` in `php/`).

| ID | Befund | Beleg | Vorschlag |
|----|--------|-------|-----------|
| E-01 | Das PHP-Log-Gate erlaubt den Kontextschlüssel `exception` und nimmt `['exception' => $e]` sogar als gutes Beispiel in den Selbsttest. Ein späterer Rückfall auf Muster (b) bliebe grün; Nextcloud schreibt bei diesem Schlüssel Nachricht und Trace ins Log. | `backend/tests/test_php_gates.py:77` (`LOG_CONTEXT_KEYS` enthält `"exception"`), `:742` (Selbsttest "good" mit `'exception' => $e`), Doku `:26` | BEHOBEN 15.11.2026: `exception` und `at` aus `LOG_CONTEXT_KEYS` gestrichen, Selbsttest prüft jetzt, dass beide feuern |
| E-02 | Ein Log-Kontext trägt neben der Klasse `getFile():getLine()` der Ausnahme. Das ist kein Ausnahmetext, aber ein absoluter Serverpfad, und bei Ausnahmen aus dem Server-Kern nicht "nur unser Code" wie der Kommentar sagt. Abweichung vom strikten Muster "nur class". | `php/lib/BackgroundJob/PublishJob.php:58`; erlaubt durch `test_php_gates.py:77` (`at`) | BEHOBEN 15.11.2026 (Owner "Entfernen"): PublishJob loggt nur noch jobId und class, `at` auch aus der Gate-Whitelist entfernt |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-15 | 103 | 102 | 1 | gsd-security-auditor (rückwirkend, HEAD 7f71f9e) |

T-01-SC GESCHLOSSEN 15.11.2026 (Owner-Entscheid Lock einchecken): `php/composer.lock` ist eingecheckt (aus dem gruenen Lauf 43724117413 geholt; 0 Laufzeitpakete, 27 Dev-Pakete, phpunit exakt 11.5.57); php.yml prueft jetzt Vorhandensein, Synchronitaet (validate --strict), Aufloesbarkeit (install --dry-run) und Advisories (audit --locked) gegen den Repo-Lock, und der phpunit-Job installiert gegen den Lock. Pin-Wechsel laufen ueber workflow_dispatch (frischer Lock als Artefakt).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (Owner-Bestätigung ausstehend)
- [x] `threats_open: 0` confirmed
- [ ] `status: verified` set in frontmatter

**Approval:** AR-01 bis AR-03 vom Owner einzeln bestätigt 15.11.2026; E-01 und E-02 behoben; T-01-SC geschlossen (Lock eingecheckt 15.11.2026).
