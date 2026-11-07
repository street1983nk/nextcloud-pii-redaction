---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 15
subsystem: ci
tags: [deploy-harp, mariadb, fixtures, canary, seed, core-path]
requires: [01-09, 01-10, 01-11, 01-12, 01-13, 01-14, 01-21]
provides: [Integrationsbeweis-Workflow auf sieben Beinen, Fixtures mit Kanarie, Skriptvertrag ci/lib.sh, Saat, Kernweg-Skript]
affects: [01-16, 01-17, 01-18, 01-20]
tech-stack:
  added: []
  patterns: ["ci/lib.sh als gemeinsamer Skriptvertrag (NC_URL, NC_ROOT, ADMIN_*, CI_PASS, ci/out/)", "Dienstcontainer nur auf einem Matrix-Bein über leeren Image-Ausdruck"]
key-files:
  created: [ci/make_fixtures.py, ci/pdf_text.py, ci/lib.sh, ci/seed.sh, ci/flow.sh, backend/tests/test_ci_fixtures.py]
  modified: [.github/workflows/deploy-harp.yml, .github/workflows/python.yml, backend/tests/test_workflows.py, backend/tests/test_lockstep_versions.py, backend/pyproject.toml, .gitignore, php/package.json, php/vite.config.ts]
decisions:
  - "Gemeinsame Helfer in ci/lib.sh (gesourct); Plan 17 nutzt req, wait_status, start_job, fileid_of, etag_of"
  - "Gruppenordner Akten mit offenem PDF (FILE_GF_ALICE) und Unterordner Gesperrt mit ACL -read für carol (FILE_GF_CAROL); seed prüft beides positiv und negativ"
  - "Download-gesperrte Freigabe als eigene Datei 'Bescheid 2026-114 Kopie.pdf'; shareapi_allow_view_without_download bleibt unberührt (fail closed ohne Einstellung)"
  - "dora bekommt ein eigenes PDF (FILE_PDF_DORA) für das Kontrast-Projekt"
  - "MariaDB 11.8 per Index-Digest c4124d1a... als Dienstcontainer nur auf stable35/amd64"
  - "php-Build mit --configLoader runner: beseitigt die 01-21-Warnung zu @vue/tsconfig, Ausgabe bytegleich"
metrics:
  duration: "ca. 45 min"
  completed: 2026-11-07
  tasks: 3
  files: 14
---

# Phase 1 Plan 15: Integrationsbeweis-Workflow Summary

`deploy-harp.yml` läuft jetzt auf sieben Beinen: NC 33/34/35 je amd64 und arm64 mit SQLite, dazu stable35/amd64 mit MariaDB. Jedes Bein installiert notifications, PHP-App und ExApp über HaRP und ruft die Prüfungen in einer festen Reihenfolge auf: Fixtures, Saat, sechs Kernwege, rights/stale/queue/routes, Playwright, measure und am Ende canary. Fixtures und PDF-Textprüfer brauchen nur die stdlib und haben eine Positivkontrolle mit PyMuPDF.

## Tasks

| Task | Name | Commit | Dateien |
|---|---|---|---|
| 1 | Fixtures mit Kanarie und PDF-Textprüfer | 8c32c42 | ci/make_fixtures.py, ci/pdf_text.py, backend/tests/test_ci_fixtures.py |
| 2 | Saat und Kernweg-Skript | 27dcabe | ci/lib.sh, ci/seed.sh, ci/flow.sh |
| 3 | deploy-harp.yml mit sieben Beinen und Workflow-Gates | 41f5228 | .github/workflows/deploy-harp.yml, backend/tests/test_workflows.py, backend/tests/test_lockstep_versions.py |

## Ergebnis

- **Fixtures:** `Bescheid 2026-114.pdf` hat 2 Seiten, Helvetica/WinAnsi, keinen Filter, kein `/Info`, eine gültige xref (PyMuPDF `is_repaired` false). Dazu `Antrag.docx` (4 Teile, kein docProps), `Vermerk.odt` (mimetype zuerst und stored, kein meta.xml) und `notes.txt`. Die Kanarie steht genau einmal im Inhaltsstrom bzw. nur in `word/document.xml` und `content.xml`.
- **pdf_text.py:** liest Literal-, Hex- und TJ-Strings aus ungefilterten und Flate-Strömen und überspringt Bilder, Fonts und fremde Filter. Positivkontrollen: Es findet die Kanarie in der Fixture und in einer mit Flate komprimierten PDF, deren Rohbytes sie verbergen. In der echten Platzhalter-PDF des Backends findet es "Placeholder from PII Redaction".
- **seed.sh:** legt die sieben Nutzer an, setzt Sprache und Locale vor dem ersten Login und gibt dora hohen Kontrast. groupfolders kommt aus dem Store oder als Tarball. Die ACL wird mit `--enable` eingeschaltet und mit `-read` für carol gesetzt. Die Freigabe an bob läuft über OCS mit `download:false`. `fileids.env` enthält 11 IDs plus `GROUP_FOLDER_ID`.
- **flow.sh:** Je Aufruf zwei Durchläufe: Start 201, Abfrage bis `review` (Log nur mit Codes und Zahlen), `no-store`, PNG-Magic und `nosniff` für Seite 1, Benachrichtigung `job`/`{id}` ohne Stamm und ohne Kanarie, Platzhalter 202, `cron.php` bis `published`. Danach muss der Kopienname (NFC) mit `outputName` und `outputFileId` übereinstimmen, die Kopie enthält die Platzhalterzeile und keine Kanarie, der zweite Name endet auf ` (2).pdf`, Etag und sha256 des Originals bleiben gleich.
- **Workflow-Gate:** prüft die sieben Beine, die feste Reihenfolge (Kommentare ausgenommen), canary.sh als letztes Skript, `NEXTCLOUD_WORKERS=8`, den notifications-Checkout, Build vor `mv`, MariaDB-Digest, `--database=mysql`, Artefakt-Ausschlüsse `*.sql`/`*-dump.*` und dass kein `runner.` in Workflow- oder Job-env steht. Jede Regel hat einen Selbsttest.

