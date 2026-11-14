---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 18
subsystem: ci
tags: [deploy-harp, upgrade, drift, lockstep, companion, release, store-archive, loglevel]
requires: [01-15, 01-16, 01-17]
provides: [Upgrade-Job 0.0.1 nach 0.1.0, Drift-Schritte für sechs Admin-Zustände und die Gegenrichtung, ci/redeploy.sh, ci/admin-state.sh, zwei Store-Archive im Release-Workflow, Loglevel 1 im CI]
affects: [01-20]
tech-stack:
  added: []
  patterns: ["Drift-Schritte nach der Kanarie (Redeploy ersetzt den Container und damit sein Log)", "ci/admin-state.sh <name.json> [Zielzustand] wartet bis 120 s auf den Zustand", "Auftrag in die Warteschlange bei angehaltenem Container (docker pause), damit er vor dem Abschalten der PHP-App nicht gezogen wird"]
key-files:
  created: [ci/redeploy.sh, ci/admin-state.sh, backend/tests/test_release_archives.py]
  modified: [.github/workflows/deploy-harp.yml, .github/workflows/release.yml, scripts/release/store-archive.sh, ci/canary.sh, backend/tests/test_workflows.py, backend/tests/test_ci_scripts.py, backend/src/pii_redaction_backend/nc.py, backend/src/pii_redaction_backend/runner/runner.py, backend/src/pii_redaction_backend/api/status.py, backend/tests/test_runner.py, backend/tests/test_nc.py, backend/tests/test_api_routes.py]
decisions:
  - "Owner 14.11.2026: nextcloud.log im CI auf loglevel 1 (info), nur im Workflow, nie in der App, nicht debug; ci/canary.sh prüft per Positivkontrolle, dass Info-Zeilen der App im Log stehen"
  - "Drift-Schritte laufen nach ci/canary.sh; das Gate verlangt das jetzt ausdrücklich (Kanarie bleibt letzte Prüfung des Hauptlaufs)"
  - "Upgrade ohne veröffentlichte Vorversion: derselbe Commit per sed auf 0.0.1 (PHP-info.xml, Backend version und image-tag), ein Image unter beiden Tags"
  - "Ein Claim mit 403/404 löst sofort einen Handshake aus (nc.CompanionGone); /status frischt eine veraltete Companion-Antwort auf wie in AVS"
  - "Job-Timeout deploy-harp 120 statt 90 min (Drift-Schritte kommen dazu), in Plan 20 messen"
metrics:
  duration: "nicht erfasst"
  completed: 2026-11-14
  tasks: 2
  files: 15
---

# Phase 1 Plan 18: Upgrade-Job, Drift-Schritte und zwei Store-Archive Summary

Lockstep im Lebenszyklus: Ein Upgrade-Job hebt beide Apps von 0.0.1 auf 0.1.0 und beweist, dass Volume, state.db (gleiche Inode), Auftrag und Seitenbild bleiben und danach keine Browser-Route in den Container führt. Sieben Drift-Schritte erzeugen im echten Lauf alle sechs Admin-Zustände samt Banner (Playwright-Tags) und die Gegenrichtung (PHP-App aus, Container meldet companion missing und zieht keine Arbeit). Der Release-Workflow baut zwei Store-Archive. Lokal ist nichts davon gegen eine Instanz gelaufen; der echte Lauf ist Plan 20.

## Tasks

| Task | Name | Commit | Dateien |
|---|---|---|---|
| 1 (Abweichung) | RED: abgelehnter Claim fragt den Handshake | 0051635 | backend/tests/test_runner.py, backend/tests/test_nc.py |
| 1 (Abweichung) | GREEN: Container merkt die fehlende PHP-App in einer Runde | a31022c | nc.py, runner/runner.py |
| 1 (Abweichung) | RED: /status frischt die Companion-Antwort auf | 8762e3b | backend/tests/test_api_routes.py |
| 1 (Abweichung) | GREEN: /status fragt eine veraltete Antwort neu | 09823f7 | api/status.py |
| 1 | Upgrade-Job und Drift-Schritte in deploy-harp.yml | 90dc36d | deploy-harp.yml, ci/redeploy.sh, ci/admin-state.sh, ci/canary.sh, test_workflows.py, test_ci_scripts.py |
| 2 | RED: Archiv-Gate | af692f9 | backend/tests/test_release_archives.py |
| 2 | GREEN: zwei Store-Archive im Release-Workflow | f11f00f | scripts/release/store-archive.sh, release.yml, test_release_archives.py |

