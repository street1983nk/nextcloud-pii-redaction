---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 17
subsystem: ci
tags: [rights, etag, queue, routes, canary, measurements, gates]
requires: [01-10, 01-11, 01-12, 01-13, 01-14, 01-15, 01-21]
provides: [ci/rights.sh, ci/stale.sh, ci/queue.sh, ci/routes.sh, ci/canary.sh, ci/measure.sh, Skript-Gate, Vollständigkeits-Gate]
affects: [01-18, 01-20]
tech-stack:
  added: []
  patterns: ["db_query/db_init in ci/lib.sh: SQLite über python3 sqlite3, MariaDB über den Client im Dienstcontainer, mit Positivkontrolle auf oc_pii_slot", "Negativsuche nur mit Positivkontrolle im selben Skript", "Dumps heißen *-dump.* oder *.sql und bleiben im Runner"]
key-files:
  created: [ci/rights.sh, ci/stale.sh, ci/queue.sh, ci/routes.sh, ci/canary.sh, ci/measure.sh, backend/tests/test_ci_scripts.py]
  modified: [ci/lib.sh, backend/tests/test_php_gates.py]
decisions:
  - "Gelöschtes Original: Status-API antwortet 404 (FileAccess sieht die Datei nicht mehr, Recheck missing); cancelled(original_deleted) wird in oc_pii_jobs und über die Prüfseite (200, gelöschte Karte ohne Namen) nachgewiesen"
  - "Betreff der Benachrichtigung aus oc_notifications.subject, weil die OCS-Antwort nur den übersetzten Text trägt"
  - "Namenssuche in canary.sh nimmt nur zwei benannte Stellen aus: Zugriffszeilen von WebDAV-Anfragen im PHP-Server-Log und das url-Feld solcher Anfragen in nextcloud.log (Pfad wählt der Testclient); die Kanarien-Suche läuft auf den ungefilterten Dateien"
  - "Kanarie zusätzlich in Hex-Form in DB- und state.db-Auszug gesucht (SQLite schreibt BLOBs als X'..'), dazu in den hochgeladenen ci/out/*.json und *.log"
  - "measure.sh legt lastChild unter festen Schlüsseln je Art (render, soffice, placeholder) ab; nur die Art des letzten Kindes ist belegt, die anderen sind null"
  - "routes.sh prüft den unsignierten Aufruf an HaRP direkt (8780) und über die Vorderadresse (8090)"
metrics:
  duration: "ca. 75 min"
  completed: 2026-11-14
  tasks: 3
  files: 9
---

# Phase 1 Plan 17: Prüfskripte für Rechte, Etag, Warteschlange, Routen, Kanarie und Messung Summary

Sechs CI-Skripte belegen im echten Lauf Rechte, Etag-Bindung, Einzelauftrag, fehlende Browser-Routen, die Kanarie mit Positivkontrolle und die Messwerte. Zwei Gates halten die Skripte (Kopf, Umleitungen nur nach ci/out, Reihenfolge der Positivkontrolle, beide Warteschlangen-Prüfungen) und den Phase-1-Dateibaum (33 PHP-Dateien) fest. Gegen die echte Instanz läuft das erst in Plan 20, lokal gibt es kein PHP und kein HaRP.

## Tasks

| Task | Name | Commit | Dateien |
|---|---|---|---|
| 1 | Rechte-, Etag- und Warteschlangen-Skript | 699c058 | ci/rights.sh, ci/stale.sh, ci/queue.sh, ci/lib.sh |
| 2 | Routen-, Kanarien- und Mess-Skript | d2c63e0 | ci/routes.sh, ci/canary.sh, ci/measure.sh |
| 3 | Skript-Gate und Vollständigkeits-Gate (RED) | bee3983 | backend/tests/test_ci_scripts.py, backend/tests/test_php_gates.py |
| 3 | Skripte für das Umleitungs-Gate angepasst (GREEN) | 874e070 | ci/queue.sh, ci/canary.sh, ci/measure.sh |

