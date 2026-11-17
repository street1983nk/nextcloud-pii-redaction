---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 09
subsystem: intake
tags: [xml, pdf, safe-02, job-05, tdd]
requires: [02-02, 02-04, 02-07]
provides: [intake.xmlcheck make_parser/parse_part/check_parts, intake.pdfcheck check_pdf/PdfReport]
affects: [02-13, 02-17]
key-files:
  created:
    - backend/src/pii_redaction_backend/intake/xmlcheck.py
    - backend/src/pii_redaction_backend/intake/pdfcheck.py
    - backend/tests/test_intake_xml.py
    - backend/tests/test_intake_pdf.py
decisions:
  - "Ein XML-Syntaxfehler gilt als unsafe_content, wenn das Teil eine DOCTYPE- oder ENTITY-Deklaration trägt (BOM-bewusst dekodiert); libxml2 bricht Billion Laughs selbst mit 'entity amplification' ab"
  - "Nicht-Bild-Flate-Ströme werden blockweise gezählt (Ausgabe verworfen) und nach der ZIP-Ratenregel (ZIP_MAX_RATIO ab ZIP_RATIO_MIN_BYTES) bewertet; /DL über derselben Grenze ist too_large; Bilder nur über /Width x /Height"
  - "zlib-Fehler in einem Strom führen nicht zur Ablehnung (MuPDF liest über kaputte Ströme hinweg); alles andere Unerwartete ist damaged"
  - "Objektzahl zuerst aus Trailer /Size, dann aus der echten Objektliste"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 09: XML- und PDF-Vorprüfung Summary

Ein einziger lxml-Parser (sechs feste Optionen, DOCTYPE/Entitäten abgelehnt, Teile gestreamt gezählt) und eine pikepdf-Prüfung mit allen Deckeln aus limits.py, Passwort-/Besitzerpasswort-Unterscheidung und Signaturerkennung; alle PDF-, XML- und zip_lying_size-Fälle des Korpus liefern ein Wort ihrer Manifest-Menge.

## Commits

| Schritt | Commit |
|---|---|
| Task 1 RED (XML) | 7ec2429 |
| Task 1 GREEN (xmlcheck.py) | d198a25 |
| Task 2 RED (PDF) | 5f947f2 |
| Task 2 GREEN (pdfcheck.py) | 24d9b5a |

## Prüfung

- Suite 864 passed, 14 skipped; ruff, Format, pyright (latest) 0, vulture grün.
- XXE-Datei: Kanarienwert erscheint nie; Positivkontrolle mit auflösendem Parser zeigt ihn. Netz: lokaler Lausch-Socket sieht keine Verbindung, Kontrollverbindung wird gesehen; Audit-Hook-Zähler 0.
- Korpus: pdf_flate_bomb too_large, pdf_page_loop damaged, pdf_objects_500001 too_large, genau 500 000 ok, pdf_owner_only ok + owner_protected, pdf_signed signed, zip_lying_size im Manifest-Satz (CRC-Bruch -> damaged).
- deferred-items 02-09 (PDF-Strukturfälle, DOCTYPE/Entitäten, zip_lying_size) damit erledigt; pdf_prefix bleibt Sache der Stufe A (magic.py), pikepdf öffnet es.

## Deviations from Plan

**1. [Rule 2 - Sicherheit] Begrenztes Zählen von Flate-Strömen statt reiner /Length-/DL-Prüfung.** Der Plan sagt "nicht dekodieren", verlangt aber pdf_flate_bomb als too_large/damaged; ohne Zählen wäre der Fall ok gewesen. Gelöst mit blockweisem Inflate ohne Speichern, Abbruch kurz nach der erlaubten Menge; Bilder werden weiterhin nie dekodiert.

**2. [Rule 1] Billion Laughs ergab zuerst damaged statt unsafe_content** (libxml2 bricht vor dem DOCTYPE-Test ab). Behoben über Deklarationsprüfung des Teils bei Syntaxfehler.

**3. [Rule 3] lxml ohne Typ-Stubs:** `from lxml import etree` mit `pyright: ignore[reportAttributeAccessIssue]` (kein neues Paket, lxml-stubs nicht gepinnt).

**4. pikepdf-API (A4):** wie angenommen; `PasswordError` beim Nutzerpasswort, `is_encrypted` True beim Besitzerpasswort, `Page.mediabox` mit Vererbung, Seitenschleife wirft schon beim Öffnen `PdfError`. Context7 nicht genutzt, direkt am installierten 10.17.0 geprüft.

## Threat Flags

Keine.

## Self-Check: PASSED