## Ergebnis

**Drift-Schritte (Job deploy-harp, nach ci/canary.sh):**
- Versionen aus `apps/pii_redaction/appinfo/info.xml` abgeleitet (`OWN_VERSION`, Patch `x.y.(z+1)`, Minor `x.(y+1).0`), `INFO_XML` und `fileids.env` in `GITHUB_ENV` (Pitfall 8).
- Grundlinie ok mit `companion ok`.
- Drift 1 Patch: `version_patch_differs`, Start auf frischer Kopie bis `review`, `--grep @patch` mit `PII_BACKEND_VERSION`.
- Drift 2 Minor: `version_drift`, `POST /api/v1/jobs` 503 `backend_unavailable`, `--grep @drift` mit `PII_BACKEND_VERSION`; Rückbau auf die eigene Version.
- Drift 3 `app_api:app:disable`: `backend_disabled`, 503, `@disabled`, wieder an, Zustand ok.
- Drift 4 `docker stop`: `backend_unreachable`, 503, `@unreachable`, `docker start`, Zustand ok.
- Drift 5 `app_api:app:unregister` ohne Datenflag: `backend_missing`, 503, `@missing`, Neuregistrierung, Zustand ok.
- Drift 6 `occ app:disable app_api`: `no_app_api`, 503, `@noappapi`, wieder an (falls AppAPI die ExApp deaktiviert zurücklässt, wird sie aktiviert), Zustand ok.
- Drift 7 Gegenrichtung: Positivkontrolle `"companion": "ok"` im Container-Log, frisches Urteil, Container per `docker pause` angehalten, Auftrag eingestellt (201), `occ app:disable pii_redaction`, `docker unpause`, binnen 60 s Logzeile `"companion": "missing"`, Positivkontrolle `"msg": "claim refused"`, 25 s später keine weitere abgelehnte Claim-Zeile, Auftrag in `oc_pii_jobs` `queued`. PHP-App wieder an, Admin-Zustand ok mit `companion ok`, derselbe Auftrag erreicht `review`.
- In jedem Fehlerzustand prüft der Schritt HTTP 503 und `reason == "backend_unavailable"`; `ci/admin-state.sh` ruft vorher die Route hinter "Erneut prüfen" auf, die den Zustand frisch bestimmt und speichert, sodass `startAllowed()` ihm folgt.

**Upgrade-Job (vier Beine: 33, 34, 35 amd64, 35 arm64):** Checkout von `nextcloud/viewer` im Zweig der Serverversion (Pitfall 7) und `nextcloud/notifications`. PHP-Bundle gebaut, `php-prev` per sed auf 0.0.1 (genau ein `<version>`), Backend-info.xml je Seite mit Registry, Version, image-tag und Pflicht auf `<routes/>`. Ein Image unter 0.0.1 und 0.1.0. Installation bei 0.0.1, Seed, Auftrag von alice bis `review`. Vorher festgehalten: Admin-Zustand ok bei 0.0.1, Zeile des Auftrags in `oc_pii_jobs`, Zeile in state.db plus sha256 von `page-1.png` (Positivkontrolle: beide existieren), `CreatedAt` des Volumes, Inode von state.db. Dann `occ upgrade` (Exit 0 oder 3, `installed_version` muss springen, Pitfall 9) und `app_api:app:update` (Image-Tag und `APP_VERSION` 0.1.0). Danach: Volume und Inode gleich, beide Zeilen und das Seitenbild per `cmp` gleich, Admin-Zustand ok bei 0.1.0, `ci/routes.sh` grün (Pitfall D), Prüfseite, Status (`review`) und PNG-Seitenbild des alten Auftrags 200.

**Owner-Entscheid 14.11.2026 (Loglevel):** `./occ config:system:set loglevel --value=1 --type=integer` im Installationsschritt von deploy-harp, nur dort. `ci/canary.sh` prüft als neuen Punkt 5, dass `loglevel` 1 ist und `nextcloud.log` mindestens eine Zeile mit `level 1` und Meldung `PII Redaction: ...` trägt (z. B. die abgelehnten Starts aus `ci/rights.sh`); sonst "positive control failed". Damit laufen die Info-Zeilen der App durch Kanarien- und Namenssuche. Gate: Loglevel 1 vor der Kanarie, nie `--value=0`, kein `loglevel` in `php/lib`.