## Ergebnis

- **rights.sh:** (a) bob auf alices PDF ergibt 404 `not_readable`. (b) bob auf alices Auftrag: Status, Prüfseite und Bild ergeben 404, im Körper weder Dateiname (auch nicht URL-kodiert) noch Kanarie. (c) carol auf `FILE_GF_CAROL` ergibt 404 `not_readable`, carol auf alices Gruppenordner-Auftrag 404 für alle drei Wege. (d) `FILE_SHARED_BLOCKED_BOB` ergibt 403 `download_blocked`. (e) Frische Kopie wird normal an bob geteilt, bob kommt bis `review` (Positivkontrolle 200/200/200), alice entzieht per `DELETE .../shares/{id}`, danach 404/404/404. (f) Kopie mit `download:true` geteilt, bob kommt bis `review`, alice setzt per `PUT` `download:false`: Bild 403, Status 200 mit `recheck: download_blocked`. Positivkontrolle: alice liest ihren Auftrag mit 200, `recheck ok`.
- **stale.sh:** Jeder Auftrag läuft auf einer frischen WebDAV-Kopie. Vor der Änderung prüft das Skript Bild 200 und `review_ready` in `oc_notifications` als Positivkontrolle. PUT mit geänderten Bytes ergibt `stale`/`original_changed`, Bild 409 und genau eine Benachrichtigung `job_stale`. DELETE ergibt in der DB `cancelled`/`original_deleted` und keine Benachrichtigung mehr (geprüft, bevor die Prüfseite geöffnet wird, denn das Öffnen würde sie auch verwerfen). Der Status antwortet 404, die Prüfseite 200 ohne Namen, das Bild 404.
- **queue.sh:** Drei WebDAV-Kopien (PDF, DOCX, ODT). Das Skript wartet, bis kein früherer Lease mehr läuft, und startet dann direkt hintereinander. `ahead` darf nicht fallen, beim dritten Auftrag ist es mindestens 1. Alle 0,5 s eine Stichprobe `COUNT(*) ... status IN ('analyzing','applying') AND lease_until > now` nach `ci/out/queue-samples.log`, alle 2 s der Status. Jede Stichprobe ist höchstens 1, mindestens eine genau 1.
- **routes.sh:** alice und dora bekommen für `status`, `jobs/1/pages/1.png` und `jobs/1/output` über `app_api/proxy/pii_redaction_backend` jeweils 404. Unsigniert an HaRP und an der Vorderadresse kommt nicht 200. Positivkontrolle: `admin/state` als dora antwortet 200 mit `ok`.
- **canary.sh:** Zuerst die Positivkontrolle in PDF, DOCX (`word/document.xml`) und ODT (`content.xml`) unter `data/alice/files`. Danach DB-Vollauszug (SQLite `iterdump`, MariaDB `mariadb-dump --skip-extended-insert`), die Zeilen von `oc_pii_*`, Container- und HaRP-Log, `state.db` per `docker exec`, Text aller 12 Kopien per `ci/pdf_text.py` (mit Positivkontrolle „Placeholder from PII Redaction“ je Kopie). Die Kanarie steht in keiner dieser Quellen und auch nicht in `nextcloud.log`, im PHP-Server-Log und in den hochgeladenen `ci/out/*.json|*.log`. Die Testdateinamen fehlen in den Logs, den `oc_pii_*`-Zeilen und in `state.db`. Positivkontrolle dafür: alle drei Namen stehen im DB-Vollauszug (oc_filecache). Ausgenommen und im Skript benannt: Seitenbilder (PNG) und `work/<job>/src`.
- **measure.sh:** Erfasst `imageBytes`, `imageGzipBytes`, `coldStartRegisterMs`, `coldStartReadyMs`, `idleMemoryCurrentBytes`, `idlePeakBytes` (null mit Hinweis, wenn `memory.peak` fehlt, A7), `idleAnonBytes` und `lastChild_<art>_rssKb|ms`. Das Ergebnis geht nach `ci/out/measurements-<server>-<arch>-<db>.json`. Danach prüft python3, dass jeder Wert eine Zahl oder null ist.

