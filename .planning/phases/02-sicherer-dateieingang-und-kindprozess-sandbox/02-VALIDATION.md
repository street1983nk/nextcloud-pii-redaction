---
phase: 2
slug: sicherer-dateieingang-und-kindprozess-sandbox
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-11-16
---

# Phase 2 , Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend, .venv), phpunit 11.5.x (php/, CI), Workflow-Gates (test_workflows.py, test_workflow_pins.py), Container-Suite `pytest -m container` in sandbox.yml |
| **Config file** | backend/pyproject.toml (Marker container, linux ab Plan 02-02), backend/tests/conftest.py (Hook pytest_collection_modifyitems ab Plan 02-07: container nur mit PII_IN_CONTAINER=1, linux nur auf Linux), php/phpunit.xml |
| **Quick run command** | `cd backend && uv run pytest tests/<berührter Bereich> -x -q` |
| **Full suite command** | `cd backend && uv run ruff check --no-cache . && uv run ruff format --check --no-cache . && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright --pythonpath .venv/Scripts/python.exe && uv run vulture && uv run pytest -q` |
| **Estimated runtime** | Backend-Vollsuite einige Minuten lokal (Container- und Linux-Tests dort per Hook skipped, nie failed); PHP, Linux-Kernel-Tests und Container-Suite nur in CI |
| **Besonderheit** | Docker bleibt lokal AUS: Container-Messungen (seccomp/Landlock-Probe, Geheimnis-Lesewege, LibreOffice-Netzmitschnitt, --network none, frpc-0711-Wirkung A1, VmPeak LibreOffice) laufen NUR in sandbox.yml; lokale Tests prüfen Logik mit Fakes. Korpus per ci/make_corpus.py, keine Binärdateien im Repo. Linux-Tests (Marker linux) laufen in python.yml auf ubuntu-24.04. |

---

## Sampling Rate

