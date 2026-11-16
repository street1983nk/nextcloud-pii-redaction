---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 07
subsystem: test-corpus
tags: [corpus, safe-04, markers, measurements]
requires: []
provides: [ci/make_corpus.py build(outdir, canary_port, e2e), conftest corpus-Fixture, skip_reason/pytest_collection_modifyitems, record_measurement]
affects: [02-09, 02-12, 02-13, 02-14, 02-17, 02-21, 02-22, 02-23, 02-24]
tech-stack:
  added: []
  patterns: [Korpus per Skript nur mit Standardbibliothek, Selbsttest ohne Umsetzungsmuster (AST-Prüfung)]
key-files:
  created:
    - ci/make_corpus.py
    - backend/tests/test_ci_corpus.py
    - backend/tests/test_collection_markers.py
  modified:
    - backend/tests/conftest.py
    - .gitignore
    - backend/.dockerignore
decisions:
  - "zip_prefix.docx als versteckter Local Header vor den gelisteten Mitgliedern (beginnt mit PK), damit die Vorprüfung unsafe_content sagt; reiner Fremdvorspann wäre schon in Stufe A unsupported_format"
  - "zip_lying_size.docx: document.xml mit 32 MiB Leerzeichen, deklariert 1000 Byte in Central und Local Header; Stufe B erkennt das nicht (unter Ratio-Schwelle), der gestreamte XML-Leser mit Zähler in 02-09 muss es ablehnen"
  - "Besitzer-geschützte PDF wird über metadata['encryption'] (RC4) belegt, nicht über is_encrypted (PyMuPDF meldet nach automatischem Öffnen mit leerem Passwort False)"
  - "Messdatei backend/tests/out/measurements.json in .gitignore und .dockerignore"
metrics:
  completed: 2026-11-16
  tasks: "2/2"
---

# Phase 2 Plan 07: Angriffs-Korpus Summary

49 Korpusdateien per Skript (nur Standardbibliothek, keine Binärdatei im Repo), Manifest mit erwarteten Wörtern, unabhängiger Selbsttest (zipfile, rohes Zentralverzeichnis, PyMuPDF, nie intake/pikepdf), Session-Fixture `corpus`, Marker-Hook für container/linux und Messwert-Helfer.

## Commits

| Schritt | Commit |
|---|---|
| Selbsttest und Marker-Tests | a84a3ba |
| Erzeuger, Fixture, Hook, Messhelfer | 65be213 |

## Prüfung

- Suite 689 passed, 7 skipped; ruff, pyright, vulture grün; Korpus-Erzeugung im Testlauf ca. 3 s.
- PyMuPDF bestätigt das selbst geschriebene RC4-40: Nutzerpasswort-PDF verlangt Passwort und liefert nach `authenticate("geheim")` den Text; Besitzer-PDF öffnet ohne Passwort, Text lesbar, Verschlüsselung RC4.
- Querprobe (nur Scratch, nicht im Repo) Vorprüfung 02-04 gegen das Manifest: alle ZIP-, CFB-, Bytes- und Wrong-Type-Fälle stimmen. Offen bleiben erwartungsgemäß die PDF-Strukturfälle (301 Seiten, MediaBox, Bild, Flate-Bombe, Objekte, Seitenschleife, Passwort, abgeschnitten) und die XML-Fälle (DOCTYPE/Entitäten) sowie zip_lying_size: das ist Arbeit für pdfcheck/xmlcheck in 02-09.

## Deviations from Plan

- TDD: Erzeuger und Selbsttest entstanden zusammen; Test-Commit liegt vor dem Feat-Commit, ein separater roter Lauf wurde nicht festgehalten.
- [Rule 2] .gitignore und .dockerignore um tests/out/ ergänzt, damit Messdateien weder ins Repo noch ins Image kommen.
- Marker `container` und `linux` sind weiter nicht registriert (02-02); bis dahin PytestUnknownMarkWarning, der Hook wirkt trotzdem.

## Self-Check: PASSED