### Belege (lokal)

- `bash -n` aller 9 `ci/*.sh`: ohne Fehler. `set -euo pipefail` je 1-mal in rights/stale/queue.
- Akzeptanz-Greps Task 1: download_blocked 4, not_readable 3, DELETE|unshare|shares/ 2, original_changed 4, original_deleted 4, 409 3, lease_until 3, mariadb|mysql 1. Task 2: positive control 9, app_api/proxy/pii_redaction_backend 2, exapps/pii_redaction_backend 4, PIIKANARIE7Q4XZ9 2, state.db 7, docker logs 2, memory.peak 7, measurements- 2. Task 3: `def test_self` 4, `test_the_tree_carries_the_files_the_gates_are_about` 1.
- **canary.sh gegen eine Attrappe** (unechtes `php`/`occ` und `docker`, echte Fixtures aus `ci/make_fixtures.py`, SQLite-DB und state.db im Scratchpad). Der saubere Lauf endet mit Exit 0, „canary done“. Diese 12 Störfälle schlagen alle mit Exit 1 an: Kanarie im Container-Log, Name im Container-Log, Name in einer Nicht-WebDAV-Zeile des PHP-Logs, Name in der Meldung von nextcloud.log, Kanarie im WebDAV-url-Feld von nextcloud.log (für die Kanarie gilt keine Ausnahme), Kanarie als BLOB in der DB (Hex-Treffer), Name in state.db, Name in oc_pii_jobs, Kanarie im Original entfernt („positive control failed“), eine Kopie fehlt („11 copies found“), Kanarie in einer Kopie (Text und Rohbytes), Kanarie in einer hochgeladenen JSON-Datei. Nach der Umstellung auf Heredocs zusätzlich: Name im HaRP-Log und Kanarie in state.db schlagen an.
- **measure.sh gegen eine Attrappe:** Das JSON enthält nur Zahlen und null. Fehlt `memory.peak`, steht `idlePeakBytes: null` mit Hinweis. Eine unbekannte Kindart bricht ab, ein Wort statt einer Zahl ebenso („measurements that are no numbers: lastChild_render_rssKb“, Exit 1).
- **queue.sh:** Die Auswertungs-Regexe an einem Probelog geprüft: 5 Stichproben, davon 2 mit genau 1 und 2 über 1 (auch „12“ wird erkannt). Ohne Treffer zählt das Log 0.
- **RED:** Der erste Lauf von `test_ci_scripts.py` gegen die Skripte aus d2c63e0 schlug fehl mit `{'queue.sh': ['$(date']}`: eine verschachtelte SQL-Zeichenkette sah wie eine Umleitung aus. Danach wurde der mehrzeilige `python3 -c '...'`-Block in canary.sh als blinde Stelle erkannt (die `state.db`-Umleitung war unsichtbar). Beides ist in 874e070 behoben, jetzt sieht das Gate 33 Umleitungen in den 8 aufgerufenen Skripten plus lib.sh, alle nach `/dev/null` oder ci/out.
- **Gates in backend/:** pytest 460 passed, 3 skipped. ruff check „All checks passed!“, ruff format --check ohne Änderung, pyright „0 errors, 0 warnings, 0 informations“, vulture ohne Fund.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] DB-Zugriff als gemeinsamer Helfer in ci/lib.sh** (nicht in files_modified)
- stale.sh, queue.sh und canary.sh brauchen denselben Weg zu SQLite und MariaDB. `sqlite_file` liest Datenverzeichnis und `dbname` per occ, `db_query` und `db_init` prüfen positiv, dass die Zeile `oc_pii_slot` id 1 gelesen wird.
- **Commit:** 699c058

