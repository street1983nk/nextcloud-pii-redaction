---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 08
subsystem: sandbox
tags: [jail, reaper, safe-01, spawn-gate]
requires: [02-03]
provides: [sandbox.jail main/jail_argv/parse/Ops, sandbox.reaper reap_group/become_subreaper, run_child(profile=, read=, write=)]
affects: [02-13, 02-14, 02-17, 02-19, 02-21, 02-22]
key-files:
  created:
    - backend/src/pii_redaction_backend/sandbox/jail.py
    - backend/src/pii_redaction_backend/sandbox/reaper.py
    - backend/tests/test_jail.py
    - backend/tests/test_reaper.py
    - backend/tests/test_spawn_gate.py
  modified:
    - backend/src/pii_redaction_backend/workers/child.py
    - backend/src/pii_redaction_backend/workers/soffice.py
    - backend/src/pii_redaction_backend/runner/runner.py
    - backend/tests/test_child.py
    - backend/tests/test_runner.py
    - backend/tests/test_render.py
decisions:
  - "Jail ausserhalb von Linux: Exit 71, es startet nichts (keine rlimits, kein prctl); echte Kind-Tests sind daher alle linux-markiert"
  - "soffice wird mit absolutem Pfad /usr/bin/soffice gestartet (execv sucht nicht im PATH); Profilordner /tmp/lo-<job> wird vor dem Lauf angelegt, weil Landlock nur existierende Pfade freigibt"
  - "reap_group wartet nach killpg höchstens 1 s (10-ms-Takt) auf noch sterbende Gruppenmitglieder statt beim ersten pid 0 aufzuhören"
  - "Linux-Echtlauf liest die Grenzen per resource.getrlimit im Kind statt /proc/self/limits, weil /proc ausserhalb der Landlock-Lesepfade liegt"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 08: Jail und Gruppen-Reaper Summary

Jedes Kind startet jetzt als `python -I -m pii_redaction_backend.sandbox.jail <profil> [--read P] [--write P] -- <befehl>`: rlimits (Core 0, nie NPROC), NO_NEW_PRIVS, Landlock, seccomp in fester Reihenfolge, dann `os.execv`; nach jedem Kind tötet und sammelt `reap_group` die ganze Gruppe; ein AST-Gate hält Prozessstart in `workers/child.py` und exec im Jail fest.

## Commits

| Schritt | Commit |
|---|---|
| Task 1 RED: Jail-Tests | f7ed7fd |
| Task 1 GREEN: jail.py | 905ac1e |
| Task 2 RED: Reaper, run_child, Spawn-Gate | eb6b57d |
| Task 2 GREEN: Reaper, run_child, Aufrufer | 0ece427 |

## Prüfung

- Suite 804 passed, 14 skipped (vorher 703/7); ruff-Vollsatz, Format, pyright (latest) 0 Fehler, vulture grün.
- RED belegt für Task 1 (Sammelfehler ohne jail.py), danach 35 passed, 2 skipped.
- Linux-Fälle (echte Grenzen, seccomp-Socket, Reaper nach Zeitlimit und Erfolg, Subreaper, echte Render-Kette im Runner) laufen erst in python.yml nach dem Push-Tor 02-16; lokal Skip über `pytest.mark.linux` plus `skipif`, Skip-Logik selbst ist durch 02-07 (`test_collection_markers.py`) positiv geprüft.
- `grep -rn "waitpid(-1" backend/src` ohne Treffer.

## Deviations from Plan

**1. [Rule 1 - Sicherheitslücke im Gate, durch Positivkontrolle gefunden]** Das Spawn-Gate prüfte zunächst nur Aufrufe. Die Positivkontrolle (jail.py an fremdem Ort muss anschlagen) blieb stumm, weil jail.py `execv=os.execv` als Wert übergibt. Gate wertet jetzt jede Referenz (Attribut oder importierter Name) wie einen Aufruf; drei neue Proben (`run = os.execv`, `start(execv=os.execv)`, `go = asyncio.create_subprocess_exec`). Commit eb6b57d.

**2. [Rule 3 - Blocker] soffice mit absolutem Pfad.** `execv` sucht nicht im PATH; `command()` nennt jetzt `/usr/bin/soffice`, test_render angepasst. Commit 0ece427.

**3. [Rule 1 - Bug] Profilordner vor dem Lauf anlegen.** Landlock überspringt nicht existierende Pfade; ohne `mkdir` hätte LibreOffice sein Profil nicht schreiben dürfen. Commit 0ece427.

**4. [Rule 3] Echte Kind-Tests nur unter Linux.** `test_analyze_through_the_real_render_child` (test_runner) und die drei Verhaltens-Tests in test_child liefen bisher auch unter Windows; das Jail startet ausserhalb Linux bewusst nichts. Jetzt `linux`-markiert, laufen in python.yml.

**5. Gate-Reihenfolge:** Task 1 wurde vor dem vollen Suite-Lauf committet (nur Teilsuite + ruff); der volle Gate-Lauf kam mit Task 2. Kein Befund daraus.

## Threat Flags

Keine neue Angriffsfläche über das Bedrohungsmodell hinaus.

## Self-Check: PASSED