**Store-Archive:** `stage-companion` bricht ohne oder mit leerem `php/js/pii_redaction-init.mjs` ab, bevor es kopiert; Include-Liste `appinfo lib templates js css img l10n` plus LICENSE und CHANGELOG.md, ohne `src/`, `node_modules/`, `tests/`. `stage-backend` verlangt genau ein `<routes/>` und keine `<route>` und kopiert info.xml byteidentisch (`cmp`). `assert-contents` verbietet zusätzlich `src`, `node_modules`, `package.json`, `vite.config.ts`, `tsconfig.json`, Schlüsselendungen `.p12`/`.csr`. release.yml: `npm ci --ignore-scripts` und `npm run build` in `php/` vor `stage-companion`, `occ integrity:sign-app`, zwei Release-Signaturen, Tag-Prüfung gegen beide info.xml und `<image-tag>`, Pin `4f61842e...` für `pii_redaction`, `pending-certificate` für das Backend mit dem Satz zu PR 1419 und dem lokal berechneten Pin `7a8c64ae...` als Kommentar ("nach Ausstellung von #1419 gegen das Zertifikat prüfen").

### Belege (lokal)

- Verify Task 1: `pytest tests/test_workflows.py tests/test_workflow_pins.py tests/test_lockstep_versions.py -x` 62 passed, `bash -n` beider Skripte ohne Fehler.
- Verify Task 2: `pytest tests/test_release_archives.py tests/test_workflow_pins.py tests/test_public_artifacts.py -x` 35 passed, `bash -n scripts/release/store-archive.sh` ohne Fehler.
- Gesamt in backend/: 490 passed, 3 skipped (vorher 460 passed, 3 skipped). ruff check "All checks passed!", ruff format --check "61 files already formatted", pyright "0 errors, 0 warnings, 0 informations", vulture ohne Fund.
- Akzeptanz-Greps Task 1: `^  upgrade:` 1, `nextcloud/viewer` 2, `--grep @(patch|drift|disabled|unreachable|missing|noappapi)` 6, `backend_unavailable` 7, `app:disable pii_redaction` 1. Task 2: `pii_redaction-init.mjs` in store-archive.sh 4, `cmp` 2, `integrity:sign-app` in release.yml 2, `pending-certificate` 3, `git ls-files` mit `.key|.pem|.p12|.csr` 0.
- RED echt: test_runner/test_nc 22 failed (TypeError unbekanntes Argument, AttributeError CompanionGone); test_api_routes 1 failed (refresh nie gerufen); test_release_archives 15 failed (altes Ein-App-Skript, fehlende Workflow-Teile).
- `ci/admin-state.sh` gegen eine HTTP-Attrappe: Warten über zwei `backend_unreachable` bis `ok` Exit 0; ohne Zielzustand Exit 0; nie erreichter Zustand nach 4 s Exit 1; falsches Passwort (401, kein App-Passwort) Exit 1; Name `../x.json` abgelehnt.
- `ci/redeploy.sh` gegen Docker- und occ-Attrappen: Erfolg mit tag, push, list, unregister, register und umgeschriebener info.xml (Version und image-tag 0.1.1, `<routes/>` bleibt); falsches `APP_VERSION` im Container Exit 1; info.xml ohne `<routes/>` Exit 1; ohne `INFO_XML` Abbruch; Version `1.2` abgelehnt.
- Zähler der Info-Zeilen aus canary.sh gegen zwei Probelogs: Positivlog 1 Treffer, Negativlog (App-Zeile mit Level 2, Kernzeile mit Level 1) 0.
- Skript-Gate: alte Regex sah `admin-state.sh` nicht (Gegenprobe über den echten Workflow: Liste ohne den Namen), neue sieht ihn; Regel 2 (Umleitungen nur nach ci/out) gilt jetzt auch für beide neuen Skripte und ist grün.
- Staging lokal auf einer Kopie des Baums (Git-sh): Companion-Baum genau Include-Liste, Bundle drin, kein src/node_modules/tests/.gitkeep; Abbruch ohne und mit leerem Bundle; manipuliertes Skript ohne Prüfung staged ohne Bundle (Gegenprobe); Backend byteidentisch mit einem `<routes/>`; info.xml mit Route bricht ab; pack plus assert-contents grün für beide, Companion-Archiv als Container-Hälfte geprüft rot ("carries a code signature"). Der CRLF-Wächter von pack schlug beim ersten Lauf auf eine im Test unter Windows geschriebene signature.json an (Positivkontrolle des Wächters); der Test schreibt jetzt Bytes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Container meldet companion missing erst nach bis zu fünf Minuten**
- **Gefunden bei:** Task 1 (Gegenrichtung "binnen 60 s").
- **Problem:** `companion.run_periodic` fragt bei Zustand ok nur alle 300 s. Ohne Browser-Route kann der Workflow `/status` nicht von außen anstoßen (in AVS ging das über HaRP), und bei abgeschalteter PHP-App ruft niemand `/status`. Der Runner schickte inzwischen alle bis 10 s Claims, die mit 404 abgelehnt wurden.
- **Fix:** `nc.claim` hebt bei 403/404 `nc.CompanionGone`; der Runner fragt dann sofort `companion.check_once` (Seam `recheck_companion`) und zieht in der nächsten Runde nichts, solange missing gilt. Positivkontrolle im Test: leere Warteschlange löst keinen Handshake aus.
- **Commits:** 0051635, a31022c

