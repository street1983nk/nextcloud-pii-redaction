---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 05
subsystem: backend-workers
tags: [child-process, sandbox-early, pymupdf, libreoffice, placeholder, sqlite, dockerfile]
requires: [01-01]
provides:
  - "workers/child.py: run_child (SAFE_ENV + Allowlist, DEVNULL, start_new_session, killpg), python_child, ChildTimeout, ChildFailed, peak_child_rss_kb"
  - "workers/sniff.py: detect -> pdf | docx | odt | None per Magic-Bytes"
  - "workers/render.py: Kind-Einstieg Seite 1 als PNG plus meta.json {pages, width, height}"
  - "workers/soffice.py: command, convert (Profil /tmp/lo-<job_id> je Auftrag, im finally gelöscht)"
  - "workers/placeholder.py: einseitige Platzhalter-PDF DE/EN/FR ohne Quelldatei"
  - "store/schema.sql + repo.py: state.db (WAL), Tabellen meta und jobs ohne Text- oder Namensspalten"
  - "Dockerfile: libreoffice-writer-nogui und vier Schriftpakete"
affects: [01-06, 01-10, 01-15, 01-17]
tech-stack:
  added: ["libreoffice-writer-nogui, fonts-liberation2, fonts-dejavu-core, fonts-crosextra-carlito, fonts-crosextra-caladea (Debian, nur im Image)"]
  patterns:
    - "Kinder mit sys.executable -I -m pii_redaction_backend.workers.<name>, nur render und placeholder zugelassen"
    - "POSIX-Zweige hinter sys.platform-Prüfung, POSIX-Tests mit skipif win32 (laufen in python.yml)"
    - "Kind loggt nichts; Exit 0 oder 2, nur Dateien im Arbeitsordner kommen zurück"
key-files:
  created:
    - backend/src/pii_redaction_backend/workers/{__init__,child,sniff,render,soffice,placeholder}.py
    - backend/src/pii_redaction_backend/store/{__init__.py,schema.sql,repo.py}
    - backend/tests/{test_child,test_sniff,test_render,test_placeholder,test_store_schema}.py
  modified:
    - backend/Dockerfile
    - backend/tests/test_dockerfile.py
key-decisions:
  - "Die Auftragszeile der Platzhalter-PDF ist eine gemeinsame Zeile 'Auftrag n · Job n · Tâche n' (UI-SPEC: eine gemeinsame Zeile)"
  - "run_child tötet die Gruppe auch bei Abbruch (CancelledError), nicht nur bei Zeitüberschreitung"
  - "render nimmt dpi nur zwischen 36 und 300; job_id für soffice und placeholder nur ASCII-Ziffern"
  - "repo prüft task/stage gegen lokale Mengen; Plan 06 zieht auf model.py um"
requirements-completed: []  # JOB-02 und PLAT-03 erst mit Runner (Plan 10), Image-Build und CI-Lauf belegt
metrics:
  duration: "ca. 40 min"
  completed: 2026-11-07
  tasks: 3
  files: 18
---

# Phase 1 Plan 05: Kindprozesse, Rendering, LibreOffice und Platzhalter Summary

Alles, was fremde Dateien anfasst, läuft jetzt in Kindprozessen ohne Geheimnis. Jedes Kind hat eine eigene Prozessgruppe und eine Zeitgrenze, nach der die ganze Gruppe beendet wird. Seite 1 wird per PyMuPDF zum PNG gerendert, DOCX und ODT gehen vorher über LibreOffice, und die Platzhalter-PDF entsteht ganz ohne Quelldatei. Das Image bringt LibreOffice und die Schriften mit, `state.db` speichert keinen Text.

## Ergebnis

- **Task 1 (TDD, RED `7da5dd1`, GREEN `3420c93`):** `run_child` startet mit `SAFE_ENV` (PATH, HOME, LANG, OMP_THREAD_LIMIT) plus Allowlist (`TESSDATA_PREFIX`, `SAL_USE_VCLPLUGIN`). Ein fremder Schlüssel ergibt `ValueError`. Alle drei Standardkanäle gehen auf `DEVNULL`. Bei Zeitgrenze und Abbruch folgt `killpg(SIGKILL)`; ein Exit-Code ungleich 0 ergibt `ChildFailed(code)` ohne Ausgabe. `sniff` liest nur Kopfbytes, ZIP-Namen und höchstens 128 Byte `mimetype`. ODS, ZIP ohne Pflichtteile, kaputte ZIP und leere Datei ergeben `None`.
- **Task 2 (TDD, RED `cbea75f`, GREEN `16c44b4`):** `render.main` liefert für A4 bei 120 dpi eine Breite um 992 px; jeder Fehler ergibt Exit 2, ohne dass Dateien liegen bleiben. Der `soffice.command` entspricht genau dem Aufruf in CLAUDE.md. `convert` verlangt genau eine PDF und löscht das Profil im `finally`. Die Platzhalter-PDF ist einseitig, trägt die Texte aus UI-SPEC Fläche 4 (FR mit U+00A0) und hat als Metadaten nur den Titel "PII Redaction placeholder". Das Schema läuft in WAL und hat keine Text- oder Namensspalte. `schema.sql` steckt im Wheel (lokal mit `uv build` geprüft).
- **Task 3 (`ba05c2b`):** Die fünf Pakete stehen in einer `RUN`-Zeile mit `--no-install-recommends`, ungepinnt (trixie-security, `hadolint ignore=DL3008` mit Begründung). Es gibt kein Java und keinen Formeleditor, der Nutzer bleibt 10001. `test_dockerfile.py` prüft das mit Selbsttest.

Gates in `backend/` vor jedem Commit: ruff, ruff format --check, pyright (latest) 0 Fehler, vulture leer, pytest seriell. Endstand: 234 passed, 3 skipped (die drei POSIX-Tests in `test_child.py` laufen in `python.yml` auf Ubuntu). Neue Python-Pakete: keine (pymupdf 2.1 war schon da).

## TDD Gate Compliance

Bei beiden TDD-Tasks liegt der `test(...)`-Commit vor dem `feat(...)`-Commit, und die RED-Läufe scheiterten wie erwartet beim Import.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `resource` gibt es auf Windows nicht**
- **Fix:** Import in `peak_child_rss_kb` hinter `sys.platform != "win32"`. Damit bleiben Modulimport und pyright auf beiden Plattformen grün.
- **Commit:** 3420c93

**2. [Rule 3 - Blocking] ruff ASYNC110/ASYNC240**
- **Fix:** Das Warten auf den Enkel liegt in einem synchronen Test-Helfer. In `convert` laufen die Dateisystemschritte in kleinen synchronen Helfern (`_prepare`, `_single_pdf`).
- **Commits:** 3420c93, 16c44b4

**3. [Rule 2] Gruppen-Kill auch bei Abbruch**
- **Issue:** Wird der Runner abgebrochen (Shutdown), liefe das Kind sonst weiter.
- **Fix:** `except asyncio.CancelledError`: Gruppe beenden, warten, weiterreichen.
- **Commit:** 3420c93

**4. [Rule 1] Dockerfile-Kommentar nannte die verbotenen Paketnamen**
- **Issue:** Die Akzeptanz verlangt 0 Treffer für `default-jre|libreoffice-math`, der erste Kommentar nannte beide.
- **Fix:** Umformuliert ("no Java runtime ... no formula editor").
- **Commit:** ba05c2b

## Hinweise

- Lokal liegt eine von Git ignorierte Datei `backend/src/pii_redaction_backend/workers/.claude-active`. Sie stammt nicht aus diesem Plan, kommt aber bei einem lokalen `uv build` mit ins Wheel. CI und Image sind nicht betroffen, weil die Datei nicht eingecheckt ist.
- Die Image-Größe mit LibreOffice misst Plan 17 in `docker.yml`.

## Known Stubs

- `repo.TASKS`/`STAGES` sind lokale Mengen, bis Plan 06 `model.py` liefert (so geplant).

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-05-05 (LibreOffice-Makros/Netz) bleibt wie geplant `accept` bis Phase 2.

## Self-Check: PASSED

- Dateien vorhanden: workers/child.py, sniff.py, render.py, soffice.py, placeholder.py, store/schema.sql, store/repo.py, fünf Testdateien, Dockerfile mit libreoffice-writer-nogui
- Commits vorhanden: 7da5dd1, 3420c93, cbea75f, 16c44b4, ba05c2b
