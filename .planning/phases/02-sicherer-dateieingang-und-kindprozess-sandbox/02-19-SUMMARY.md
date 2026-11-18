---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 19
subsystem: runner
tags: [safe-01, safe-02, safe-03, job-05, tdd, runner, claim, ack]
requires: [02-14, 02-15, 02-17]
provides: [nc.Claim expected/confirmed, nc.ReviewFlags, ack confirm, Runner precheck/sanitize/confirm/page cap, runner._read_verdict/_read_sanitize/_child_failure_reason, Runner(mark_jail_failed=...)]
affects: [02-20, 02-21, 02-22, 02-24]
tech-stack:
  added: []
  patterns: [Kind-Antwort mit genau den geschlossenen Schlüsseln, sonst damaged; Fehlerwort je Kindart aus einer Funktion]
key-files:
  created: []
  modified:
    - backend/src/pii_redaction_backend/nc.py
    - backend/src/pii_redaction_backend/runner/runner.py
    - backend/tests/test_nc.py
    - backend/tests/test_runner.py
  deleted:
    - backend/src/pii_redaction_backend/workers/sniff.py
    - backend/tests/test_sniff.py
decisions:
  - "expected null im analyze-Claim bleibt ein Claim; der Runner beendet den Auftrag ohne Download mit unsupported_format (Vertrag 02-15). Fehlt der Schlüssel ganz oder ist das Wort fremd, wird der Claim verworfen"
  - "Andere Abstürze von precheck/sanitize (nicht Zeitlimit, SIGXCPU, SIGXFSZ, Exit 71) ergeben damaged, nicht render_failed"
  - "Exit 71 markiert den Jail auch beim Platzhalter (apply) und bei soffice, nicht nur bei precheck/sanitize/render"
  - "sanitize läuft noch in der Stufe checking; converting beginnt erst mit LibreOffice"
  - "Die bereinigte Kopie heißt src-clean.<fmt>, damit _remove_sources sie mit dem Muster src* löscht"
  - "Die Zeitdeckel des Runners sind entfernt; jedes Kind läuft mit der Wanduhr seines Jail-Profils"
metrics:
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 19: Runner mit Vorprüfung, Bestätigung, Bereiniger und Seitendeckel Summary

Jede Analyse läuft jetzt so: fetch, dann Stufe `checking` mit dem Kind `precheck` im eigenen Jail-Profil. Dessen Antwort prüft der Server erneut gegen die geschlossene Liste. Eine Ablehnung endet mit ihrem Wort. Eine signierte PDF ohne Bestätigung endet mit `ack confirm`. DOCX und ODT gehen erst durch `sanitize`, LibreOffice bekommt nur die bereinigte Kopie. Nach dem Rendern gilt der Deckel von 300 Seiten. `ack review` trägt `macrosRemoved`, `externalLinksRemoved` und `ownerProtectionDropped`. Im Server-Prozess wird keine Nutzerdatei mehr geparst, `sniff.py` ist entfernt.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Task 1 RED | 30801ca | test(02-19): claim takes expected and confirmed strictly, ack confirm and review flags |
| Task 1 GREEN | 63dde68 | feat(02-19): nc.py speaks the extended claim and ack contract strictly |
| Task 2 RED | 2370189 | test(02-19): the runner checks, asks, cleans and caps before it renders |
| Task 2 GREEN | 36067d9 | feat(02-19): every analysis runs through precheck, confirmation, cleaner and page cap |

## Prüfung

- Lokale Gates grün: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture.
- Ganze Suite lokal: `1434 passed, 44 skipped`. Vorher waren es 1330 passed, 44 skipped. test_sniff.py ist entfallen.
- RED belegt: test_nc 64 rot (Claim ohne Felder, kein ack confirm), test_runner 97 rot (Runner ohne `mark_jail_failed`, sniff.py vorhanden).
- Akzeptanz: `_typed_source` 0, `AckResult.CONFIRM` 1, `limits.MAX_PAGES` 4, `mark_jail_failed` 3, `python_child("precheck"` 1 in runner.py, sniff.py fehlt, `confirmed` 9 in nc.py.
- Frontend nicht betroffen. PHP nicht geändert.

## Was die Tests belegen

