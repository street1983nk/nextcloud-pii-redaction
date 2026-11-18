---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 17
subsystem: workers
tags: [safe-01, safe-02, safe-03, job-05, libreoffice, tdd]
requires: [02-08, 02-09, 02-13, 02-16]
provides: [workers.precheck main/judge/write_answer, workers.sanitize main/clean, lo_profile/registrymodifications.xcu, soffice.harden_profile, ProfileTemplateMissing reasons malformed/conflict]
affects: [02-19, 02-21, 02-22]
key-files:
  created:
    - backend/src/pii_redaction_backend/workers/precheck.py
    - backend/src/pii_redaction_backend/workers/sanitize.py
    - backend/src/pii_redaction_backend/workers/lo_profile/registrymodifications.xcu
    - backend/tests/test_precheck_worker.py
    - backend/tests/test_sanitize_worker.py
  modified:
    - backend/src/pii_redaction_backend/workers/soffice.py
    - backend/src/pii_redaction_backend/runner/runner.py
    - backend/tests/test_soffice_profile.py
    - backend/tests/test_render.py
decisions:
  - "precheck-Antwort hat immer genau fünf Schlüssel; bei Ablehnung format null, pages null, signed und ownerProtected false"
  - "Unerwartete Ausnahme eines Parsers ist damaged, MemoryError too_large; Exit 2 nur bei falschen Argumenten oder nicht schreibbarer Antwort"
  - "Die Härtung ersetzt registrymodifications.xcu der Vorlagenkopie nicht, sondern fügt ihre Einträge vor dem Schlusstag ein (ooSetupInstCompleted der Vorlage bleibt, sonst Neustartgefahr aus 02-16 R1)"
  - "Setzt die Vorlage schon einen Härtungsschlüssel (conflict) oder ist sie keine Registry (malformed), endet der Auftrag vor dem Start von soffice"
  - "Vorlagendatei wird mit dem einzigen XML-Parser des Pakets (intake.xmlcheck, lxml) gelesen; der Test liest die Paketdatei unabhängig mit xml.etree"
metrics:
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 17: Kinder precheck/sanitize und gehärtetes LibreOffice-Profil Summary

`precheck` und `sanitize` laufen als eigene Kind-Einstiege mit geschlossenen Antworten über `.tmp` + `os.replace`. Jeder LibreOffice-Auftrag bekommt die zwölf Härtungsschlüssel aus RESEARCH Pattern 5 in seine frische Vorlagenkopie, bevor soffice startet. Danach wird das Profil gelöscht.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Task 1 RED | df591a5 | test(02-17): precheck and sanitize children answer in closed words only |
| Task 1 GREEN | a9d3f33 | feat(02-17): precheck and sanitize as child entry points with a closed answer |
| Task 2 RED | c11aa8b | test(02-17): a hardened LibreOffice profile per job, merged into the template copy |
| Task 2 GREEN | 2fd526b | feat(02-17): every LibreOffice job profile gets the hardening keys of Pattern 5 |

## Prüfung

- Lokale Gates grün: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture.
- Suite lokal: `1330 passed, 44 skipped`. Vorher waren es 1298 passed in CI bzw. 1312 lokal nach Task 1.
- RED belegt: Task 1 als Sammelfehler ohne Module. Task 2 mit 16 roten Tests, darunter das Wheel ohne xcu (KeyError) und eine ungültige job_id, die den Ausgabeordner schon angelegt hatte.
- Korpus: Jede Datei außer `unit_only` liefert über `precheck.main` ein Wort ihrer Manifest-Menge, mindestens 30 Dateien geprüft. `confirm` heißt `ok` mit `signed true`. `ownerProtected` ist nur bei `pdf_owner_only.pdf` gesetzt. stdout und stderr bleiben leer, auch im Fehlerfall.
- `grep -c "print("` in precheck.py und sanitize.py: je 0.
- `grep -c` der sieben Sicherheitsnamen in der xcu-Datei: 7.
- `uv build --wheel` enthält `pii_redaction_backend/workers/lo_profile/registrymodifications.xcu` bytegleich. uv_build nimmt die Datei ohne Include-Regel auf, pyproject.toml bleibt unverändert. Das Image installiert mit `uv sync --no-editable`, bekommt die Datei also über das Wheel.

