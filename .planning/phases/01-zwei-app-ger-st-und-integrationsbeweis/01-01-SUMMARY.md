---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 01
subsystem: infra
tags: [scaffold, exapp, php-app, lockstep, ci, phpunit, dependabot, supply-chain]
requires: []
provides:
  - "backend/ mit ExApp pii_redaction_backend (Paket, Dockerfile, appinfo mit leerem routes-Element, l10n, Tests)"
  - "php/ mit PHP-App pii_redaction (info.xml, Application.php, composer, phpunit, bootstrap, erster Unit-Test)"
  - "Lockstep-Gate backend/tests/test_lockstep_versions.py (4 Versionen + Server-Fenster gegen deploy-harp-Matrix)"
  - ".github/workflows/php.yml (lint, composer-hygiene, phpunit gegen stable34)"
  - "conftest BACKEND_ROOT/REPO_ROOT, scripts/l10n_js.py --root"
  - "Laufzeit-Pins pymupdf 2.1 und httpx 0.28.1"
affects: [01-02, 01-03, 01-09, 01-10, 01-13, 01-14, 01-15, 01-16]
tech-stack:
  added: ["pymupdf 2.1 (mit onnxruntime 1.31.1, networkx 3.7, numpy 2.5.4, psutil 7.2.2, tabulate 0.10.0, pymupdf-layout/pymupdf4llm 2.1, flatbuffers 25.12.19, protobuf 7.36.2)", "httpx 0.28.1 (von dev nach Laufzeit)", "phpunit/phpunit 11.5.57 (require-dev, nur CI)"]
  patterns:
    - "Zwei-App-Muster wie AVS/Findling: php/ + backend/, eine Versionsnummer"
    - "Tests trennen BACKEND_ROOT (Paket, Dockerfile, appinfo, l10n, pyproject) und REPO_ROOT (Workflows, Doku)"
    - "Env-Präfix PII_REDACTION_ als config.ENV_PREFIX"
    - "ExApp ohne Browser-Routen: leeres routes-Element, Store-Test und deploy-harp-Negativprüfung"
