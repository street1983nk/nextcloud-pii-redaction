# Project Research Summary

**Project:** PII Redaction (PHP-App `pii_redaction` + ExApp `pii_redaction_backend`)
**Domain:** Lokale Erkennung, menschliche Prüfung, echte Schwärzung und Pseudonymisierung personenbezogener Daten in PDF (Text und Scan), DOCX und ODT als Nextcloud-App für Behörden, Gerichte, Kommunen und Selfhoster
**Researched:** 07.11.2026
**Confidence:** MEDIUM (Stack und Nextcloud-Grenzen HIGH, Schwärzungsmechanik für Text-PDF/DOCX/ODT HIGH aus dem Spike; Scans, PDF-Strukturlecks, LibreOffice-Härtung, DOCX-Anzeigeabbildung und Länder-Rechtsgrundlagen MEDIUM bis LOW)

## Executive Summary

Das Produkt ist ein Schwärzungswerkzeug mit Mensch im Ablauf: Erkennen, Vorschlagen, Prüfen, Freigeben, dann echt Entfernen und unabhängig Nachprüfen. Maßstab im Markt sind Acrobat (Sanitize), Objective Redact (Arbeitskopie, Freigabe, Codes je Rechtsordnung), Redactable (Grund je Schwärzung, Zertifikat) und JANO (Entitätenliste mit Zähler, rollenbasierte Pseudonyme). Keiner dieser Anbieter dokumentiert eine unabhängige, blockierende Leck-Nachprüfung, deutsche Rechtsgrundlagen-Sätze oder offene Qualitätszahlen; Conduction (Filinq/Anonymiq) als einziger Nextcloud-Mitbewerber fällt bei komplexen PDFs auf Klartext-Export zurück und ersetzt nur mit `[PERSON]`. Genau dort liegt die Differenzierung: lokal, layouttreu, nachweislich leer, deutsch.

Die Empfehlung ist klar: Die PHP-App ist die Sicherheits- und Workflow-Grenze (Dateiaktion, Prüfseite, Rechte bei jeder Anfrage, Vier-Augen, Ablage per `newFile()` als Nutzer, Protokoll), der Container ist ein Rechenknecht ohne eigene Browser-Routen. Erkennung mit dem gemessenen Spike-Stapel (Presidio 2.2.366 + eigene DE-Erkenner + spaCy `de_core_news_lg` + GLiNER2-PII, Personen-Recall 0,996, Leckrate 1,1 %), Schwärzung PDF mit PyMuPDF 2.1 `apply_redactions` + `scrub` + Neuschreiben + pikepdf-Allowlist, DOCX/ODT per lxml auf allen XML-Teilen, Ausgabe-PDF über LibreOffice headless, Prüfseite mit serverseitig gerenderten Seitenbildern statt pdf.js. Der Leck-Prüfer ist ein eigenes Paket ohne PyMuPDF und ohne gemeinsamen Code mit der Schwärzung (pypdf, pdfminer.six, pikepdf, pypdfium2 + Tesseract, LibreOffice-Textexport), fail-closed, ohne Abschaltschalter.

Die größten Risiken liegen nicht in der Erkennung, sondern in Leckorten, die weder Schwärzer noch Prüfer kennen (PDF-Strukturbaum, `BDC`-ActualText, geteilte XObjects, Font-Teilmengen, DOCX-Textfeld-Fallback, Datenbindung über customXml, ODT-Bedingungstext), in bösartigen Eingaben (die ExApp hält das AppAPI-Geheimnis), in Klartext an Nebenorten (Nextcloud-DB, Logs, Protokoll-Hashes, Versionen, geteilte Ordner) und in Scans, die der Spike nicht gemessen hat. Gegenmittel: Sandbox und Parser-Härtung vor jeder Format-Phase, ein mit fremden Werkzeugen erzeugter Leck-Zoo und ein Mutationstest des Prüfers vor der echten Schwärzung, Allowlist statt Blocklist für PDF-Katalog und ZIP-Teile, Klartext nur im Container-Volume mit Lebensdauer, Ausgabe erst nach Freigabe und bestandener Nachprüfung.

## Key Findings

### Recommended Stack

Python 3.13 ExApp aus dem Skeleton (FastAPI 0.162.0, nc-py-api 0.30.3, uv), alle Pakete exakt gepinnt, Modelle nie im Image, sondern mit festem sha256 im persistenten Speicher oder per Admin-Ablage. PHP-App für NC 33 bis 35 mit Vite-Build, weil `@nextcloud/files` 4.x die Dateiaktion nur als gebündeltes Modul richtig registriert (Abweichung von AVS, das ohne Build auskam). Details und Hashes: STACK.md.

**Core technologies:**
- **presidio-analyzer 2.2.366** (Projekt jetzt `data-privacy-stack/presidio`): Rahmen für Muster- und Kontexterkenner; erzwingt `numpy==2.4.6` (Deckel `<2.5.0`, anders als Findling/AV).
- **spaCy 3.8.18 + `de_core_news_lg` 3.8.0** (MIT, sha256 gepinnt): NER und Tokenisierung; EN/FR-Modelle bei Bedarf nachladen.
- **gliner2 2.1.0 + `fastino/gliner2-privacy-filter-PII-multi` @ `1cb41660`** (Apache-2.0): zweiter NER-Kanal, größter Recall-Hebel; ohne `[local]`-Extra.
- **torch 2.15.0+cpu nur aus `download.pytorch.org/whl/cpu`**: PyPI-torch zieht mehrere GB CUDA.
- **transformers 4.57.6** (Spike-Stand): Wechsel auf 5.x nur über das Release-Gate.
- **PyMuPDF 2.1** (AGPL, passt zur App-Lizenz): einzige Bibliothek, die Text, Bildpixel und Vektoren unter einer Fläche entfernt; Spike 0/88.
- **pikepdf 10.17.0**: Struktur-Nachlauf (Allowlist) und Rohobjekt-Prüfer.
- **lxml 6.1.3**: DOCX/ODT-Schwärzung, Parser gehärtet (keine Entitäten, kein Netz, DOCTYPE ablehnen; mindestens 6.1.0 wegen CVE-2026-41066).
- **pypdf 7.0.0, pdfminer.six 20260107, pypdfium2 5.15.0, rapidfuzz 3.14.6, python-docx, odfpy**: nur Prüfer; pypdfium2 neu gegenüber dem Spike als von MuPDF unabhängiger Renderer für die Prüf-OCR.
- **LibreOffice `libreoffice-writer-nogui` (trixie-security, ungepinnt) + metrisch kompatible Schriften**: PDF-Ausgabe aus DOCX/ODT, Vorschau-PDF, dritter Prüfer; je Aufruf eigenes Profil, Zeitgrenze, Gruppenkill.
- **Tesseract 5.5.0 + deu/eng/fra (+ osd) exakt gepinnt**: OCR; Wortpositionen über PyMuPDF `get_textpage_ocr`, Prüf-OCR über die Tesseract-CLI. Kein OCRmyPDF, kein pytesseract.
- **Frontend: Vue 3 + `@nextcloud/vue` 9.14.1, `@nextcloud/files` 4.1.1, `@nextcloud/vite-config` 2.5.4.**