- Claim: Ein Claim ohne `expected`, mit `doc`, `PDF`, leer, als Zahl oder Liste wird verworfen. Das gilt auch für `confirmed` als `"true"`, `1` oder `null`. Ein fehlendes `confirmed` gilt als false. apply und purge übernehmen keines der beiden Felder.
- Ack: `confirm` sendet nur Token und Wort. Die Flags gehen nur mit ihren Typen raus (bool, int 0 bis 10000, kein bool als int). Bei einem anderen Ergebnis als review gibt es einen ValueError vor dem Senden.
- Runner: Jedes der acht Ablehnungswörter endet mit genau diesem Grund, ohne render und ohne soffice. 26 kaputte Antwortformen ergeben damaged, darunter fremdes Wort, pages 0/301/bool/String, signed `"yes"`, fremdes Format, Zusatzschlüssel, kein JSON und fehlende Datei. Für sanitize gibt es 8 Formen, dazu ok ohne bereinigte Kopie.
- Signatur: unbestätigt ergibt `ack confirm` mit Stufen `fetching, checking`, Quelle gelöscht. Bestätigt läuft der normale Weg.
- DOCX und ODT: Der Fake prüft, dass `convert` genau den Pfad der bereinigten Kopie bekommt, nie die Quelle.
- Seitendeckel: 301 ergibt too_many_pages, 300 geht zu review, jeweils für PDF und DOCX.
- Fehlerabbildung: Zeitlimit, -24 und -25 in precheck/sanitize ergeben too_large. Exit 71 ergibt render_failed und genau einen Aufruf von `mark_jail_failed`, für precheck, sanitize, render, soffice und Platzhalter. Bei allen anderen Fehlern wird es nie gerufen.
- AST-Test: runner.py importiert weder zipfile, pymupdf, pikepdf, lxml, pypdf noch eines der Prüfmodule. Positivkontrolle: Der Scanner sieht `workers.child` und `intake.limits`.

## Deviations from Plan

**1. [Rule 1 - Vertragskonflikt] `expected: null` wird nicht verworfen.**
- Plan Task 1: "analyze-Claim ohne expected ... verworfen".
- Problem: Laut 02-15 sendet PHP `null`, wenn die Datei weg ist oder einen anderen MIME-Typ hat, und der Container soll dann `unsupported_format` melden. Würde der Claim verworfen, bliebe der Auftrag bis zum Lease-Ende hängen und würde danach wieder ausgegeben.
- Lösung: Fehlt der Schlüssel oder ist das Wort fremd, wird der Claim verworfen. `null` dagegen führt ohne Download zu `failed unsupported_format`.

**2. Fehlerwort für andere Abstürze von precheck und sanitize.** Der Plan nennt nur too_large und render_failed. Ein Absturz der Parser durch eine Datei, etwa SIGSEGV oder Exit 2, ergibt hier damaged. Das passt zu `judge()` in precheck.py: Eine unerwartete Ausnahme ist dort ebenfalls damaged.

**3. Exit 71 auch bei Platzhalter und soffice.** Der Plan nennt den Fall allgemein. Umgesetzt ist er an jeder Stelle, an der ein Kind läuft.

**4. Zusatzprüfungen in `_read_verdict`.** Bei ok muss das Format dem erwarteten entsprechen. Eine Ablehnung darf weder Format, Seiten noch Flags tragen. DOCX und ODT dürfen weder signiert noch besitzergeschützt sein. Sonst ergibt sich damaged (T-02-15).

**5. Die Konstante `PLACEHOLDER_TIMEOUT_SECONDS` ist ebenfalls entfernt.** Der Wert war 60 s wie das Profil `render`.

## Offen (nur mit CI oder Docker belegbar, nicht geraten)

- `test_analyze_through_the_real_render_child` läuft nur unter Linux (python.yml). Jetzt geht er zusätzlich durch das echte precheck-Kind im Jail-Profil `precheck`. Ob die Testinterpreter-Lesepfade dafür reichen, zeigt erst CI nach einer Push-Freigabe. Ein Exit 71 dort wäre die erwartete fail-closed-Antwort, aber ein roter Test.
- precheck und sanitize im echten Jail über den ganzen Korpus: Plan 02-21. Wirkung der LibreOffice-Härtung auf der bereinigten Kopie: Plan 02-22.
- Ende-zu-Ende mit PHP: `ack confirm`, die Ablehnungswörter und die Flags gegen den echten QueueController. PHPUnit läuft nur in php.yml, PHP ist lokal nicht installiert.
- UI-Sichtprüfung der confirm-Karte mit echtem Container: gemeinsam mit dem Owner per Playwright.
- Requirements SAFE-01, SAFE-02, SAFE-03 und JOB-05 sind nicht als erledigt markiert. Es fehlen die Container- und CI-Belege (02-21, 02-22, 02-24), bei SAFE-03 auch der Netzaufruf-Test mit dem externen Bild.

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche. T-02-15: `_read_verdict` und `_read_sanitize` prüfen genaue Schlüsselmenge, Wortliste, Bereiche und strenge bools. T-02-49: sniff ist entfernt, der AST-Test ist grün. T-02-13: Test auf den Pfad der bereinigten Kopie. T-02-19: confirm vor jeder Analyse. T-02-27: ownerProtectionDropped. T-02-20: Die neuen Logzeilen "check step failed", "check answer refused" und "signature needs confirmation" sind Literale mit job_id, child, exc_type, exit_code, signal und reason. Das Log-Gate ist grün.

## Self-Check: PASSED
