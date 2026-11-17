---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 12
subsystem: ci
tags: [sandbox, network-proof, models, safe-04, res-02]
requires: [02-06, 02-07]
provides: [.github/workflows/sandbox.yml, ci/fetch_models.py]
affects: [02-14, 02-16, 02-21, 02-22, 02-24]
key-files:
  created:
    - .github/workflows/sandbox.yml
    - ci/fetch_models.py
    - backend/tests/test_ci_fetch_models.py
  modified:
    - backend/tests/test_workflows.py
decisions:
  - "Kanarien-Zertifikatsordner wird auf dem Runner angelegt (uid 10001, 0600) und als /certs/frp:ro eingehängt; alle drei Dateien (client.key, client.crt, ca.crt), weil entrypoint.sh sonst 60 s auf HaRP wartet"
  - "Heartbeat über den Unix-Socket /tmp/exapp.sock (HP_SHARED_KEY gesetzt = HaRP-Modus), HP_FRP_ADDRESS=127.0.0.1, damit frpc nur Loopback versucht und der docker0-Mitschnitt leer bleiben kann"
  - "PID-1-Beleg über /proc/1/cmdline mit pii_redaction_backend.main"
  - "actions/cache@55cc8345... (v6.1.0) wie im AV-Repo; checkout mit persist-credentials: false"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 12: CI-Bühne für Container-Beweise Summary

`sandbox.yml` baut je Architektur die Teststufe lokal (nie gepusht), startet den Server als PID 1 mit Kanarien in APP_SECRET, HP_SHARED_KEY und /certs/frp, führt `pytest -m container` unter `--network none` aus und wiederholt im Bridge-Netz unter einem docker0-Mitschnitt, der leer bleiben muss; `ci/fetch_models.py` lädt die sechs Modelldateien mit festen sha256 und Host-Allowlist in den Runner-Cache.

## Commits

| Schritt | Commit |
|---|---|
| Task 1 Tests | 50f8f08 |
| Task 1 fetch_models.py | b0524f7 |
| Task 2 Workflow-Regeln | e9ee820 |
| Task 2 sandbox.yml | 4d7c878 |

## Prüfung

- Suite 958 passed, 14 skipped; ruff, Format, pyright (latest) 0, vulture, workflow_pins, dockerfile grün.
- fetch_models ohne Netz getestet: Tabelle gegen CLAUDE.md, Allowlist inkl. Täuschungshosts, Weiterleitung und Endadresse auf fremdem Host, falscher Hash ohne Rest, fünf Zip-Slip-Formen, Cache-Treffer ohne erneuten Abruf, Positivkontrolle mit passenden Dateien.
- Erster echter Lauf erst nach dem Push-Tor 02-16; bis 02-14 sammelt `-m container` nichts (Exit 5 würde den Lauf zu Recht scheitern lassen, keine Ausnahme eingebaut).

## Deviations from Plan

- [Rule 2] `persist-credentials: false` am Checkout (kein Token in .git/config neben einem Lauf mit fremdem Code).
- [Rule 3] Zertifikate per Host-Mount statt `docker exec -u 10001` (Container-Wurzel ist für 10001 nicht beschreibbar, und entrypoint.sh wartet auf alle drei Dateien vor dem Start).
- Kommentar in sandbox.yml ohne die verbotenen Muster formuliert, damit das Gate nicht an Prosa anschlägt.
- TDD-Reihenfolge: Tests und Umsetzung entstanden zusammen; Test-Commit liegt vor dem Umsetzungs-Commit.

## Threat Flags

Keine neuen; Kanarienwerte sind je Lauf erzeugte Attrappen (T-02-46 accept).

## Self-Check: PASSED