Kritische Pflicht aus STACK: drei versteckte Netzaufrufe (Presidio lädt spaCy-Modelle per `spacy.cli.download`, tldextract holt die Public Suffix List, GLiNER2 fällt auf `AutoConfig.from_pretrained`) müssen abgestellt und per CI-Lauf im Container mit `--network none` belegt werden.

### Expected Features

**Must have (table stakes):**
- Arbeiten auf Kopie, Original unverändert, Ergebnis neben dem Original, geschrieben erst nach Freigabe.
- Echte Entfernung + Sanitize + vollständiges Neuschreiben, inklusive Strukturbaum (`/Alt`, `/ActualText`).
- Vorschlagsliste je Entität (Cluster) mit Zähler, aufklappbar zu Vorkommen; Zustände offen, angenommen, abgelehnt, unsicher (zweite Meinung).
- Annehmen/Ablehnen einzeln und "für alle gleichen Funde"; Sammelannahme nur für hohe Konfidenz, mit Anzahl-Bestätigung und Undo.
- Suchen und alles schwärzen (Umlaut-Varianten, Zeilenumbruch, Silbentrennung), manuelle Textmarkierung, Flächenschwärzung mit Tastaturalternative und ganzer Seite.
- Drei Konfidenzstufen, niedrige nie automatisch.
- OCR für Scans mit sichtbarer OCR-Qualität je Seite.
- Rechtsgrundlage je Schwärzung aus konfigurierbaren Sätzen; Protokoll (PDF + JSON) ohne Klartext.
- Zwei Modi Schwärzen und Pseudonymisieren; Ausgabe mindestens als PDF.
- Ehrlicher Fortschritt, konkrete Fehlgründe, Benachrichtigung ohne Fundinhalt.
- Prüf-UI nach BITV 2.0 / WCAG 2.1 AA, mit zugänglicher Textansicht (Seitenbild allein ist nicht zugänglich).

**Should have (Differenzierung):**
- Unabhängige, blockierende Leck-Nachprüfung mit Ergebnis im Protokoll.
- Deutsche Label-Sätze (IFG Bund, UIG, VIG, Länder, Urteilsveröffentlichung), als Daten, je Behörde änderbar, inklusive Label für bewusstes Nicht-Schwärzen (§ 5 Abs. 4 IFG).
- Amtsträger-Kategorie mit Unterscheidung "Bearbeiter im Vorgang" und "sonstige Bedienstete", bis zur Prüfung geschwärzt, Entscheidung protokolliert.
- Konsistente Pseudonyme über Varianten mit wählbarem Schema DE/EN/FR, ohne echte Initialen.
- Begründungsliste für den Bescheid (Seite, Umfang, Rechtsgrundlage, Kurzbegründung) als billiges Nebenprodukt der Labels.
- Vier-Augen-Freigabe (abschaltbar), Tastaturfluss mit Legende, Seitenübersicht mit Fundmarkern, Original/Ergebnis-Umschalter.
- Getaggtes, barrierefreies Ausgabe-PDF auf dem DOCX/ODT-Weg.
- Hinweise statt Versprechen: "Datum in Personenzeile", Art.-9-Begriffe, Beruf neben Name.
- Offene Qualitätszahlen (Leckrate je Kategorie und Dokumenttyp).

**Defer (v1.x / v2+):**
- v1.x: Rollen-Pseudonyme aus dem Rubrum, Prüfexemplar (audit copy), gerenderte Nebeneinander-Ansicht, Stapel-Analyse eines Ordners (Prüfung weiter je Datei), gleiche Pseudonyme über einen Vorgang, Label-Import/Export.
- v2+: Platzhalter-Tags für barrierefreie Ausgabe aus getaggten PDF-Quellen (Synergie mit der Schwester-App PDF Accessibility), Glyphen-Normalisierung ohne Rastern, Unterschrift-/Stempel-/Gesichtserkennung, Fristen und Drittbeteiligung § 8 IFG, Interop-Format.

**Anti-Features (bewusst nicht):** Auto-Schwärzung ohne Prüfung, Overlay-Ausgabe, echte Initialen als Standard-Pseudonym, `[PERSON]` ohne Zähler, umkehrbare Pseudonymisierung mit gespeicherter Zuordnung, Cloud-OCR/LLM, Rechtsberatung in der App, Klartext oder Einzelwert-Hashes im Protokoll, Rastern als Standard, Teilen vor Abschluss, PII-Markierung in Dateiliste/Vorschau.

### Architecture Approach

