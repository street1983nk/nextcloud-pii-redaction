---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 04
subsystem: intake
tags: [precheck, zip, cfb, limits, safe-02, job-05]
requires: []
provides: [intake.limits (alle Grenzen, MAX_PAGES=300), intake.verdict (VERDICTS, Rejected), intake.magic.detect, intake.zipcheck (check_zip, read_member_head, normalized_name)]
affects: [02-09, 02-13, 02-17, 02-19]
tech-stack:
  added: []
  patterns: [Findling-archive.py-Kopie mit Herkunftskommentar, Rejected(wort) als einziger Ablehnungsweg, Testdateien in tmp_path erzeugt]
key-files:
  created:
    - backend/src/pii_redaction_backend/intake/__init__.py
    - backend/src/pii_redaction_backend/intake/limits.py
    - backend/src/pii_redaction_backend/intake/verdict.py
    - backend/src/pii_redaction_backend/intake/magic.py
    - backend/src/pii_redaction_backend/intake/zipcheck.py
    - backend/tests/intake_builders.py
    - backend/tests/test_intake_limits.py
    - backend/tests/test_intake_magic.py
    - backend/tests/test_intake_zip.py
  modified:
    - backend/src/pii_redaction_backend/config.py
decisions:
  - "Raten wie Findling streng 'über': Rate genau 100 angenommen, über 100 too_large, genau 1000 too_large, über 1000 unsafe_content (Plan schrieb 'Rate 1000 -> unsafe'; Findling-Semantik beibehalten, Grenze/Grenze+1-Test passt dazu)"
  - "CFB-Verzeichnis wird über die FAT-Kette gelesen (nicht nur der erste Sektor), Deckel 4 MiB, Zyklus/Link aus der Datei = damaged; EncryptionInfo oder EncryptedPackage irgendwo im Verzeichnis = encrypted_document (fail-closed)"
  - "Verschlüsselte Office-Datei mit Anspruch pdf = wrong_type; mit docx/odt = encrypted_document"
  - "Verborgene Daten: erster Local Header muss an Offset 0 liegen, zipfile-concat muss 0 sein, Local-Header-Bereiche dürfen sich nicht überlappen und nicht ins Zentralverzeichnis reichen"
  - "ODF-Verschlüsselung per Bytesuche 'encryption-data' ohne Präfix im gestreamten Manifest (Präfix frei wählbar)"
metrics:
  completed: 2026-11-16
  tasks: "2/2"
---

# Phase 2 Plan 04: Vorprüfung Bytes und ZIP Summary

Zentrale Grenzwert-Tabelle (ein 300-Seiten-Deckel), geschlossene Verdict-Liste und eine fail-closed Vorprüfung: PDF-Kopf an Offset 0, CFB-Verzeichnis für passwortgeschützte Office-Dateien, ZIP-Zentralverzeichnis gezählt vor ZipFile, dann Bomben, Traversal, Doppelnamen (exakt, Groß/Klein, NFC, Segmente), Vorspann, verborgene Daten, Overlap, Verschlüsselung.

## Commits

| Schritt | Commit |
|---|---|
| RED limits/verdicts/Bytes | 4e11419 |
| RED zipcheck | cb3d76e |
| GREEN zipcheck, limits, verdict | aabcd62 |
| GREEN magic, config | 28d3312 |

## Prüfung

Suite 625 passed, 7 skipped; ruff, pyright, vulture grün. Positivkontrollen: saubere DOCX/ODT bestehen, je Grenze der Wert an der Grenze besteht; zipfile selbst sieht den Fall "verborgene Daten vor dem ersten Mitglied" nicht (im Test belegt), die Prüfung lehnt ihn ab.

## Deviations from Plan

- Reihenfolge der Commits: magic ruft check_zip von Anfang an (keine Übergangslösung in Task 1), daher kam zipcheck vor magic ins Repo; RED-Commits beider Tasks liegen vor den GREEN-Commits.
- Ratio-Semantik wie Findling (streng größer), siehe decisions.
- [Rule 2] Zusätzlich zu den Planfällen: Mitglied, das in das nächste hineinreicht, und Local Header, der nicht an der deklarierten Stelle steht (damaged).

## TDD Gate Compliance

test-Commits 4e11419 und cb3d76e vor feat-Commits aabcd62 und 28d3312.

## Self-Check: PASSED