**2. [Rule 1 - Bug] Gate-blinde Stellen in den eigenen Skripten**
- Die verschachtelte SQL-Zeichenkette in queue.sh ist jetzt die Funktion `active_leases`. Die mehrzeiligen `python3 -c '...'` in canary.sh und measure.sh sind Heredocs, `docker exec -i` für state.db. Der Kopien-Text liegt unter `${CI_OUT}/...`, die leere nextcloud.log-Vertretung direkt in ci/out.
- **Commit:** 874e070

**3. [Rule 2 - Missing] Strengere Kanarien-Suche**
- Die Hex-Form wird in DB und state.db mitgesucht, die hochgeladenen `ci/out/*.json|*.log` werden mitgescannt. Leere Dumps brechen ab, und mindestens 12 Kopien müssen da sein (`EXPECTED_COPIES`).
- **Commit:** d2c63e0

**4. Nachweis von cancelled(original_deleted):** Der Plan nennt „Status cancelled/original_deleted“. Die Status-API kann das nicht liefern (404, weil die Datei für alice fehlt und der Recheck `missing` meldet). Deshalb belegt das Skript den Zustand über `oc_pii_jobs`, die Prüfseite (200, gelöschte Karte) und den Status 404.

**5. Benannte Ausnahmen in der Namenssuche:** WebDAV-Zugriffszeilen im PHP-Server-Log und das `url`-Feld von WebDAV-Anfragen in nextcloud.log. Begründung: Der eingebaute PHP-Server schreibt jeden Anfragepfad ins Log, `Antrag.docx` stünde dort schon durch die Saat. Die Zahl der ausgenommenen Zeilen wird ausgegeben, die Kanarien-Suche bleibt ungefiltert.

## TDD Gate Compliance

Task 3 (`tdd="true"`): RED-Commit bee3983 (`test(...)`), GREEN-Commit 874e070 (`fix(...)`). Der RED-Fehlschlag war echt (siehe Belege). Die Skripte selbst stammen aus Task 1 und 2 (vor dem Gate, wie im Plan vorgesehen).

## Offen für den echten Lauf (Plan 20)

- Kein Skript lief bisher gegen eine echte Instanz. Ungeprüft sind: der OCS-PUT von `attributes` auf eine bestehende Freigabe (NC 33 bis 35), `mariadb-dump` im Image mariadb:11.8 (der Workflow nutzt dort bisher nur `mariadb`), `memory.peak` auf den GitHub-Runnern und ob `ahead` durch Purge-Aufgaben früherer Skripte springt.
- shellcheck läuft nur in CI (python.yml), lokal gibt es kein shellcheck. Lokal geprüft ist nur `bash -n`.
- nextcloud.log steht auf der Standardstufe (warning), Info-Zeilen der App landen also nicht darin. Der Scan dort ist deshalb schwächer als bei den anderen Logs. Ein Debug-Level im Workflow brächte Kernzeilen mit Pfaden und damit Fehlalarme. Entscheidung offen, nicht geändert.
- Der Kaltstart aus `coldstart.json` misst Registrierung und erste `ok`-Antwort, nicht den Containerstart allein.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche. T-01-17-01: Positivkontrollen in jedem Skript, Reihenfolge durch Gate gehalten. T-01-17-02: Kanarie und Namen in DB, Logs, state.db und Kopien. T-01-17-03: Proxy-404 als Nutzer und Admin, unsigniert nicht 200. T-01-17-04: Entzug, nachträgliche Sperre und ACL im echten Lauf. T-01-17-05: DB-Stichproben auf SQLite und MariaDB. T-01-17-06: alle Auszüge heißen `*-dump.*` oder `*.sql` und fallen unter die Artefakt-Ausschlüsse von deploy-harp.yml.

## Self-Check: PASSED