Zwei Apps im Lockstep nach dem AVS-Muster: Browser spricht nur mit PHP; PHP spricht über einen einzigen `ExAppService` signiert mit dem Container; der Container liest Originalbytes nur über das Content-Gateway der PHP-App (`actAs`, `readableFile`) und schreibt nie in Nutzerdaten. Arbeit läuft als Pull-Queue mit Lease (`analyze`, `apply`, `purge`), jede Stufe mit persistiertem Cursor. Modelle, LibreOffice, Tesseract und alle PDF-/XML-Parser laufen in Kindprozessen, nie im FastAPI-Prozess. Integrität der Freigabe liegt in PHP (Revision + sha256 des kanonischen Entscheidungsstands), Inhalt im Container.

**Major components:**
1. **Dateiaktion + JobController/JobService (PHP):** Start nach Rechteprüfung, Zustandsautomat mit geschlossener Status- und Grundliste, kein Freitext.
2. **ReviewController + Vue-Prüfseite (PHP):** Recheck bei jeder Anfrage (Mitgliedschaft, `readableFile`, Etag), Proxy für Seiten-PNG, Wortkästchen, Funde, Entscheide; `Cache-Control: private, no-store`.
3. **ApprovalService + Notifier, PublishJob, Lifecycle-Listener (PHP):** Vier-Augen ohne Selbstfreigabe, Ablage erst im Zustand `verified`, `getNonExistingName()` + `newFile()` als Auftraggeber, Purge bei Löschung/Änderung/TTL.
4. **Job-Runner + RAM-Wächter (Python):** ein Auftrag zur Zeit, Zulassung je Kindprozess-Art (Detektor 4 GB + 1 GB Reserve), nie Detektor und LibreOffice gleichzeitig.
5. **Doc-Worker (Python, Kindprozess):** Positionsindex (PDF `rawdict`, OCR-Wortboxen, DOCX/ODT-Textstrom mit Quellanker), Rendering, Schwärzung.
6. **Detektor-Host (Python, Kindprozess, warm):** Presidio + spaCy + GLiNER2; `logic/` ohne I/O für Zusammenführung, Stufen, Rollenwortfilter, Weitergabe, Amtsträger, Cluster, Pseudonym, Entscheidungs-Hash.
7. **Leck-Prüfer (eigenes Paket, eigener Prozess):** Importgrenze per AST-Test, keine gemeinsame Normalisierung, fail-closed.

### Critical Pitfalls

1. **Nachprüfung kennt nur die Fundorte des Schwärzers (Pitfall 1):** Leck-Zoo mit Kanarienwerten je Leckklasse, erzeugt mit Word, LibreOffice, Acrobat, qpdf und Scannern; Rohsuche in UTF-16BE, Hex, PDFDocEncoding, XML-Entitäten, Base64, rekursiv in eingebetteten ZIPs; Mutationstest mit Nachprüfer-Recall 100 % je Leckklasse als Release-Gate.
2. **PDF-Struktur und geteilte Objekte lecken (Pitfalls 2, 3):** pikepdf-Nachlauf als Allowlist (Katalog und Seiten neu aufbauen, `/StructTreeRoot`, `/PageLabels`, `/Dests`, `/PieceInfo` usw. weg), `BDC`-ActualText im Inhaltsstrom entfernen, `/ID` neu, geteilte XObjects und Bilder je Seite entflechten, Fonts neu untersetzen, signierte PDFs vorab melden.
3. **DOCX/ODT tragen Text an vielen Orten (Pitfalls 6, 7):** ZIP-Allowlist über `_rels`, generischer Durchlauf über alle Textknoten und Textattribute, `mc:Fallback`, Felder in statischen Text, Datenbindung und customXml weg, Bild-EXIF und Beschnitt, bedingter ODT-Text; Leck-Zoo aus echtem Word, nicht aus python-docx.
4. **Bösartige Dokumente übernehmen die ExApp (Pitfall 11):** Parser nur in Kindprozessen ohne AppAPI-Geheimnis in der Umgebung, mit rlimits und Zeitgrenze; ZIP-/PDF-/XML-Vorprüfung; externe Beziehungen und Makros vor LibreOffice entfernen; Bomben- und XXE-Korpus in CI.
5. **Prüfzustand, Protokoll, Logs, Nextcloud-Ablage werden selbst zum Leck (Pitfalls 8, 10):** kein Klartext in `oc_`-Tabellen, keine Einzelwert-Hashes, Logging nur mit Feld-Allowlist, Kanarien-Scan über DB, Logs und Volume in CI; Ausgabe erst nach Freigabe, nie überschreiben, geteilten Zielordner bestätigen lassen.
6. **Scans (Pitfall 5):** eine einzige Koordinatenquelle (eigene OCR in der Schwärzungsgeometrie), Boxen erweitern, MRC-Seiten flach rendern, Prüfziffer-Erkenner auf Scans zusätzlich ohne Prüfziffer als "niedrig", Pixelprüfung unter jedem Balken, Pflichtsichtung je Scan-Seite.

## Konflikte zwischen den Recherchen und ihre Auflösung