**2. [Rule 1 - Bug] /status fragte nie neu (refresh_if_stale ungenutzt)**
- **Gefunden bei:** Task 1 (Rückweg der Gegenrichtung).
- **Problem:** Der Docstring von companion.py sagt, `/status` frage nach mehr als 30 s neu; `api/status.py` las aber nur `companion.current()`. AVS ruft `await companion.refresh_if_stale()`. Folge: Nach dem Wiedereinschalten der PHP-App blieb der Container bis zu 300 s bei missing, und `startAllowed()` verweigerte jeden Start mit 503.
- **Fix:** `/status` ruft `refresh_if_stale()` wie in AVS.
- **Commits:** 8762e3b, 09823f7

**3. [Rule 1 - Bug] Blinde Stelle im Skript-Gate**
- `test_ci_scripts._SCRIPT_CALL` erkannte keine Bindestriche, `ci/admin-state.sh` wäre von Kopf- und Umleitungsregel nicht geprüft worden. Regex erweitert, Test mit Positivkontrolle. Commit 90dc36d.

**4. [Rule 3 - Blocking] Kanarien-Gate aus Plan 15 mit Drift-Schritten unvereinbar**
- `deploy_findings` verlangte `ci/canary.sh` als letztes Skript der ganzen Datei; der Plan setzt Drift-Schritte und den Upgrade-Job dahinter. Die Regel gilt jetzt für den Job deploy-harp ohne die Drift-Skripte, und neu: kein Drift-Skript vor der Kanarie. Commit 90dc36d.

**5. Weitere Anpassungen gegenüber der AVS-Vorlage**
- `ci/redeploy.sh` prüft die Version nicht über `GET /status` durch HaRP (leere Routen, Entscheid 9), sondern über `APP_VERSION` in der Umgebung des neuen Containers und den Docker-Healthcheck; die Bewertung liest danach `ci/admin-state.sh`.
- `ci/admin-state.sh` nutzt zuerst Basic-Auth mit `OCS-APIRequest` wie `ci/routes.sh`, App-Passwort als Rückfall, schreibt nur nach ci/out und kann auf einen Zielzustand warten.
- Upgrade ohne Release 0.1.0 als Vorgänger (AVS nutzte einen alten Commit): Planvorgabe "beide Apps per sed auf 0.0.1" umgesetzt; der Container-Code ist auf beiden Seiten derselbe, bewiesen werden Update-Pfad, Volume, Daten und Routen.
- Auftrag bis `review` im Upgrade-Job über `start_job`/`wait_status` statt `ci/flow.sh pdf alice`, weil flow.sh immer bis zur Platzhalter-Kopie läuft (Plan: "bis review, ohne Platzhalter").
- release.yml: Tag-Schritt liest beide info.xml selbst (der Schritt "Read the version" entfiel).
- Job-Timeout deploy-harp 90 auf 120 min (offener Punkt aus 01-16, Drift-Schritte kommen dazu).

