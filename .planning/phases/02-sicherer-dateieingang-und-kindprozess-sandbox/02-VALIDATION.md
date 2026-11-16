---
phase: 2
slug: sicherer-dateieingang-und-kindprozess-sandbox
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-11-16
---

# Phase 2 , Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend, .venv), phpunit 11.5.x (php/, CI), Workflow-Gates (test_workflows.py, test_workflow_pins.py) |
| **Config file** | backend/pyproject.toml, php/phpunit.xml |
| **Quick run command** | `cd backend && uv run pytest tests/<berührter Bereich> -x -q` |
| **Full suite command** | `cd backend && uv run ruff check --no-cache . && uv run ruff format --check --no-cache . && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright --pythonpath .venv/Scripts/python.exe && uv run vulture && uv run pytest -q` |
| **Estimated runtime** | Backend-Vollsuite einige Minuten lokal; PHP in CI |
| **Besonderheit** | Docker bleibt lokal AUS: alle Container-Messungen (seccomp/Landlock-Probe, LibreOffice-Netzmitschnitt, --network none, frpc-0711-Wirkung A1) laufen NUR in CI; lokale Tests prüfen Logik mit Fakes. Korpus (Bomben, XXE, Doppelnamen, External-Rels) wird per Skript erzeugt, keine Binärdateien im Repo. |

---

## Sampling Rate

- **After every task commit:** Quick run des berührten Bereichs
- **After every plan wave:** Full suite (backend) plus Workflow-Gates
- **Before `/gsd:verify-work`:** Full suite grün, CI-Beweise (Korpus-Job, --network-none-Job, Sandbox-Probe) grün
- **Max feedback latency:** 240 seconds

---

## Per-Task Verification Map

> Wird vom Planner je Task gefüllt (Task-IDs entstehen erst mit den PLAN.md-Dateien).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (vom Planner zu füllen) | | | SAFE-01..04, JOB-05, RES-02 | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Korpus-Erzeuger-Skripte (scripts/ci/ oder backend/tests/corpus/) mit Selbsttest (Positivkontrolle: harmlose Datei passiert, Bombe wird abgewiesen)
- [ ] ctypes-Module seccomp/Landlock mit Capability-Probe (Laufzeit-Erkennung), Fakes für lokale Tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Owner-Freigabe neuer Texte (Ablehnungsgründe, Signatur-Bestätigung, Makro-Meldung) | JOB-05, D-02-01..04, D-02-12 | Textfreigabe vor dem Bau ist Owner-Entscheid | Textliste DE/EN/FR vorlegen |
| AR-Vorlagen (Isolation-Restrisiken) | D-02-05, D-02-11 | ARs legt der Owner einzeln fest | je AR eine Frage |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 240s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