| Thema | Positionen | Auflösung (Empfehlung) |
|---|---|---|
| **Wo lebt der Prüfzustand mit Klartext-PII?** | PROJECT: "nur serverseitig, zugriffsbeschränkt, befristet". FEATURES-Diagramm: "Prüfzustand in App-DB". ARCHITECTURE: nur im Container-Volume (`state.db` mit `secure_delete`, `work/<job>/`), PHP hält nur Revision + Hash. PITFALLS 10: am besten gar kein Klartext, nur Offsets, Text zur Laufzeit aus dem Original, HMAC je Auftrag für "gleiche Funde". | **ARCHITECTURE gilt.** Einziger Klartextort ist das Container-Volume mit TTL; die Nextcloud-DB enthält nie Fundtext, Suchbegriffe, Kommentare oder Pseudonym-Zuordnungen (geschlossene Status-/Grundlisten, kein Freitext). Die strengere PITFALLS-Variante bringt wenig, weil die Quelldatei ohnehin in `work/<job>/` liegt; übernommen werden aber ihre Pflichten: Purge bei Veröffentlichung/Abbruch/Ablauf/Löschung, TTL verlängerbar (WCAG 2.2.1), zweite TTL-Linie im Container, `tmp` je Auftrag mit Aufräumen beim Start, Kanarien-Scan. "App-DB" in FEATURES ist als "App-Speicher" zu lesen. |
| **Hashes im Protokoll** | PROJECT: "Hashes". FEATURES: gesalzene Hashes je Schwärzung. ARCHITECTURE Pattern 7 und PITFALLS 10: keine Einzelwert-Hashes, nur Dateihashes. | **Keine Hashes einzelner Werte**, auch nicht gesalzen (Salz liegt beim Protokoll, kurze Werte wie PLZ, Steuer-ID, Nachname sind per Vollsuche umkehrbar). Protokoll enthält sha256 von Original und Ausgaben, je Schwärzung nur lfd. Nr., Seite, Position, Kategorie, Label, Herkunft, Konfidenzstufe, Entscheider. HMAC mit Instanzschlüssel nur auf späteren Owner-Entscheid. PROJECT-Zeile entsprechend präzisieren (Owner bestätigt). |
| **Wann entsteht die Ausgabe?** | PROJECT: Kopie neben dem Original. FEATURES, ARCHITECTURE, PITFALLS 8: erst nach Freigabe. | **Erst nach Freigabe und Urteil `clean`** schreibt PHP (PublishJob) als Auftraggeber. Vorher existiert nichts im Nutzerspeicher (sonst sehen Freigabe-Empfänger, Versionen, Findling und Volltextsuche einen Entwurf). Zusätzlich: nie überschreiben (`getNonExistingName`), geteilten Zielordner vor dem Schreiben bestätigen lassen, Dateiname und Ordnerpfad auf Personenbezug prüfen, UI warnt vor dem Ersetzen des Originals. |
| **Flächenschwärzung bei DOCX/ODT** | FEATURES: Fläche wirkt nur auf die PDF-Ausgabe, DOCX/ODT-Ausgabe entfällt oder mit Warnung; Ausnahme eingebettetes Bild. ARCHITECTURE: Anzeige über LibreOffice-Vorschau-PDF des Originals, Ausgabe-PDF aus dem geschwärzten Dokument. PITFALLS 15: Prüfansicht aus demselben Rendering wie die Ausgabe. | **Fläche auf DOCX/ODT erzeugt nur eine PDF-Ausgabe**, keine DOCX/ODT-Ausgabe (Ausnahme: Fläche liegt vollständig auf einem eingebetteten Bild, dann wird das Bild im XML ersetzt und beide Ausgaben bleiben). Weil Ersatztext den Umbruch verschiebt, dürfen Flächen nicht in Koordinaten der Original-Vorschau gespeichert und blind auf das Ausgabe-PDF übertragen werden: Flächen werden auf der gerenderten **Nachher**-Vorschau des geschwärzten Dokuments gesetzt bzw. bestätigt, und genau dieses Rendering wird mit PyMuPDF geschwärzt und ausgeliefert. Genaues Verfahren in der Office-Phase festlegen. |
| **Rastermodus vs. barrierefreies PDF** | PROJECT: "Höchste Sicherheit" (Rastern + frische OCR) wählbar. FEATURES/PITFALLS: Rastern zerstört Barrierefreiheit (BITV 2.0), 3,4 bis 6,3-fache Größe; Strukturbaum ist zugleich Leckquelle. | **Standard bleibt echte Entfernung**, Rastermodus nur bewusst wählbar mit Erklärung der Folgen, im Protokoll und Dateinamen kenntlich. Barrierefreiheit getrennt nach Quelle: DOCX/ODT-Weg liefert in v1 ein getaggtes PDF (Ersatztext "[geschwärzt]" bzw. Pseudonym im XML, LibreOffice-Export mit Tags; Strukturbaum geht durch den Leck-Prüfer). PDF-Quelle: v1 Strukturbaum entfernen, Ausgabe als "nicht barrierefrei" ausweisen; Platzhalter-Tags v2. Scans und Raster sind nie getaggt. |
| **Initialen als Pseudonym** | PROJECT: Varianten "Herr Müller", "Müller", "M." (Eingabe-Varianten). FEATURES: Standard "A., B." nach erstem Auftreten, nie die echten Initialen, echte Initialen nur als Option mit Warnung. PITFALLS 12: pro Dokument zufällig, nie aus Hash oder echtem Anfangsbuchstaben, Rollen statt Fantasienamen. | **"M." bleibt eine zu erkennende Variante, ist aber nie ein Ausgabe-Pseudonym.** Standard: fortlaufende Buchstaben je Kategorie in Reihenfolge des ersten Auftretens, Buchstabe gleich echter Initiale wird übersprungen, nichts aus Hash oder Name abgeleitet, je Dokument neu vergeben (über einen Vorgang gleich erst v1.x als bewusste Option). Keine realistischen Fantasienamen. Unsichere Zuordnungen werden Fund "Zuordnung prüfen" statt geraten. UI sagt "pseudonymisiert", nie "anonymisiert". |
| **RLIMIT_AS** | STACK: nicht für den torch-Worker. PITFALLS 15: RLIMIT_AS setzen. | Kein `RLIMIT_AS` für den Detektor-Host (virtueller Speicher von torch), dafür RAM-Wächter + `oom_score_adj`; `RLIMIT_AS` für Doc-Worker, LibreOffice und Prüfer nach Messung. |
| **Netz-Isolation der Parser** | PITFALLS 11: eigener Netz-Namespace (`unshare -n`/bubblewrap). STACK: bubblewrap unter Docker-seccomp meist gesperrt, ohne Capabilities kein Netz-Abschalten nur für LibreOffice. | Pflicht ohne Vorbehalt: Kindprozesse ohne AppAPI-Geheimnis in der Umgebung, rlimits, Zeitgrenze, Nicht-Root, externe Beziehungen und Makros vor LibreOffice entfernen, LO-Profil gehärtet, Test-DOCX mit externem Bild darf keinen Netzaufruf erzeugen. Netz-Namespace in der Sandbox-Phase unter HaRP/Docker ausprobieren; geht es nicht, Restrisiko dokumentieren. |
| **OCR-Zweitkanal bei Text-PDFs** | PITFALLS 4: im gründlichen Modus jede Seite rendern und OCR mit der Textebene vergleichen (kaputte CMaps, Vektortext, Bild-PII). Kostet ungefähr doppelte Laufzeit. | Bilder in Text-PDFs immer OCRen (Pflicht). Vollständiger Seitenvergleich im gründlichen Modus ist nach Owner-Regel "bestes Ergebnis" naheliegend, aber erst nach Messung festlegen (siehe Owner-Entscheidungen). |
| **Länder-Label-Sätze** | FEATURES: alle Länder in v1. PITFALLS 13: kein stiller Standard, Rechtsrahmen beim Einrichten wählen. Konfidenz der Länder-Paragrafen LOW bis HIGH gemischt. | Bund + Urteilsveröffentlichung als geprüfter Standardsatz; Länder als Daten mitliefern, aber als "juristisch ungeprüft" gekennzeichnet bis zum Gegenlesen; Admin wählt beim Einrichten den Rechtsrahmen, Hinweis "keine Rechtsberatung". |

