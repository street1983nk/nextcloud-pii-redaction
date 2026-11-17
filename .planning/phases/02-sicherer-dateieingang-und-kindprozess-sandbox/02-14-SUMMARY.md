---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 14
subsystem: sandbox
tags: [probe, dumpable, status, safe-01, container-smoke]
requires: [02-07, 02-08]
provides: [sandbox.probe run/current/mark_jail_failed/SandboxState, main.harden_process, /status sandbox, tests/test_container_smoke.py]
affects: [02-16, 02-19, 02-20, 02-24, 02-25]
key-files:
  created:
    - backend/src/pii_redaction_backend/sandbox/probe.py
    - backend/tests/test_probe.py
    - backend/tests/test_container_smoke.py
  modified:
    - backend/src/pii_redaction_backend/main.py
    - backend/src/pii_redaction_backend/api/status.py
    - backend/src/pii_redaction_backend/logs.py
    - backend/tests/test_main.py
    - backend/tests/test_log_calls.py
    - backend/tests/test_logs.py
decisions:
  - "Probe-Ordner unter <storage>/work/probe-*, weil das Jail jeden anderen Schreibpfad auf dem Volume ablehnt; er wird danach entfernt"
  - "Smoke-Test spricht hinter HaRP (HP_SHARED_KEY gesetzt) den Unix-Socket an, sonst APP_PORT; in sandbox.yml ist HaRP-Modus aktiv"
  - "Off Linux meldet die Probe jail failed (das Jail startet dort bewusst nichts); lokal unter Windows also erwartbar"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 14: Server-Härtung und Schutzzustand Summary

`main()` macht den Server als erste Handlung nicht dumpbar und zum Subreaper; die Lifespan führt vor dem Runner eine Fähigkeitsprobe aus (seccomp, Landlock-ABI, ein Jail-Lauf mit /bin/true) und `/status` zeigt `sandbox: {seccomp, landlock, landlockAbi, jail}` in festen Wörtern; `mark_jail_failed()` hält einen Exit-71-Fall dauerhaft sichtbar; `test_container_smoke.py` ist der erste Container-Test für sandbox.yml.

## Commits

| Schritt | Commit |
|---|---|
| Tests | 4dc8f1f |
| Umsetzung | 6e8e75b |

## Prüfung

- Suite 1008 passed, 18 skipped; ruff, Format, pyright (latest) 0, vulture, Log-Gate grün.
- Smoke-Test lokal 3x skipped "container only" (Marker-Hook), Dumpable-Kindtest skipped "needs Linux"; beide laufen erst nach dem Push-Tor 02-16 (python.yml bzw. sandbox.yml amd64/arm64).
- Positivkontrollen: frischer Prozess dumpable 1, gehärteter 0 (Linux); falsches Geheimnis am Container-/status ergibt 401.

## Deviations from Plan

- [Rule 3] `tests/test_logs.py` (Skelett-Schlüsselmenge) um die vier Sandbox-Schlüssel ergänzt; Datei stand nicht in files_modified, das Gate verlangt aber Gleichstand.
- Positivkontroll-Test mit falschem Geheimnis im Smoke-Test zusätzlich.

## Threat Flags

Keine neuen; /status trägt nur feste Wörter und eine Zahl.

## Self-Check: PASSED