Gates in `backend/`: ruff check (inkl. `../ci`), ruff format --check (60 Dateien), pyright 0 Fehler, vulture leer, pytest 434 passed / 3 skipped (seriell). In `php/`: npm typecheck und build grün. `bash -n` für alle drei Skripte, YAML per `yaml.safe_load` gelesen (7 Beine, 34 Schritte).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ruff, pyright und vulture sahen ci/ nicht**
- **Found during:** Task 1
- **Fix:** `../ci` in `[tool.ruff] src`, `[tool.pyright] include` und `[tool.vulture] paths` (vulture mit `exclude = ["node_modules"]`). Der ruff-Schritt in python.yml prüft jetzt auch `../ci`.
- **Commit:** 8c32c42

**2. [Rule 1 - Bug] Der gh-Schreib-Scan las Bytecode**
- **Found during:** Task 1. Der Test lädt `ci/*.py` und erzeugt dabei `ci/__pycache__`. `test_no_workflow_or_script_writes_...` brach dann mit UnicodeDecodeError ab.
- **Fix:** Der Scan überspringt `__pycache__` und `.pyc`.
- **Commit:** 8c32c42

**3. [Rule 2 - Missing] shellcheck für ci/*.sh**
- Neuer python.yml-Schritt `shellcheck -x ci/*.sh` an der Repo-Wurzel. Lokal gibt es kein shellcheck (neues Paket wäre nötig), deshalb nur `bash -n`. `lib.sh` schaltet SC2034/SC2329 ab, weil die gesourcten Variablen und Funktionen erst in den aufrufenden Skripten benutzt werden.
- **Commit:** 27dcabe

**4. [Rule 2 - Missing] Gemeinsamer Helfer ci/lib.sh** (nicht in files_modified). Er setzt den Skriptvertrag einmal statt in jedem Skript um und wird von Plan 17 gesourct.

**5. Abweichende Logdatei:** Die Fortschrittsdatei heißt `progress-<format>-<user>.log` statt `progress-<format>.log`, weil das PDF viermal mit verschiedenen Nutzern läuft und sich sonst überschreiben würde.

**6. [Rule 3 - aus 01-21] tsconfig-Warnung im Server-Baum behoben**
- **Ursache:** Das esbuild-Bündeln von `vite.config.ts` liest jede `tsconfig.json` oberhalb von `php/`, im CI also die des nextcloud/server-Baums mit `extends @vue/tsconfig`. Lokal nachgestellt mit einer Eltern-tsconfig: Warnung da.
- **Fix:** `npm run build` nutzt `vite build --configLoader runner`. Danach ist die Warnung weg, die Ausgabe (sha256 über alle `js/*.mjs`) ist mit beiden Ladern gleich. Der Fix betrifft auch php.yml und deploy-harp.yml, weil beide `npm run build` aufrufen.
- **Commit:** 41f5228

## TDD Gate Compliance

Task 1 (`tdd="true"`): Test und Umsetzung liegen im selben `feat`-Commit, es gibt keinen eigenen RED-Commit. Die Positivkontrollen (PyMuPDF findet die Kanarie, pdf_text liest Flate) und der Selbsttest mit falschen Aufrufen decken das Verhalten ab.

## Offen für den echten Lauf (Plan 20)

- Ob ein CSRF-POST per Basic-Auth mit `OCS-APIRequest: true` ohne Cookie durchgeht, zeigt erst der erste Lauf. Erwartet: ja.
- `groupfolders:create` für stable35 kommt nur aus dem Store (für 35 gibt es keine Tarball-Zuordnung, wie bei AVS).
- Die Schritte für rights/stale/queue/routes/measure/canary verweisen auf Skripte aus Plan 17, der Playwright-Schritt auf `ci/playwright` aus Plan 16.

## Known Stubs

Keine. Die Workflow-Schritte der Pläne 16/17 sind bewusst vorab eingehängt.

## Threat Flags

Keine neue Fläche. T-01-15-01: nur synthetische Fixtures, Dumps vom Upload ausgeschlossen. T-01-15-02: Actions per SHA, MariaDB per Digest. T-01-15-03: `permissions: contents: read`, keine Secrets, Testpasswörter nur für die Wegwerf-Instanz. T-01-15-04: `set -euo pipefail` und `fail` mit letztem Status.

## Self-Check: PASSED