## Deviations from Plan

**1. [Rule 1 - Bug, Konflikt mit Owner-Entscheid 02-16] Zusammenführen statt Überschreiben.**
- Plan: `registrymodifications.xcu` nach `<profil>/user/` kopieren, Test "Bytes gleich".
- Problem: Seit 02-16 kommt das Profil aus der Image-Vorlage. Deren `registrymodifications.xcu` trägt `ooSetupInstCompleted` (Sandbox-Lauf zu c1b6f5f: `TEMPLATE-RESTART setup_completed=ja`). Überschreiben würde den Eintrag löschen, LibreOffice hielte das Profil für neu (`userinstall::create`), und der Neustart im Jail wäre wieder möglich.
- Lösung: `harden_profile` setzt die Einträge der Paketdatei bytegleich vor `</oor:items>` der Kopie. Der Test prüft jede Zeile der Paketdatei in der Kopie, jeden Schlüssel genau einmal und den Setup-Eintrag der Vorlage.

**2. [Rule 2 - fail-closed] Zwei neue Gründe für `ProfileTemplateMissing`.**
- `conflict`: Die Vorlage setzt schon einen Härtungsschlüssel. Welcher von zwei Werten gilt, bleibt nicht dem Zufall überlassen.
- `malformed`: kein XML, DOCTYPE, fremde Wurzel oder kein `oor`-Namensraum.
- Der Runner-Kommentar zur Log-Liste ist nachgezogen. Das Log nennt weiter nur das Wort.

**3. [Rule 1] Ungültige job_id vor jedem Dateizugriff.** `convert` legte den Ausgabeordner an, bevor `_checked` lief. Jetzt kommt `_checked(job_id)` zuerst.

**4. [Rule 3] test_render.py angepasst (Datei aus 02-08/02-16).** Die Testvorlage `<oor:items/>` ist keine Registry mehr, die die Härtung annimmt. Sie trägt jetzt den Setup-Eintrag. Geprüft wird Setup-Eintrag plus `DisableMacrosExecution`.

**5. Korpus ohne `unit_only`.** `zip_entries_10000.docx` gilt nur für Stufe B, weil seine Teile leer sind; das ist dieselbe Ausnahme wie in test_ci_corpus.py.

## Offen (nur mit Docker/CI belegbar, nicht geraten)

- Die echte Image-Vorlage nimmt die Härtung ohne `conflict` und `malformed` an, und soffice wandelt danach ohne Neustart. Das zeigt erst der nächste Sandbox-Lauf: `SOFFICE-LAYER product exit=0 pdf=ja`, `SOFFICE-STARTS product n=1` auf amd64 und arm64. Für diesen Lauf braucht es eine Push-Freigabe.
- A3: LibreOffice 25.2 liest die Schlüssel tatsächlich aus dem vorbereiteten Profil (Wirkung, nicht nur Vorhandensein). Das belegt der Schichtlauf b in Plan 02-22.
- A9: Ob die Debian-nogui-Variante den UpdateCheck-Dienst überhaupt baut, ist offen. Der Schlüssel ist trotzdem gesetzt.
- Die Kinder precheck und sanitize im echten Jail über den ganzen Korpus folgen in 02-21. Im Container liefen die Intake-Funktionen schon unter dem Produktprofil (`PROFILE-WORK precheck/sanitize product_ok=ja`). Die neuen Module selbst sind dort noch ungeprüft.

## Threat Flags

Keine neue Angriffsfläche. T-02-14, T-02-13 und T-02-28 sind über das Profil adressiert, T-02-15 und T-02-20 über die geschlossenen Antworten ohne Ausgabe. Die Prüfung der Antworten im Server folgt in 02-19.

## Self-Check: PASSED
