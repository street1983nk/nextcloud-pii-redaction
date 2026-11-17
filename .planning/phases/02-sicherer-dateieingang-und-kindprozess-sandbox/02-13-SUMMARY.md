---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 13
subsystem: intake
tags: [sanitizer, safe-03, docx, odt, tdd]
requires: [02-04, 02-07, 02-09]
provides: [intake.sanitize sanitize/SanitizeReport]
affects: [02-17, 02-21, 02-22]
key-files:
  created:
    - backend/src/pii_redaction_backend/intake/sanitize.py
    - backend/tests/test_sanitize.py
  modified:
    - ci/make_corpus.py
    - backend/tests/test_ci_corpus.py
decisions:
  - "Komplexe Felder (fldChar begin/separate/end): bei ladendem Feldbefehl werden alle Elemente des Code-Bereichs samt fldChar entfernt, die Läufe des Ergebnisses bleiben; einfache Felder werden durch ihre Kinder ersetzt"
  - "Externe Hyperlinks behalten ihre Id mit leerem Ziel und ohne TargetMode; jede andere externe Beziehung geht"
  - "ODT: Quellen-Elemente (section-source, table-source, DDE) gehen ganz, bei Bildern/Objekten nur das externe xlink:href"
  - "Unveränderte XML-Teile werden bytegleich übernommen; geänderte mit lxml neu geschrieben"
  - "Externes Ziel per Schema-Regex statt urllib (Boundary-Gate verbietet urllib außerhalb der Grenze)"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 13: Bereiniger vor LibreOffice Summary

`sanitize(src, dst, fmt)` schreibt eine DOCX/ODT-Kopie ohne externe Beziehungen, Makro-/ActiveX-/OLE-Teile, ladende Felder, altChunk, Vorlagen-Injektion, Frameset, ODF-Skripte, Ereignisse und externe Quellen; die Kopie wird erneut durch zipcheck und xmlcheck geschickt und der Bericht trägt nur `macros_removed` und `external_links_removed`.

## Commits

| Schritt | Commit |
|---|---|
| Korpus-Fix INCLUDEPICTURE + Wohlgeformtheits-Selbsttest | 7b315ca |
| Tests (RED, Sammelfehler belegt) | bd4b9e0 |
| sanitize.py | fa774b0 |

## Prüfung

- Suite 994 passed, 14 skipped; ruff, Format, pyright (latest) 0, vulture, Boundary-Gate grün.
- Prüfungen der Ausgabe nur mit zipfile, Bytesuche und xml.etree; AST-Test hält den Import auf `sanitize`/`SanitizeReport`. Positivkontrollen: Kanarien-Adresse und macroEnabled stehen in den Quellen, harmloses PAGE-Feld und internes ODT-Bild bleiben, harmlose Dateien kommen kanonisch gleich heraus, Wachstumsdeckel greift erst bei abgesenktem Wert.

## Deviations from Plan

**1. [Rule 1 - Bug im Korpus 02-07] ext_includepicture.docx war kein wohlgeformtes XML** (Feldbefehl mit nackten Anführungszeichen im Attribut). Die Vorprüfung hätte die Datei als damaged abgewiesen, der Bereiniger-Fall wäre nie gelaufen. Behoben mit `&quot;`; neuer Korpus-Selbsttest prüft jedes erwartete ok-Paket mit der Standardbibliothek auf Wohlgeformtheit (unit_only ausgenommen: zip_entries_10000 hat leere Teile und gilt nur für Stufe B).

**2. [Rule 3] urllib aus dem Bereiniger entfernt** (test_boundary verbietet urllib-Importe ausserhalb der Grenze); Schema-Erkennung per Regex.

**3. Wachstumstest** über das Absenken von `GROWTH_PERCENT` (per Pfad-String gepatcht), weil sich ein natürlich wachsendes Paket nicht verlässlich bauen lässt; Positivkontrolle mit Standardwert davor.

## Threat Flags

Keine.

## Self-Check: PASSED