## Offene Owner-Entscheidungen

Kurz, jeweils mit Empfehlung:

1. **Protokoll ohne Einzelwert-Hashes** (nur Dateihashes) bestätigen; PROJECT-Zeile anpassen. Empfehlung: ja.
2. **Fläche auf DOCX/ODT = nur PDF-Ausgabe** (Ausnahme Bildersatz). Empfehlung: ja, statt DOCX mit Warnung.
3. **Echte Initialen als Pseudonym-Option** mit Warnung anbieten oder ganz weglassen. Empfehlung: weglassen in v1.
4. **Gerundete Balkenbreite als Standard** (gegen Längenleck). Empfehlung: an.
5. **Download-Sperre der Freigabe blockiert den Start**, ohne Admin-Ausnahme in v1. Empfehlung: ja.
6. **Länder-Label-Sätze in v1** als "ungeprüft" markiert, und wer gegenliest. Empfehlung: ja, Gegenlesen vor Store.
7. **Begründungsliste für den Bescheid in v1** (billig, da Labels kommen). Empfehlung: ja.
8. **Protokoll-PDF neben der Kopie** standardmäßig an oder aus (enthält Prüfernamen, Zielordner oft geteilt). Empfehlung: aus, Abruf über die Prüfseite; Begründungsliste ist das Dokument für Antragsteller.
9. **OCR-Zweitkanal je Seite im gründlichen Modus** trotz ungefähr doppelter Laufzeit. Empfehlung: nach Messung im Testsatz entscheiden, bei Leckgewinn an.
10. **PDF-Quelle in v1 nicht barrierefrei** (Strukturbaum entfernt, ausgewiesen), Platzhalter-Tags v2. Empfehlung: ja.
11. **Diagramme, SmartArt, OLE in v1 entfernen** mit Meldung statt schwärzen. Empfehlung: ja.
12. **`fr_core_news_lg` (LGPL-LR) zur Laufzeit laden**, nicht ins Image. Empfehlung: ja.
13. **TTL des Prüfzustands** (Vorschlag 14 Tage, verlängerbar) und Seitenlimit je Auftrag (Vorschlag 300).
14. **Signierte PDFs:** Signatur wird entfernt, Hinweis vor Analyse und im Protokoll. Empfehlung: ja.

## Implications for Roadmap

Vorgeschlagene Struktur in 14 Phasen. Harte Reihenfolge-Regeln: Sandbox und Parser-Härtung vor jeder Format-Phase; Positionsindex vor Erkennung, Prüfseite, Schwärzung und Nachprüfung; Leck-Zoo und unabhängiger Leck-Prüfer fertig und grün, bevor echte Schwärzung als erledigt gilt. Testsatz und `logic/` laufen ab Phase 1 begleitend.