key-files:
  created:
    - backend/README.md
    - backend/tests/test_lockstep_versions.py
    - php/appinfo/info.xml
    - php/lib/AppInfo/Application.php
    - php/composer.json
    - php/phpunit.xml
    - php/tests/bootstrap.php
    - php/tests/Unit/AppInfo/ApplicationTest.php
    - .github/workflows/php.yml
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/Dockerfile
    - backend/docker/entrypoint.sh
    - backend/appinfo/info.xml
    - backend/l10n/{de,en,fr}.{json,js}
    - backend/src/pii_redaction_backend/{__init__,config,main,settings}.py
    - backend/tests/*.py
    - backend/.dockerignore
    - scripts/l10n_js.py
    - .github/workflows/{python,docker,deploy-harp}.yml
    - .github/dependabot.yml
    - .gitignore
key-decisions:
  - "Owner-Freigabe 07.11.2026: alle Pakete freigegeben, aber vue 3.5.44 statt 3.5.45 und @playwright/test 1.64.1 statt 1.65.0 (Cool-down, wie nextcloud/server und AVS)"
  - "Env-Präfix bleibt PII_REDACTION_ (config.ENV_PREFIX), nicht PII_REDACTION_BACKEND_"
  - "Backend ohne Browser-Routen: leeres routes-Element; deploy-harp prüft, dass unsignierte Aufrufe von /status nicht 200 ergeben"
  - "httpx nur einmal gepinnt (Laufzeit), nicht zusätzlich in dev"
  - "Image ohne LICENSE-Datei und ohne img/: Build-Kontext backend/, Lizenz im OCI-Label"
  - "Repo-Name in Tests fest nextcloud-pii-redaction (folgt der PHP-App)"
  - ".planning/ vom Strich-/Emoji-Gate ausgenommen (GSD-Statuszeichen)"
  - "Erster PHP-Unit-Test auf die App-IDs, damit der phpunit-Job mit failOnEmptyTestSuite nicht rot läuft"
requirements-completed: []  # PLAT-01 und PLAT-03 nur angelegt (Gerüst, Lockstep-Gate); Läufe auf NC 33 bis 35 folgen in späteren Plänen
metrics:
  duration: "ca. 75 min"
  completed: 2026-11-07
  tasks: 4
  files: 55
---

# Phase 1 Plan 01: Zwei-App-Gerüst Summary

Das Skeleton ist jetzt aufgeteilt in `backend/` (ExApp `pii_redaction_backend`, ohne Browser-Routen, mit den Laufzeit-Pins pymupdf 2.1 und httpx 0.28.1) und `php/` (PHP-App `pii_redaction`). Alle Python-Gates sind grün. Das Lockstep-Gate prüft vier Versionen plus das Server-Fenster, `php.yml` testet die PHP-Hälfte in CI.

## Task 1: Paket-Legitimität (Owner-Freigabe)

Die Belege wurden rein lesend gesammelt (npm view, PyPI JSON, Packagist p2, `nextcloud/server` stable33 bis 35 `package.json`). Die Tabelle steht im Checkpoint-Bericht an den Koordinator.

**Owner-Entscheidung, wörtlich wie vom Koordinator übermittelt (07.11.2026, Kanal Claude-Code-Terminal, wörtlich "Go" als Antwort auf die Empfehlung des Koordinators):**

> all packages approved as listed EXCEPT two pins changed: vue 3.5.44 instead of 3.5.45, and @playwright/test 1.64.1 instead of 1.65.0 (cool-down, same as nextcloud/server and AVS). pymupdf 2.1 (incl. its mandatory deps onnxruntime, numpy, networkx, pyyaml, psutil, tabulate and the two stub packages) and @nextcloud/dialogs 8.0.0 stay approved.

Belege zu den beiden geänderten Pins, nachträglich lesend erhoben:
- vue 3.5.44: github.com/vuejs/core, veröffentlicht 13.10.2026, kein postinstall, `sha512-dvvmaOCG7lAMkJTPqPwWeGMsPS6DIsFsfZDUgBp9V6mHf9b3+/wyVwYR4Es+WV6uJC0FKRxp81Obcq0ZwUcGFQ==`
- @playwright/test 1.64.1: github.com/microsoft/playwright, veröffentlicht 14.10.2026, kein postinstall, `sha512-IaYGml/nSOiZWROfPtuIL7neuu9qDOZ3TNvNljUIrhDMxiGTgPjzj/g9p9RxpS2tSepPDRY+UwAaEeiKtUvIAg==`

Die npm-Pakete werden erst in den Plänen 09 und 16 installiert, dann mit diesen Pins. In `uv.lock` stimmen die pymupdf-sha256 mit den freigegebenen Werten überein: x86_64 `a9efa2e9...cbcd9`, aarch64 `5a1a1fee...d1dd`.

## Ergebnis

- **Task 2:** 33 Dateien per `git mv` nach `backend/` verschoben, die Historie bleibt erhalten. Paket, Modul, `APP_ID`, Image und Datenpfad heißen jetzt `pii_redaction_backend`, die Env-Variable bleibt `PII_REDACTION_LOG_LEVEL`. Dazu kommen eine eigene `backend/README.md` und die "Backend-Beschreibung" aus der UI-SPEC in Formular, info.xml und l10n (DE/EN/FR). `<routes/>` ist leer, und ein Store-Test mit Selbsttest schlägt bei jeder Route an. `l10n_js.py` kennt jetzt `--root`. `uv lock`/`uv sync` liefen, das alte `.venv` an der Wurzel ist gelöscht.
- **Task 3:** `python.yml` arbeitet in `backend/` und hat einen eigenen ruff-Schritt für `../scripts`. `docker.yml` baut aus `backend/` (`ghcr.io/street1983nk/pii_redaction_backend`). `deploy-harp.yml` setzt `BACKEND_APP_ID`; die Admin-Routen-Prüfung ist zur Negativprüfung "kein unsignierter Weg auf /status" geworden, anonym und mit Admin-Login. Dependabot beobachtet uv/docker auf `/backend` sowie npm auf `/php` und `/ci/playwright`, vite-Majors werden ignoriert. `.gitignore` deckt die Build-Ausgaben ab. `test_workflows.py` hat eine neue Regel gegen schreibende `gh`-Befehle (PR-Kommentar, -Bearbeitung, -Review überall; jeder schreibende Befehl neben `app-certificate-requests`), mit Selbsttest an mutierten Beispielen.
- **Task 4:** `img/` liegt jetzt in `php/img/`. Neu sind `php/appinfo/info.xml` (0.1.0, PHP 8.2, NC 33 bis 35, DE/EN/FR mit Hinweis auf "PII Redaction Backend"), `Application.php` (`final`, `APP_ID`, `BACKEND_APP_ID`), composer/phpunit/bootstrap aus AVS und der erste Unit-Test. Dazu kommen `test_lockstep_versions.py` aus AVS und `php.yml`.

Gates in `backend/`: ruff check, ruff format --check, pyright (latest) mit 0 Fehlern, vulture leer, pytest 122 passed (seriell, wegen knappem RAM). Gegenproben: `php/appinfo/info.xml` auf 0.1.1 und danach `max-version` auf 34 gesetzt; das Lockstep-Gate wurde jeweils rot und danach zurückgesetzt.

## Task Commits

1. **Task 1: Paket-Legitimität** - kein Commit (Checkpoint, Owner-Freigabe oben)
2. **Task 2: Backend nach backend/** - `265764f` (refactor)
3. **Task 3: Workflows, Dependabot, Ignore-Dateien** - `ee7b163` (ci)
4. **Task 4: PHP-Gerüst, Lockstep, php.yml** - `f8e27f6` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Strich-/Emoji-Gate scheiterte an .planning/**
- **Found during:** Task 2
- **Issue:** `test_no_tracked_text_carries_a_dash_or_an_emoji` fand GSD-Statuszeichen in `.planning/PROJECT.md` und weiteren Planungsdokumenten (gleicher Befund wie AVS).
- **Fix:** `EXEMPT_PREFIXES = (".planning/",)` mit Begründung.
- **Commit:** 265764f

**2. [Rule 1 - Bug] Store-Test verlangte Env-Präfix = APP_ID**
- **Fix:** `config.ENV_PREFIX = "PII_REDACTION_"`. Der Test prüft gegen die Konstante und gegen die exakte Variablenliste.
- **Commit:** 265764f

**3. [Rule 1 - Bug] Repo-URLs aus APP_ID abgeleitet**
- **Issue:** Mit der neuen ID hätten Store- und Workflow-Test `nextcloud-pii-redaction-backend` erwartet.
- **Fix:** Der Repo-Name `nextcloud-pii-redaction` steht jetzt fest im Test.
- **Commits:** 265764f, ee7b163

**4. [Rule 3 - Blocking] LICENSE und img/ außerhalb des Build-Kontexts**
- **Fix:** `COPY LICENSE` und `COPY img` sind aus dem Dockerfile entfernt. Ein Kommentar erklärt: Lizenz im OCI-Label, Icons trägt die PHP-App.
- **Commit:** 265764f

**5. [Rule 2 - Owner-Regel] FR-Texte der Backend-info.xml ohne U+00A0**
- **Fix:** U+00A0 vor `: ; ? !` und innerhalb von « » in der FR-Beschreibung und der FR-Zusammenfassung.
- **Commit:** 265764f

**6. [Rule 3 - Blocking] test_workflow_pins.py hatte ein eigenes REPO_ROOT = parents[1]**
- **Fix:** auf `parents[2]` umgestellt.
- **Commit:** 265764f

**7. [Rule 1 - Bug] Zwei Fehler in den AVS-Vorlagen zum Stand 7d11d76**
- **Issue:** Die AVS-Datei `php/composer.json` hatte im Namensraum einfache Backslashes (`"OCA\AudioVideoSearch\\"` ist ungültiges JSON, Pitfall 1). `php/tests/bootstrap.php` hatte `rtrim($serverRoot, '/\')`, ein PHP-Syntaxfehler. AVS hat beides später korrigiert.
- **Fix:** Doppelte Backslashes (per `json.loads` geprüft) und `'/\\'`.
- **Commit:** f8e27f6

**8. [Rule 2 - Missing] phpunit-Job wäre leer gelaufen**
- **Issue:** `failOnEmptyTestSuite` plus fehlende Tests ergeben einen roten CI-Job. AVS hatte das bis Plan 03 aufgeschoben.
- **Fix:** `php/tests/Unit/AppInfo/ApplicationTest.php` prüft die beiden eingefrorenen App-IDs.
- **Commit:** f8e27f6

**9. [Rule 2] Leeres routes-Element zusätzlich in deploy-harp und Dockerignore gehärtet**
- Die Negativprüfung testet anonym und mit Admin-Login und prüft zusätzlich, dass kein `app_id`-JSON zurückkommt. `.dockerignore` hält jetzt auch `.env*` und `coverage.xml` heraus.
- **Commits:** ee7b163

Kleinere Ergänzungen: `.gitignore` deckt zusätzlich `php/vendor/`, `php/.phpunit.cache/` und `php/junit.xml` ab. `php.yml` steht in der Pflichtliste von `test_workflows.py`. `l10n_js.py` nimmt ohne `--root` nur Wurzeln, die existieren (`php/l10n` kommt erst mit Plan 11). Ruff, pyright und vulture laufen über `../scripts` mit.

Hinweis zur Prüfung: `grep -cF 'OCA\\PiiRedaction\\' php/composer.json` liefert in Git Bash unter Windows 0, obwohl die Bytes stimmen (per od geprüft). Python zählt 2 Treffer, `json.loads` liefert `OCA\PiiRedaction\`.

## Hinweise für den Owner

- Mit pymupdf 2.1 kamen über onnxruntime zwei transitive Pakete in den Lock, die in der Freigabeliste nicht einzeln standen: **flatbuffers 25.12.19** und **protobuf 7.36.2** (beide Google, Pflichtabhängigkeiten von onnxruntime 1.31.1). Ich habe sie als Teil der freigegebenen pymupdf-Kette behandelt. Wenn der Owner das anders sieht: vor dem ersten Push melden.
- numpy steht über diese Kette auf 2.5.4. Presidio verlangt später `<2.5.0`, siehe `deferred-items.md`.

## Deferred Issues

Siehe `deferred-items.md`: `release.yml`, `store-submit.yml` und `scripts/release/store-archive.sh` sind noch im Wurzel-Layout, `CONTRIBUTING.md` nennt alte Pfade, PHP ist nur statisch geprüft (Laufbeweis in CI), dazu der numpy-Deckel.

## Known Stubs

- `php/lib/AppInfo/Application.php`: `register()` und `boot()` sind absichtlich leer. Notifier und Listener trägt Plan 14 ein.

## Threat Flags

Keine neue Angriffsfläche. Das Backend hat jetzt weniger Fläche als vorher, weil `^/status` als Browser-Route entfallen ist.

## Self-Check: PASSED

- Dateien vorhanden: backend/src/pii_redaction_backend/main.py, backend/appinfo/info.xml, php/appinfo/info.xml, php/lib/AppInfo/Application.php, backend/tests/test_lockstep_versions.py, .github/workflows/php.yml
- Commits vorhanden: 265764f, ee7b163, f8e27f6

## Nachtrag Owner-Freigabe (2026-11-07)

Transitive Pakete über onnxruntime (pymupdf-Kette): flatbuffers 25.12.19 und protobuf 7.36.2. Owner-Antwort im Claude-Code-Terminal auf die Frage "Freigeben?": "Freigeben (Empfohlen)".