## TDD Gate Compliance

Task 2 (`tdd="true"`): RED af692f9 (`test(...)`), GREEN f11f00f (`feat(...)`). Die Abweichungen 1 und 2 ebenfalls mit RED/GREEN (0051635/a31022c, 8762e3b/09823f7). Task 1 ist kein TDD-Task; seine Gates kamen im selben Commit.

## Offen für den echten Lauf (Plan 20)

- Nichts lief gegen eine Instanz (kein Docker, kein PHP lokal). Ungeprüft: Antwort der Claim-Route einer abgeschalteten App (erwartet 404, sonst schlägt Drift 7 binnen 60 s fehl), `docker pause` neben HaRP, `docker logs --since` mit UTC-Zeitstempel, ob `occ app:disable app_api` die ExApp deaktiviert zurücklässt (abgefangen), `occ upgrade` mit Exit 0 oder 3 auf 33 bis 35, Basic-Auth auf die HTML-Prüfseite.
- Loglevel 1: Kernzeilen auf Info-Stufe könnten Testdateinamen tragen und die Namenssuche in canary.sh rot machen (Ausnahme nur für das WebDAV-`url`-Feld). Falls ja, Zeilen benennen und gezielt ausnehmen, nicht das Level senken.
- Laufzeit: 120 min sind eine Schätzung (zwölf Playwright-Projekte je Drift-Tag, vier Neuregistrierungen, zwei Aufträge).
- PDF-Vorschau-Anbieter im Runner (offener Punkt aus 01-16) ist hier nicht angefasst.
- `/status` fragt jetzt bei veralteter Antwort den Handshake innerhalb des 1,5-s-Budgets von `ExAppService::status()` (wie AVS, dort grün); auf langsamen Instanzen beobachten.

## Deferred Issues (außerhalb dieses Plans)

- `.github/workflows/store-submit.yml` reicht nur `pii_redaction` ein und prüft `IMAGE: ghcr.io/street1983nk/pii_redaction`, während docker.yml `ghcr.io/street1983nk/pii_redaction_backend` baut. Für zwei Archive muss store-submit beide Apps einreichen (AVS `submit_findings`). Kein Store-Upload in Phase 1, daher nicht geändert.
- Die Tag-Prüfung in docker.yml liest nur `backend/appinfo/info.xml`, nicht `php/appinfo/info.xml` (AVS `docker_findings`). release.yml prüft beide.
- shellcheck läuft nur in CI (python.yml), lokal nicht vorhanden; für die neuen Skripte nur `bash -n`.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche. T-01-18-01: Schlüssel nur als Secret, Datei unter RUNNER_TEMP mit umask 077 und Löschschritt, Gate `git ls-files` ohne `.key/.pem/.p12/.csr` (0 Treffer), Archive ohne Schlüsselendungen. T-01-18-02: `cmp` der Backend-info.xml, `integrity:sign-app`, Tag-Lockstep über beide info.xml und image-tag. T-01-18-03: leeres `<routes/>` als Staging-Pflicht und `ci/routes.sh` nach dem Upgrade. T-01-18-04: Volume-CreatedAt, Inode, Auftragszeile, state.db-Zeile und Seitenbild vor und nach dem Update verglichen. Die Produktänderung (Claim 403/404 löst Handshake aus) sendet nichts Neues nach außen, nur den bestehenden signierten Handshake an die eigene Instanz.

## Self-Check: PASSED

- Dateien vorhanden: ci/redeploy.sh, ci/admin-state.sh, backend/tests/test_release_archives.py, scripts/release/store-archive.sh, .github/workflows/release.yml, .github/workflows/deploy-harp.yml.
- Commits 0051635, a31022c, 8762e3b, 09823f7, 90dc36d, af692f9, f11f00f in `git log`, Autor und Committer street1983nk <k.cherif@outlook.de>, keine Session- oder Co-Author-Zeilen, kein "closes/fixes #N".
- Docker wurde nicht gestartet; der Daemon lief nicht (Aufruf von `docker` endete mit "failed to connect to the docker API").
- STATE.md, ROADMAP.md und REQUIREMENTS.md nicht angefasst (Vorgabe des Auftrags).