### Phase 1: Zwei-App-Gerüst und Integrationsbeweis
**Rationale:** Alle Plattform-Unbekannten (Dateiaktion in NC 33 bis 35, Streaming über HaRP, ID-Tausch mit Zertifikaten #1411/#1419) und das Datenmodell ohne Klartext müssen stehen, bevor irgendetwas Klartext speichert; spätere Migration von Klartextspalten ist wegen Backups teuer.
**Delivers:** Repo-Umbau `backend/` + `php/`, Lockstep/Handshake, Queue mit Lease, Gateway, Job an Datei-ID + Etag, geschlossene Status-/Grundlisten, Logging-Allowlist, RAM-Wächter-Grundform, Platzhalter-Durchstich (Dateiaktion, Job, Seite 1 als PNG über PHP-Proxy mit Recheck, Benachrichtigung, Dummy-Kopie per `newFile()`), CI mit HaRP auf NC 33/34/35.
**Addresses:** Dateiaktion, Benachrichtigung, Zugriff nur für Berechtigte.
**Avoids:** Pitfalls 8, 9, 10 (Grundlagen), Anti-Patterns 1, 2, 5.

### Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox
**Rationale:** Alle Formate teilen dieselbe Sandbox; ein späterer Umbau ändert den Prozessaufbau der ExApp.
**Delivers:** Kindprozess-Host (JSON über Pipe), Umgebung ohne Geheimnis, rlimits, Zeitgrenzen, Prozessgruppen-Kill; Vorprüfung PDF (Seiten, Objekte, Pixel, Streams), ZIP (Größen, Rate, Einträge, Tiefe, Duplikate, `..`), XML (DOCTYPE ablehnen, gehärteter Parser); Magic-Bytes statt Endung; verschlüsselte/E2EE/signierte Dateien mit Grund; LibreOffice-Runner gehärtet; Bomben-, XXE-, Doppelnamen- und External-Rels-Korpus in CI; Netzfreiheitstest `--network none`; Abstellen der drei versteckten Netzaufrufe.
**Avoids:** Pitfall 11, Pitfall 15 (LibreOffice-Zombies).

### Phase 3: Positionsindex und Dokumentmodell
**Rationale:** Prüfansicht, Suche, Schwärzung und Nachprüfung hängen am selben Index; ein Index verhindert, dass die UI etwas anderes markiert als die Schwärzung entfernt.
**Delivers:** PDF `rawdict` mit Zeichen-Bboxen, DOCX/ODT-Textstrom mit Quellanker über alle Teile, Normalisierung mit Offset-Rückabbildung (NFKC, Ligaturen, U+00AD, NBSP, Nullbreite), Erkennung unsichtbarer Inhalte (Render-Modus 3, weißer Text, OCG aus, außerhalb CropBox), Vorschau-PDF via LibreOffice, Abbildung XML-Fund auf Vorschau-Kästchen, Seitenbilder lazy, Scan-Seiten-Erkennung (nur Markierung).
**Avoids:** Pitfall 4, Anti-Pattern 8.

### Phase 4: Testsatz, Leck-Zoo und Eval-Harness (begleitend ab Phase 1, fertig vor Phase 6)
**Rationale:** Ohne Leckklassen-Korpus lassen sich Pitfalls 1 bis 7 nicht nachweisen; ohne Holdout misst die Evaluation das eigene Spiegelbild.
**Delivers:** Leck-Zoo mit Kanarienwerten je Fundort, erzeugt mit Word, LibreOffice, Acrobat, qpdf, Scannern (Tagged PDF, Seitenlabels, Ziele, Signatur, Briefkopf-XObject, beschnittene Bilder, seltene Glyphen, MRC, Textfeld-Fallback, SmartArt, Diagramm-Cache, Datenbindung, Glossar, Kopf/Fuß-Varianten, ODT-Bedingungstext); Positivkontrollen aus Spike 5; kleines lizenzfreies CI-Korpus im Repo, große Korpora lokal; Kennzahlen Leckrate Zeichen, Anteil Dokumente mit Leck, exakter Recall je Kategorie/Format, Recall nach Namensherkunft; Dreiteilung mit Holdout von anderer Hand.
**Avoids:** Pitfalls 1, 14.

### Phase 5: Unabhängiger Leck-Prüfer
**Rationale:** Die Schwärzung soll gegen einen fertigen, unabhängigen Prüfer entstehen, nicht umgekehrt (Owner-Regel "Gegenprobe nie mit dem Muster der Umsetzung").
**Delivers:** Paket `leakcheck/` ohne PyMuPDF und ohne Import aus `redact/`, `detect/`, `docmodel/` (AST-Test); Text unscharf (pypdf, pdfminer, NFKD, Joker), Rohsuche (alle Kodierungen, rekursiv), Revisionszählung, OCR über pypdfium2 + Tesseract, LibreOffice-Textexport, Positionsprüfung für kurze Werte und Pixelprüfung unter Balken; Regel für erlaubte Vorkommen abgelehnter gleicher Werte; fail-closed; Mutationstest je Leckklasse mit 100 % als Gate.
**Avoids:** Pitfall 1, Anti-Pattern 3.

### Phase 6: Echte Schwärzung Text-PDF
**Rationale:** Kernwert, Eingabe noch Gold-Spannen, gegen fertigen Prüfer.
**Delivers:** Entflechten geteilter XObjects/Bilder, `apply_redactions` mit expliziten Parametern, Annotationen vorher entfernen, `scrub`, `subset_fonts`, `garbage=4`, pikepdf-Allowlist-Nachlauf, `BDC`-Eigenschaften bereinigen, `/ID` neu, Strukturbaum entfernen (als "nicht barrierefrei" ausweisen), gerundete Balkenbreite, Label im Balken optional (Auto-Size), Modus "Höchste Sicherheit"; E2E-Lecktest in CI.
**Avoids:** Pitfalls 2, 3, Anti-Pattern 4.

### Phase 7: Echte Schwärzung DOCX/ODT und Ausgabe-PDF
**Rationale:** Eigene Leckklassen und LibreOffice-Lebenszyklus; braucht Sandbox (2), Index (3), Zoo (4), Prüfer (5).
**Delivers:** ZIP-Allowlist, generischer Textknoten- und Attributdurchlauf, `mc:Fallback`, Felder statisch, Datenbindung/customXml/Glossar/rsid/attachedTemplate weg, Bild-EXIF und Beschnitt, ODT-Bedingungstext und Benutzerfelder, Diagramme/SmartArt/OLE entfernen mit Meldung, getaggtes PDF über LibreOffice, Flächen nur auf PDF-Ausgabe (Verfahren über Nachher-Rendering), beide Ausgaben geprüft.
**Avoids:** Pitfalls 6, 7, 15.

### Phase 8: Erkennung
**Rationale:** Größter Block, Logik ab Phase 1 offline gegen Spike-Daten baubar; Einbindung braucht Index (3).
**Delivers:** Modell-Register mit sha256 und Admin-Ablage, Detektor-Host warm/Leerlauf-Ende, DE-Erkenner mit Prüfziffer (Scan-Variante ohne Prüfziffer als "niedrig"), Telefon mit Datumsfilter, eigener E-Mail-Erkenner, GLiNER2-Stückelung mit Überlappung und Kürzungswarnung als Fehler, `logic/` (Stufen, Rollenwortfilter, Weitergabe, Gazetteer "Namen, die Wörter sind", Amtsträger mit Bearbeiter/sonstige, private Kontaktdaten getrennt, Cluster, Datumshinweis, Art.-9-Hinweis), Leckraten-Gate DE, Schnellmodus nur bewusst.
**Avoids:** Pitfalls 13, 14, 15 (Stückelung), Anti-Pattern 6.

### Phase 9: Prüfseite
**Rationale:** Braucht Index und Funde (kann mit Fake-Funden parallel zu 8 beginnen).
**Delivers:** Vue-App mit Seitenübersicht, Seitenbild + Kästchen, Entitätenliste mit Zähler, vier Zustände, Sammelaktionen mit Bestätigung und Undo, Suchen und schwärzen, Textmarkierung, Fläche mit Tastaturalternative, Hinweise "verborgener Text"/"nicht angezeigte Fußzeile"/"Metadaten", Original/Ergebnis-Umschalter, Tastaturfluss WCAG-2.1.4-konform, zugängliche Textansicht, Revisionen mit 409, nur Textbindung (kein `v-html`), Playwright 3 Breiten hell/dunkel.
**Avoids:** UX-Pitfalls, Pitfall 9 (Recheck je Anfrage).

### Phase 10: Workflow, Ablage, Rechtsgrundlagen, Protokoll
**Rationale:** Braucht Anwenden (6/7) und Prüfen (9); liefert den Kernwert "Text-PDF/DOCX/ODT schwärzen, geprüft, abgelegt".
**Delivers:** Status Entwurf/geprüft/freigegeben, Vier-Augen mit Freigabegruppe (keine Selbstfreigabe, Freigeber braucht Leserecht), Revision + Hash, PublishJob nur bei `verified`, geteilter Zielordner bestätigen, nie überschreiben, Label-Katalog mit Rechtsrahmen-Auswahl, Zusammenfassung "nicht geschwärzt: N Amtsträger" vor Freigabe, Protokoll PDF + JSON (geschlossene Feldliste), Begründungsliste, TTL/Purge, Lifecycle-Listener, Rechte-Negativtests (ACL-Entzug, Zweitprüfer ohne Zugriff, Etag-Wechsel, Download-Sperre), Kanarien-Scan über DB, Logs, Volume.
**Avoids:** Pitfalls 8, 9, 10, 13.

### Phase 11: Scans und OCR
**Rationale:** Im Spike ungemessen, erweitert einen funktionierenden Kernweg statt ihn zu blockieren.
**Delivers:** Eigene OCR als einzige Koordinatenquelle mit Transformationsmatrix und Rundweg-Test, osd, dpi-Warnung, Box-Erweiterung, MRC flach rendern, Pixel-Schwärzung mit `deflate`, alte Textebene verwerfen, frische OCR nach dem Schwärzen, Pflichtsichtung je Scan-Seite, Hinweis Handschrift/Stempel, ggf. `tessdata_best` nach Messung.
**Avoids:** Pitfall 5.

### Phase 12: Pseudonymisierung
**Rationale:** Braucht Cluster (8), Prüfseite (9) und Schwärzungswege (6/7).
**Delivers:** Schemata DE/EN/FR ohne echte Initialen, Kategorien-Namensräume, Cluster verknüpfen/trennen mit Neuvergabe, Flexion (Genitiv, "Herrn", "-sche", Bindestrich, Elision, "Smith's"), Geschlecht aus Anrede, Ersatztext im PDF mit Base-14-Font und Längenprüfung, Positivprüfung "jedes Pseudonym steht in der Ausgabe", Prüfer mit Originalwerten als Geheimnissen, keine gespeicherte Zuordnung nach Purge.
**Avoids:** Pitfall 12.

### Phase 13: EN/FR-Regeln auf DE-Niveau
**Rationale:** Braucht Erkennung und Eval-Harness.
**Delivers:** Aktenzeichen, Anschriften, IDs für EN/FR, EN/FR-Modelle nachladbar (FR zur Laufzeit wegen LGPL-LR), Leckraten-Gate je Sprache.

### Phase 14: Release-Härtung
**Rationale:** Owner-Gates.
**Delivers:** Admin-Zustände, Dreisprachigkeit inkl. README im Gleichstand, Umlaut-Audit, arm64-Messung (Tempo, Gate auf beiden Architekturen), Image-Größe, Lasttest auf kleiner Zielmaschine, Sicherheitsaudit mit Negativtests, Integrationstest mit Findling und Versions-App, Holdout-Gate, Volltest DE/EN/FR, gemeinsame Playwright-Abnahme.

### Phase Ordering Rationale

- **Klartext-Datenmodell zuerst (1):** Speicherorte, Etag-Bindung und Logging-Regeln müssen feststehen, bevor irgendeine Phase Funde speichert.
- **Sandbox vor Formaten (2 vor 3, 6, 7, 11):** jede Format-Phase parst fremde Dateien; die ExApp hält das AppAPI-Geheimnis.
- **Positionsindex vor allem, was markiert oder entfernt (3 vor 5, 6, 8, 9):** ein Koordinatensystem für Anzeige, Suche, Schwärzung; der Prüfer nutzt bewusst andere Extraktoren.
- **Leck-Zoo und Prüfer vor echter Schwärzung (4, 5 vor Abschluss von 6, 7):** sonst wird der Prüfer am Schwärzer kalibriert und sieht dieselben blinden Flecken.
- **Erkennung nach der Schwärzung möglich:** Schwärzung arbeitet zunächst auf Gold-Spannen; `logic/` und Regeln laufen parallel offline gegen die Spike-Daten.
- **Workflow (10) vor Scans (11) und Pseudonymisierung (12):** liefert früh den Kernwert für Text-PDF und Office, Erweiterungen bauen darauf auf.

### Research Flags

Phasen mit Bedarf an `/gsd:plan-phase --research-phase`:
- **Phase 2:** Netz-Namespace/Prozessisolation unter HaRP/Docker, LibreOffice-25.2-Härtungsschlüssel (Makros, externe Links) mit Netzwerkmitschnitt.
- **Phase 3:** Abbildung DOCX/ODT-Fund auf Vorschau-Kästchen (Tabellen, Silbentrennung, Felder), Umgang mit unsichtbaren Inhalten.
- **Phase 5:** pypdfium2 als unabhängiger Renderer (Positivkontrollen wiederholen), Regel für erlaubte Vorkommen.
- **Phase 6:** MuPDF-Verhalten bei geteilten Form XObjects, `BDC`-ActualText, `subset_fonts` nach Schwärzung, Strukturbaum nach `apply_redactions`.
- **Phase 7:** Feldaktualisierung in LibreOffice, Textfeld-Fallback, PDF/UA-Export im Container, Flächen-Verfahren über Nachher-Rendering.
- **Phase 10:** Versions-API NC 33 bis 35, Erkennung geteilter Zielordner, juristisches Gegenlesen der Label-Sätze.
- **Phase 11:** komplett offen: OCR-Qualität deutscher Behördenscans, MRC-Masken, Laufzeit, Glyphenpositions-Leck (PoPETs 2023).
- **Phase 12:** Ersatztext im PDF bei längeren Pseudonymen, Flexionsregeln, Initialen-Cluster 73 %.

Standardmuster (Recherche überspringen):
- **Phase 1:** AVS-Zwei-App-Muster, Gateway, Queue, ExAppService.
- **Phase 9:** Nextcloud-Vue-Komponenten, UI-Ablauf nach Owner-Regel (DESIGN.md, Playwright).
- **Phase 14:** AVS-Gates, Release-/Zertifikats-Pipeline.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versionen, Wheels beider Architekturen, Abhängigkeitsdeckel und Modell-Hashes am 07.11. direkt geprüft bzw. selbst gehasht; MEDIUM für LGPL-LR-Auslegung und LibreOffice-Härtung, LOW für Image-Größe (nicht gebaut). |
| Features | MEDIUM | Wettbewerber überwiegend Herstellerangaben; JANO und FAU aus Primärquellen; IFG Bund HIGH, Länder-Paragrafen gemischt bis LOW; Tastaturfluss ohne Branchenvorbild. |
| Architecture | HIGH | Nextcloud-/AppAPI-Grenzen im Quellcode stable33 bis 35 nachgesehen, Muster in AVS belegt, Pipeline aus dem Spike gemessen; MEDIUM für DOCX-Abbildung, Streaming durch HaRP, LibreOffice-Härtung; LOW für Scans. |
| Pitfalls | MEDIUM | Viele Punkte belegt (PyMuPDF-Doku, Nextcloud-Manual, CVEs, USENIX 2023), etliche ausdrücklich "Test nötig" (MuPDF bei XObjects/MRC/BDC, LibreOffice-Feldaktualisierung). |

**Overall confidence:** MEDIUM. Der Kernweg Text-PDF/DOCX/ODT ist gut belegt; Scans, PDF-Strukturlecks und Container-Messwerte sind die offenen Flanken.

### Gaps to Address

- **Container-Messwerte fehlen** (Linux-RSS des Stapels, LibreOffice-Spitze, Image-Größe amd64/arm64, Kaltstart): in Phase 1/2 messen, RAM-Schwellen erst danach festschreiben.
- **Netzfreiheit nur im Code belegt:** CI-Lauf `--network none` über Erkennung, Schwärzung und Prüfung.
- **Scans ungemessen:** eigene Messphase (11), echte Scans verschiedener Hersteller in den Zoo.
- **Strukturbaum- und XObject-Verhalten von PyMuPDF:** mit Leck-Zoo-Dateien in Phase 6 klären.
- **DOCX/ODT-Flächen und Anzeigeabbildung:** Verfahren über Nachher-Rendering in Phase 3/7 festlegen und messen.
- **Zielmaterial:** FAU/ALeKS-Goldstandard angefragt; bis dahin Holdout von anderer Hand und Recall nach Namensherkunft.
- **Länder-Rechtsgrundlagen:** juristisches Gegenlesen vor Store.
- **Prüferverhalten:** kleiner Nutzertest der Prüfseite (Zeit pro Seite, Fehlannahmen) vor Release.
- **arm64-Tempo:** GLiNER2 auf Cortex-A76 kann ein Vielfaches von 8 bis 11 s/Seite brauchen; Fortschrittsanzeige muss das tragen.

## Sources

### Primary (HIGH confidence)
- Spike 06.11.2026 `C:/Users/Student/pii-spike-2026-11-06/SPIKE-REPORT.md` (Stapel, RAM 3,96 GB, Kaltstart 16,5 s, Schwärzung 0/88, Positivkontrollen 84/88, Glyphen-Befund, Amtsträger 2/566)
- PyPI JSON-API, PyTorch-CPU-Index, Hugging Face API, GitHub `explosion/spacy-models`, Debian madison (Versionen, Wheels, Hashes, 07.11.2026)
- `nextcloud/server` und `nextcloud/app_api` stable33 bis 35 (Proxy-Zugriffsstufen, `exAppRequest`, `newFile`, `ViewOnly`, Notifications), `nextcloud-libraries/nextcloud-files` v4.1.1
- Audio & Video Search (Zwei-App-Muster, Gateway, ExAppService, Gates)
- PyMuPDF-Doku `apply_redactions`, Nextcloud Admin Manual (Versionen, Data retention), USENIX Security 2023 (Initialen), JANO-Folien 21.04.2026, FAU AnGer 2025, PoPETs 2023

### Secondary (MEDIUM confidence)
- Herstellerseiten Conduction (Filinq/Anonymiq), Objective Redact, Redactable, Adobe, Relativity
- LGPL-LR-Volltext (Auslegung), Länder-Informationsfreiheitsgesetze (Inhaltsverzeichnisse, Handreichungen), BVerwG 7 C 27/15, EuGH C-413/23 P
- CVE-Aggregatoren zu lxml, pypdf, Gotenberg/LibreOffice; iText pdfSweep 5.0.8; pdf-tools Smart Redact; GLiNER-Doku zu Eingabegrenzen
- Barrierefreie Schwärzung (Allyant/CommonLook), BITV/PDF-UA-Leitfäden

### Tertiary (LOW confidence)
- Paragrafen UIG, VIG, BremIFG, IZG LSA, SIFG, SächsTranspG (Fachwissen), französische Judilibre-Konvention, veraPDF-Eignung, LibreOffice-Hängefälle (alte Bugs), Image-Größen-Schätzung

---
*Research completed: 07.11.2026*
*Ready for roadmap: yes*