- **After every task commit:** Quick run des berührten Bereichs
- **After every plan wave:** Full suite (backend) plus Workflow-Gates
- **Nach Welle 3:** Push 02-16, python.yml/php.yml/security.yml/sandbox.yml grün (sandbox.yml: Teststufe baut, Container startet mit --network none, Smoke-Container-Test 02-14 mit /heartbeat und /status sandbox grün, Bridge im Smoke-Rückfall mit 0 Paketen; Exit 5, `|| true` und continue-on-error sind per Gate verboten)
- **Before `/gsd:verify-work`:** Full suite grün, CI-Beweise (sandbox.yml amd64+arm64 inkl. Mitschnitt, deploy-harp mit refusals.sh und Playwright) grün (Plan 02-24), ARs entschieden (02-25), dann `/gsd:secure-phase`
- **Max feedback latency:** 240 seconds (lokal)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-1 | 01 | 1 | JOB-05 | T-02-33 | Texte nur Grund, nie Inhalt | doc-check | `grep -c ... 02-TEXTS.md` (Plan) | ❌ W0 | ⬜ pending |
| 02-01-2 | 01 | 1 | JOB-05 | T-02-33 | Owner-Freigabe D-02-03 | manual | Checkpoint | - | ⬜ pending |
| 02-02-1 | 02 | 1 | RES-02 | T-02-SC | Paket-Freigabe vor Lock | manual | Checkpoint blocking-human | - | ⬜ pending |
| 02-02-2 | 02 | 1 | RES-02, SAFE-02 | T-02-SC, T-02-34 | exakte Pins, torch nur CPU-Index | unit | `cd backend && uv run pytest -q tests/test_dependencies.py` | ❌ W0 | ⬜ pending |
| 02-03-1 | 03 | 1 | SAFE-01 | T-02-05, T-02-02 | Profile ohne NPROC, ohne Geheimnispfade | unit | `cd backend && uv run pytest -q tests/test_jail_profiles.py` | ❌ W0 | ⬜ pending |
| 02-03-2 | 03 | 1 | SAFE-01 | T-02-04, T-02-01, T-02-26 | seccomp-Denylist, Landlock-ABI, fail closed | unit + linux | `cd backend && uv run pytest -q tests/test_seccomp.py tests/test_landlock.py` | ❌ W0 | ⬜ pending |
| 02-04-1 | 04 | 1 | SAFE-02, JOB-05 | T-02-12, T-02-35 | Magic an Offset 0, CFB-Verschlüsselung, feste Grenzen | tdd | `cd backend && uv run pytest -q tests/test_intake_limits.py tests/test_intake_magic.py` | ❌ W0 | ⬜ pending |
| 02-04-2 | 04 | 1 | SAFE-02 | T-02-08, T-02-09 | ZIP zählen vor ZipFile, Doppelnamen, Traversal | tdd | `cd backend && uv run pytest -q tests/test_intake_zip.py` | ❌ W0 | ⬜ pending |
| 02-05-1 | 05 | 1 | JOB-05 | T-02-36 | Lockstep Python/PHP | unit | `cd backend && uv run pytest -q tests/test_model.py tests/test_php_schema.py` | ✅ | ⬜ pending |
| 02-05-2 | 05 | 1 | JOB-05 | T-02-37 | Protokoll-Aktionen <= 32 Zeichen | unit | `cd backend && uv run pytest -q tests/test_php_schema.py` | ✅ | ⬜ pending |
| 02-06-1 | 06 | 1 | SAFE-01, RES-02 | T-02-02, T-02-21, T-02-38 | frpc 0711, Offline-ENV, start.sh-Hash | unit | `cd backend && uv run pytest -q tests/test_dockerfile.py` | ✅ | ⬜ pending |
| 02-06-2 | 06 | 1 | SAFE-01 | T-02-23 | Teststufe nie gepusht | unit | `cd backend && uv run pytest -q tests/test_dockerfile.py tests/test_workflows.py` | ✅ | ⬜ pending |
| 02-07-1 | 07 | 1 | SAFE-04 | T-02-29, T-02-40 | Korpus unabhängig geprüft | unit | `cd backend && uv run pytest -q tests/test_ci_corpus.py -k "zip or xml or docx or odt"` | ❌ W0 | ⬜ pending |
| 02-07-2 | 07 | 1 | SAFE-04 | T-02-39 | PDF-Korpus, Positivkontrollen, Marker-Hook container/linux mit Positivkontrolle, record_measurement | unit | `cd backend && uv run pytest -q tests/test_ci_corpus.py tests/test_collection_markers.py && uv run pytest -q` | ❌ W0 | ⬜ pending |
| 02-08-1 | 08 | 2 | SAFE-01 | T-02-07, T-02-26 | Jail-Reihenfolge, Exit 71 | unit + linux | `cd backend && uv run pytest -q tests/test_jail.py` | ❌ W0 | ⬜ pending |
| 02-08-2 | 08 | 2 | SAFE-01 | T-02-06, T-02-41 | Reaper, Spawn-Gate | unit + linux | `cd backend && uv run pytest -q tests/test_reaper.py tests/test_child.py tests/test_spawn_gate.py` | ❌ W0 | ⬜ pending |
| 02-09-1 | 09 | 2 | SAFE-02 | T-02-10, T-02-42 | DOCTYPE/Entitäten abgelehnt | tdd | `cd backend && uv run pytest -q tests/test_intake_xml.py` | ❌ W0 | ⬜ pending |
| 02-09-2 | 09 | 2 | SAFE-02, JOB-05 | T-02-11, T-02-43, T-02-19 | PDF-Grenzen, Passwort, Signatur | tdd | `cd backend && uv run pytest -q tests/test_intake_pdf.py` | ❌ W0 | ⬜ pending |
| 02-10-1 | 10 | 2 | RES-02 | T-02-21 | tldextract offline, Tripwire mit Positivkontrolle | unit | `cd backend && uv run pytest -q tests/test_offline.py -k "configure or tripwire or email"` | ❌ W0 | ⬜ pending |
| 02-10-2 | 10 | 2 | RES-02 | T-02-22 | AST-Gate Netz-APIs | unit | `cd backend && uv run pytest -q tests/test_offline.py` | ❌ W0 | ⬜ pending |
| 02-11-1 | 11 | 2 | JOB-05 | T-02-16, T-02-17 | E2E am Ordner, SSE nicht | phpunit | `composer test` in php.yml; lokal `uv run pytest -q tests/test_php_gates.py` | ✅ | ⬜ pending |
| 02-11-2 | 11 | 2 | JOB-05 | T-02-19, T-02-45 | Bestätigungszustände mit Protokoll, Events leben so lange wie der Auftrag (Gate mit Selbsttest) | phpunit + gate | php.yml; lokal `uv run pytest -q tests/test_php_gates.py` | ✅ | ⬜ pending |
| 02-12-1 | 12 | 2 | RES-02 | T-02-25 | Modelle mit sha256 und Host-Allowlist | unit | `cd backend && uv run pytest -q tests/test_ci_fetch_models.py` | ❌ W0 | ⬜ pending |
| 02-12-2 | 12 | 2 | SAFE-04, RES-02 | T-02-24, T-02-23, T-02-04 | sandbox.yml mit --network none und Mitschnitt, PII_IN_CONTAINER=1, Bridge nur mit vorhandener Datei sonst Smoke, kein Exit-5-Durchlass | unit (Gate) | `cd backend && uv run pytest -q tests/test_workflows.py tests/test_workflow_pins.py` | ✅ | ⬜ pending |
| 02-13-1 | 13 | 3 | SAFE-03 | T-02-13, T-02-14 | DOCX bereinigt | tdd | `cd backend && uv run pytest -q tests/test_sanitize.py -k docx` | ❌ W0 | ⬜ pending |
| 02-13-2 | 13 | 3 | SAFE-03 | T-02-47 | ODT bereinigt, Gegenprobe | tdd | `cd backend && uv run pytest -q tests/test_sanitize.py` | ❌ W0 | ⬜ pending |
| 02-14-1 | 14 | 3 | SAFE-01 | T-02-01, T-02-06, T-02-26 | Server nicht dumpbar, Probe vor Runner, mark_jail_failed sticky mit Log-Wort | unit + linux | `cd backend && uv run pytest -q tests/test_probe.py tests/test_main.py` | ❌ W0 | ⬜ pending |
| 02-14-2 | 14 | 3 | SAFE-01 | T-02-26, T-02-20 | /status sandbox, Log-Allowlist, Smoke-Container-Test (heartbeat, /status) | unit + container | `cd backend && uv run pytest -q tests/test_api_routes.py tests/test_log_calls.py tests/test_container_smoke.py`; sandbox.yml: `pytest -m container tests/test_container_smoke.py` | ❌ W0 | ⬜ pending |
| 02-15-1 | 15 | 3 | JOB-05 | T-02-32, T-02-48 | Claim expected/confirmed, Ack-Flags geprüft | phpunit | php.yml; lokal `uv run pytest -q tests/test_php_gates.py` | ✅ | ⬜ pending |
| 02-15-2 | 15 | 3 | JOB-05 | T-02-18 | confirm/decline nur Auftraggeber, CSRF | phpunit | php.yml; lokal `uv run pytest -q tests/test_php_gates.py` | ✅ | ⬜ pending |
| 02-16-1 | 16 | 4 | alle | T-02-31 | Push-Freigabe je SHA | manual | Checkpoint | - | ⬜ pending |
| 02-16-2 | 16 | 4 | SAFE-01..03, JOB-05, RES-02 | T-02-31 | CI grün (Linux, PHP, Image-Build, Smoke-Container-Test, Bridge-Smoke 0 Pakete) | ci | `gh run list --branch phase-02 --limit 8 --json name,conclusion,headSha` | - | ⬜ pending |
| 02-17-1 | 17 | 4 | SAFE-01, SAFE-02 | T-02-15, T-02-20 | Kinder liefern geschlossene Antworten | unit | `cd backend && uv run pytest -q tests/test_precheck_worker.py tests/test_sanitize_worker.py` | ❌ W0 | ⬜ pending |
| 02-17-2 | 17 | 4 | SAFE-03 | T-02-14, T-02-13, T-02-28 | LO-Profil gehärtet, je Auftrag | unit | `cd backend && uv run pytest -q tests/test_soffice_profile.py` | ❌ W0 | ⬜ pending |
| 02-18-1 | 18 | 4 | JOB-05 | T-02-30, T-02-18 | Karte ohne v-html, Bestätigung | build + unit | `cd php && npm run build && cd ../backend && uv run pytest -q tests/test_ui_assets.py tests/test_public_texts.py` | ✅ | ⬜ pending |
| 02-18-2 | 18 | 4 | JOB-05 | T-02-33 | dreisprachiger Gleichstand | unit | `cd backend && uv run pytest -q tests/test_trilingual.py` | ✅ | ⬜ pending |
| 02-19-1 | 19 | 5 | JOB-05 | T-02-32 | Claim/Ack strikt | unit | `cd backend && uv run pytest -q tests/test_nc.py` | ✅ | ⬜ pending |
| 02-19-2 | 19 | 5 | SAFE-01..03, JOB-05 | T-02-15, T-02-49, T-02-13, T-02-27, T-02-26 | Vorprüfung, confirm, Bereiniger, 300-Seiten-Deckel im Ablauf, Exit 71 -> mark_jail_failed | unit | `cd backend && uv run pytest -q tests/test_runner.py` | ✅ | ⬜ pending |
| 02-20-1 | 20 | 5 | SAFE-01 | T-02-26, T-02-50 | sandbox-Feld nur feste Wörter | phpunit | php.yml; lokal `uv run pytest -q tests/test_php_gates.py` | ✅ | ⬜ pending |
| 02-20-2 | 20 | 5 | SAFE-01 | T-02-50 | Admin-Hinweis ohne innerHTML, jail-Zeile | build + unit | `cd php && npm run build && cd ../backend && uv run pytest -q tests/test_ui_assets.py tests/test_php_gates.py` | ✅ | ⬜ pending |
| 02-20-3 | 20 | 5 | SAFE-01 | T-02-33 | Kataloge DE/de_DE/EN/FR im Gleichstand | unit | `cd backend && uv run pytest -q tests/test_trilingual.py tests/test_public_texts.py && uv run python ../scripts/l10n_js.py --check` | ✅ | ⬜ pending |
| 02-21-1 | 21 | 6 | SAFE-01 | T-02-01, T-02-02, T-02-03, T-02-06 | Jail-Lesewege hart gesperrt, Grenzen, Gruppen-Kill, keine Zombies; A1 nur gemessen (a1_frpc_environ, kein Assert), VmPeak gemessen | container | sandbox.yml: `pytest -m container tests/test_jail_container.py` | ❌ W0 | ⬜ pending |
| 02-21-2 | 21 | 6 | SAFE-04 | T-02-08 | Korpus abgewiesen, Container lebt | container | sandbox.yml: `pytest -m container tests/test_corpus.py` | ❌ W0 | ⬜ pending |
| 02-22-1 | 22 | 6 | SAFE-03 | T-02-13, T-02-14, T-02-51 | 0 Verbindungen, Schichtläufe, Positivkontrolle, Mitschnitt | container | sandbox.yml: `pytest -m container tests/test_lo_network.py` | ❌ W0 | ⬜ pending |
| 02-22-2 | 22 | 6 | RES-02 | T-02-21, T-02-22 | Stapel offline unter --network none | container | sandbox.yml: `pytest -m container tests/test_offline_container.py` | ❌ W0 | ⬜ pending |
| 02-23-1 | 23 | 6 | JOB-05 | T-02-16, T-02-52 | E2E-Gründe, keine Benachrichtigung | e2e (deploy-harp) | `cd backend && uv run pytest -q tests/test_workflows.py`; Lauf in deploy-harp | ❌ W0 | ⬜ pending |
| 02-23-2 | 23 | 6 | JOB-05 | T-02-18 | Karten in 3 Breiten hell/dunkel | e2e (Playwright) | `cd ci/playwright && npx tsc --noEmit -p tsconfig.json` | ✅ | ⬜ pending |
| 02-24-1 | 24 | 7 | alle | T-02-31 | Push-Freigabe je SHA | manual | Checkpoint | - | ⬜ pending |
| 02-24-2 | 24 | 7 | alle | T-02-02 | alle Beweise grün, Messwerte in 02-MEASUREMENTS.json, Bridge ohne Smoke-Rückfall, A1 entschieden | ci | `gh run list --branch phase-02 --limit 10 --json name,conclusion,headSha` | - | ⬜ pending |
| 02-24-3 | 24 | 7 | SAFE-01 | T-02-53 | RLIMIT_AS soffice aus Messung | unit + container | `cd backend && uv run pytest -q tests/test_jail_profiles.py` | ✅ (ab 02-03) | ⬜ pending |
| 02-25-1 | 25 | 8 | SAFE-01 | T-02-05, T-02-26 | AR-Vorlagen mit Messwert, Exit-71-Abbildung namentlich | doc-check | `grep -c "^## AR-02-" 02-ACCEPTED-RISKS.md` | ❌ | ⬜ pending |
| 02-25-2 | 25 | 8 | SAFE-01 | T-02-26 | ARs einzeln entschieden | manual | Checkpoint | - | ⬜ pending |
| 02-25-3 | 25 | 8 | JOB-05 | - | UI gemeinsam abgenommen | manual | Checkpoint (Playwright-Fotos) | - | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Korpus-Erzeuger ci/make_corpus.py mit Selbsttest und Positivkontrollen (Plan 02-07, Welle 1)
- [ ] ctypes-Module seccomp/Landlock mit Laufzeitprobe und Fakes (Plan 02-03, Welle 1)
- [ ] pytest-Marker container/linux und python.yml `-m "not container"` (Plan 02-02, Welle 1)
- [ ] Sammel-Hook in conftest (container nur mit PII_IN_CONTAINER=1, linux nur auf Linux) mit Positivkontrolle, Helfer record_measurement (Plan 02-07, Welle 1)
- [ ] Smoke-Container-Test als erster Container-Test für sandbox.yml (Plan 02-14, Welle 3)
- [ ] Dockerfile-Teststufe und sandbox.yml (Pläne 02-06, 02-12)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Owner-Freigabe neuer Texte (Ablehnungsgründe, Signatur-Bestätigung, Makro-Meldung, Admin-Hinweis) | JOB-05, D-02-01..04, D-02-11, D-02-12 | Textfreigabe vor dem Bau ist Owner-Entscheid | Plan 02-01 Task 2 |
| Paket-Freigabe und Lock-Diff | RES-02 (D-02-09) | Package Legitimacy Gate | Plan 02-02 Task 1 |
| Push-Freigaben je SHA | alle | Owner-Regel | Pläne 02-16, 02-24 |
| AR-Vorlagen (Isolation-Restrisiken) | D-02-05, D-02-11, D-02-14 | ARs legt der Owner einzeln fest | Plan 02-25 Task 2 |
| Gemeinsame UI-Abnahme per Playwright | JOB-05 | Owner-Regel UI-Abnahme | Plan 02-25 Task 3 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (Checkpoints ausgenommen)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 240s (lokal; Container-Beweise in CI)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (Ausführung)
