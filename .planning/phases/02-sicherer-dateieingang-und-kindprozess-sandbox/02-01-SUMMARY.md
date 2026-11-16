---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 01
subsystem: texte
tags: [texte, l10n, freigabe, d-02-03]
requires: []
provides: [Freigegebene Wortlaute für 02-18 und 02-20]
affects: [02-18, 02-20]
tech-stack:
  added: []
  patterns: []
key-files:
  created: [.planning/phases/02-sicherer-dateieingang-und-kindprozess-sandbox/02-TEXTS.md]
  modified: [.planning/phases/02-sicherer-dateieingang-und-kindprozess-sandbox/deferred-items.md]
decisions:
  - "Phase-2-Texte am 2026-11-16 vom Owner wie entworfen freigegeben (D-02-03)"
  - "de_DE bleibt unpersönlich im Infinitiv wie Phase 1, keine Sie-Form"
  - "e2e-Abhilfe-Rat nur an der Dateikarte, Start-Toast ohne Rat"
  - "Seitengrenze in Ziffern (300); 'neu analysieren' und 'Hilfsprozesse' bleiben; 'Das Original bleibt signiert.' bleibt"
metrics:
  completed: 2026-11-16
  tasks: "2/2"
---

# Phase 2 Plan 01: Texte zur Freigabe Summary

Alle neuen nutzersichtbaren Texte der Phase 2 (zehn Ablehnungsgründe mit Titel und Abhilfe, e2e-Start-Toast, Signatur-Bestätigung, Makro-Hinweis, Stufe `checking`, Admin-Hinweise zu seccomp/Landlock/Schutzschicht) liegen viersprachig in 02-TEXTS.md und sind vom Owner freigegeben.

## Task 1: Textentwurf

Commit 64cd1bf. Sechs Gruppen, Spalten EN/DE/de_DE/FR, keine Gedankenstriche, keine Kürzel im Nutzertext.

## Task 2: Owner-Freigabe (D-02-03)

Freigabe 2026-11-16 ohne Wortlautänderung. Antworten auf die sechs Rückfragen in 02-TEXTS.md vermerkt:

1. de_DE unpersönlich/Infinitiv wie Phase 1
2. e2e-Abhilfe bleibt an der Karte, Toast ohne Rat
3. Ziffern "300"
4. "neu analysieren"
5. "Hilfsprozesse"
6. "Das Original bleibt signiert." bleibt

Hinweis für 02-18 festgehalten (02-TEXTS.md und deferred-items.md): Status `cancelled` mit Grund `signature_declined` darf nicht "Die Datei wurde gelöscht" zeigen.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED
