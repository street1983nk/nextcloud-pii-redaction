---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 02
subsystem: database
tags: [migration, enums, queue, lease, php]
requires: [01-01]
provides:
  - "Migration Version000100Date20261107000000: pii_jobs, pii_job_events, pii_slot ohne Klartextspalten"
  - "Sieben Enums in OCA\\PiiRedaction\\Model (Status mit isTerminal/isOpen/openValues, Lang::fromLanguageCode)"
  - "Job/JobEvent mit get*Enum-Helfern, die bei fremden Werten werfen"
  - "JobMapper: find, enqueue, findOpenFor, findOpenByFile, ensureSlot, claimNext, extendLease, release, ahead"
  - "JobEventMapper::record mit Allowlist, findForJob"
  - "backend/tests/test_php_schema.py (lokales Gate für Enums und Migration, mit Selbsttest)"
affects: [01-03, 01-08, 01-12, 01-13, 01-14, 01-15, 01-17]
tech-stack:
  added: []
  patterns:
    - "Sperrzeile pii_slot: eine bedingte UPDATE mit lease_until <= now, Token-Rücklesen, kein Zeilen-Lock, keine Selbstbezug-Unterabfrage"
    - "Gleiches Token für Jobzeile und Sperrzeile; release und extendLease nur mit diesem Token"
    - "Einzige Uhr ITimeFactory::getTime()"
key-files:
  created:
    - php/lib/Model/{Status,Reason,Stage,Task,Mode,Subject,Lang}.php
    - php/lib/Migration/Version000100Date20261107000000.php
    - php/lib/Db/{Job,JobEvent,JobMapper,JobEventMapper}.php
    - php/tests/Unit/ModelTest.php
    - php/tests/Unit/QueueMapperTest.php
    - backend/tests/test_php_schema.py
  modified:
    - .github/workflows/php.yml
key-decisions:
  - "QueueMapperTest läuft gegen die echte SQLite-DB der CI-Instanz; php.yml aktiviert dafür die App vor der Suite (Migration läuft dabei mit)"
  - "Purge-Ausgaben zählen keine Versuche und belegen die Sperrzeile nicht"
  - "giveUp (repeatedly_stuck) sitzt im Mapper und schickt keine Benachrichtigung; JobService/QueueController (Plan 08/12) müssen das beim Lesen nachziehen"
requirements-completed: []  # JOB-04/JOB-06 nur Datenbasis; Durchsetzung über Controller folgt in Plan 08/12
metrics:
  duration: "ca. 35 min"
  completed: 2026-11-07
  tasks: 2
  files: 16
---

# Phase 1 Plan 02: Datenmodell und Warteschlange Summary

Die PHP-App hat jetzt ihr Datenmodell: eine Migration mit drei Tabellen, die keine Spalte für Namen, Pfade, Mime oder Text haben, sieben geschlossene Listen als Enums und einen `JobMapper`, der "ein Auftrag zur Zeit" mit einer einzigen bedingten UPDATE auf die Sperrzeile `pii_slot` durchsetzt.

## Ergebnis

- **Task 1 (`f2f1783`):** Die Enums tragen genau die Werte aus 01-SKELETON.md (Status 12, Reason 15). Die Migration hat `hasTable`-Schutz, Primärschlüssel mit Namen und die drei Indizes aus dem SKELETON. `ModelTest` prüft die Listen, `tryFrom('unknown')`, die Sprachableitung und die Spaltenlängen. Zusätzlich gibt es `test_php_schema.py`, das lokal ohne PHP die Enum-Werte, die genauen Spalten je Tabelle, verbotene Namensteile, fehlende BOOLEAN-Spalten und die Längen prüft. Ein Selbsttest mit mutierten Beispielen gehört dazu.
- **Task 2 (`d95a6d3`):** `claimNext` vergibt zuerst purge (ohne Sperrzeile). Danach nimmt es die Sperrzeile und sucht Kandidaten: apply/approved, dann analyze/queued, dann abgelaufene analyzing/applying, jeweils nach id. Ab `attempts >= 3` wird ein Kandidat `failed(repeatedly_stuck)` mit `task = purge`. `ahead` zählt wartende analyze-Aufträge mit kleinerer id und addiert 1, wenn ein anderer Auftrag einen gültigen Lease hat. `QueueMapperTest` hat 14 Tests.

Gates in `backend/`: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture leer, pytest 140 passed (seriell). Die Akzeptanz-greps der beiden Tasks treffen. PHP wurde nur statisch geprüft; phpunit läuft in CI (Plan 07).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Tabellen fehlen in der phpunit-Instanz**
- **Found during:** Task 2
- **Issue:** Der Plan verlangt einen Mapper-Test gegen die echte Testdatenbank "wie FIN-Mapper-Tests". FIN hat aber keinen solchen Test, und `php.yml` installiert nur einen leeren Server. Die `pii_*`-Tabellen gäbe es dort nicht.
- **Fix:** Neuer Schritt in `php.yml`: `./occ app:enable pii_redaction` mit Prüfung per `app:list`. Das führt nebenbei die Migration auf SQLite aus. Fehlt eine Tabelle, schlägt `setUp` mit einer klaren Meldung fehl (kein Skip).
- **Commit:** d95a6d3

**2. [Rule 2 - Missing] Lokales Gate für Migration und Enums**
- **Issue:** PHP läuft lokal nicht, und die Regel "keine Klartextspalten" (T-01-02-01, high) wäre erst nach einem Push geprüft worden.
- **Fix:** `backend/tests/test_php_schema.py` mit Selbsttest. Plan 03 bringt das allgemeine Spalten-Gate in `test_php_gates.py`; beide dürfen nebeneinander bestehen.
- **Commit:** f2f1783

**3. [Rule 2] ensureSlot schaut vor dem Insert nach**
- **Issue:** Ein fehlgeschlagenes INSERT bricht auf PostgreSQL eine laufende Transaktion des Aufrufers ab.
- **Fix:** Zuerst wird gezählt, nur bei fehlender Zeile folgt der Insert. Die eindeutige Verletzung wird weiter geschluckt (Wettlauf).
- **Commit:** d95a6d3

Kleinere Ergänzungen über den Plan hinaus: `JobMapper::find(int)`, `Job::getTaskEnum/getStageEnum/getModeEnum/getLangEnum`, `Status::openValues()`, `JobEventMapper::findForJob`, `MAX_CANDIDATES = 50` als Schleifendeckel.

## Hinweise für spätere Pläne

- **Plan 12 (ack):** `attempts` beim erfolgreichen ack auf 0 setzen. Sonst zählt ein späterer apply-Lauf die analyze-Versuche mit.
- **Plan 08/12:** `giveUp` setzt `failed(repeatedly_stuck)` direkt im Mapper. Die Benachrichtigung `job_failed` muss der Dienst nachziehen, der den Zustand zuerst liest (etwa beim nächsten claim oder beim Status-GET).
- **Purge:** Wird ein purge nie bestätigt, gibt der Mapper ihn alle 60 s erneut aus, ohne Deckel. Das ist harmlos (kein Rendering), wird aber in Phase 8 gemessen.

## Known Stubs

- `expires_at` wird auf 0 gesetzt; TTL-Durchsetzung ist außerhalb von Phase 1 (SKELETON "Out of Scope").

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-02-01 bis -05 sind wie geplant mitigiert.

## Self-Check: PASSED

- Dateien vorhanden: php/lib/Migration/Version000100Date20261107000000.php, php/lib/Db/JobMapper.php, php/lib/Model/Status.php, php/tests/Unit/QueueMapperTest.php, php/tests/Unit/ModelTest.php, backend/tests/test_php_schema.py
- Commits vorhanden: f2f1783, d95a6d3
