---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 03
subsystem: sandbox
tags: [sandbox, seccomp, landlock, rlimits, safe-01]
requires: []
provides: [sandbox.profiles (Profile, PROFILES, profile_for), sandbox.seccomp (available, install_network_denylist), sandbox.landlock (abi_version, handled_access, restrict)]
affects: [02-08, 02-14, 02-17]
tech-stack:
  added: []
  patterns: [ctypes-Hülle mit injizierbarer Bibliothek bzw. Syscall-Funktion für Fakes, Probe meldet unavailable, Fehler nach Probe wirft]
key-files:
  created:
    - backend/src/pii_redaction_backend/sandbox/__init__.py
    - backend/src/pii_redaction_backend/sandbox/profiles.py
    - backend/src/pii_redaction_backend/sandbox/seccomp.py
    - backend/src/pii_redaction_backend/sandbox/landlock.py
    - backend/tests/test_jail_profiles.py
    - backend/tests/test_seccomp.py
    - backend/tests/test_landlock.py
  modified: []
decisions:
  - "Profile ohne Schreibpfade auf Systemebene; Auftragspfade kommen in 02-08 dazu; /proc gar nicht freigegeben (auch nicht /proc/self), bis eine Messung es verlangt"
  - "Landlock-Syscall-Hülle als injizierbare Funktion mit Kernel-Konvention (Ergebnis oder minus errno), ganzzahlige Argumente als c_long für variadisches syscall()"
  - "Regeln auf Dateien (nicht Ordner) bekommen nur dateitaugliche Rechte (sonst EINVAL vom Kernel)"
  - "libseccomp setzt no_new_privs beim Laden selbst (Standardattribut NNP); Landlock verlangt es vorher vom Jail"
metrics:
  completed: 2026-11-16
  tasks: "2/2"
---

# Phase 2 Plan 03: Sandbox-Bausteine Summary

Feste Kindprozess-Profile (render, precheck, sanitize, soffice, ocr, detect) mit CPU = Wanduhr + 5 s, AS/FSIZE/NOFILE nach RESEARCH, Core 0, ohne RLIMIT_NPROC; dazu ctypes-Hüllen für eine seccomp-Netzsperre über libseccomp und Landlock-Dateiregeln über die Systemaufrufe 444 bis 446.

## Commits

| Task | Schritt | Commit |
|---|---|---|
| 1 | RED test_jail_profiles.py | bf95825 |
| 1 | GREEN profiles.py | f31f19b |
| 2 | RED test_seccomp.py, test_landlock.py | df02f21 |
| 2 | GREEN seccomp.py, landlock.py | fa43fc8 |

## Prüfung

- Suite lokal (Windows): 554 passed, 7 skipped; ruff check/format, pyright (0 Fehler), vulture grün.
- Linux-Tests (echter Filter: AF_INET/AF_INET6 EACCES nach Positivkontrolle, AF_UNIX offen; echter Landlock-Regelsatz: außerhalb lesen/schreiben verweigert nach Positivkontrolle, /etc und Innenordner gehen; Datei-/Ordner-Rechtemaske) laufen lokal nicht (kein Linux, Docker tabu) und kommen mit python.yml beim Push 02-16.

## Deviations from Plan

- Marker `linux` ist noch nicht registriert (macht 02-02 Task 2 in pyproject); bis dahin zeigt pytest PytestUnknownMarkWarning (5 Warnungen), keine Fehlschläge.
- Linux-Landlock-Test prüft Schreibverbot an einem eigenen Außenordner mit Positivkontrolle statt an /etc (dort hätte schon die Unix-Rechteprüfung verweigert, keine echte Kontrolle).

## Self-Check: PASSED
