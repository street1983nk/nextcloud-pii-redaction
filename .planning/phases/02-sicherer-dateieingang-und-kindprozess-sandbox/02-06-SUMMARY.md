---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 06
subsystem: image
tags: [docker, frpc, offline, seccomp, test-stage, safe-01, res-02]
requires: []
provides: [frpc 0711, Offline-ENV im Runtime-Image, libseccomp2, Stufen build-test und test, target runtime in docker.yml]
affects: [02-12, 02-21, 02-24]
tech-stack:
  added: []
  patterns: [Dockerfile-Regeln als Textprüfung mit mutierter Probe, start.sh per sha256 festgeschrieben]
key-files:
  created: []
  modified:
    - backend/Dockerfile
    - backend/.dockerignore
    - backend/tests/test_dockerfile.py
    - .github/workflows/docker.yml
decisions:
  - "tests/ wieder im Build-Kontext (für die Teststufe); Schutz vor Auslieferung über die Regel 'runtime kopiert nie tests' und target: runtime beim Push"
  - "Teststufe erbt USER 10001, ENTRYPOINT und HEALTHCHECK aus runtime; Dev-venv aus build-test ersetzt /app/.venv"
metrics:
  completed: 2026-11-16
  tasks: "2/2"
---

# Phase 2 Plan 06: Image-Härtung und Teststufe Summary

frpc nur ausführbar (0711), vier Offline-Variablen im Runtime-ENV, libseccomp2 ausdrücklich installiert, neue Stufen `build-test` und `test` nach `runtime`; docker.yml baut und pusht nur `target: runtime`.

## Commits

| Task | Commit |
|---|---|
| 1 Dockerfile, .dockerignore, Regeln | 74d7e49 |
| 2 docker.yml target runtime | 1e1cf21 |

## Prüfung

Suite 637 passed, 7 skipped; ruff, pyright, vulture grün. Neue Regeln mit Selbsttest: Stufenfolge (Probe mit Stufe debug, Probe mit COPY tests in runtime), frpc-Modus (Probe 0755), Offline-ENV (Probe ohne HF_HUB_OFFLINE), Push-Ziel (Probe ohne target). start.sh unverändert (sha256 8cf550aa...). Ein echter Image-Build läuft erst in CI (Docker lokal tabu).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] .dockerignore schloss tests/ aus**
- Die Teststufe hätte `COPY tests` nicht bauen können. tests/ aus .dockerignore genommen, Begründung im Kopf; neue Regel prüft, dass die runtime-Stufe nie tests kopiert.
- Commit: 74d7e49

**2. [Rule 1 - Bug] Digest-Regel hielt Stufennamen für Images**
- `resolved_bases` erkannte nur `\w+`-Stufennamen und nahm `FROM build`/`FROM runtime` als Basis-Image; jetzt `[\w-]+` und Stufen-Referenzen ausgenommen.
- Commit: 74d7e49

- Der Gate-Test für das Push-Ziel kam mit Commit 74d7e49 ins Repo, die Workflow-Zeile erst mit 1e1cf21 (Zwischenstand allein wäre rot gewesen).

## Self-Check: PASSED
