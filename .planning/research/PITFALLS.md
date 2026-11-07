# Pitfalls Research

**Domain:** Lokale Schwärzung und Pseudonymisierung personenbezogener Daten (PDF inkl. Scans, DOCX, ODT) als Nextcloud-App (PHP `pii_redaction` + ExApp `pii_redaction_backend`) für deutsche Behörden
**Researched:** 2026-11-07
**Confidence:** MEDIUM (PDF/OOXML-Mechanik und Nextcloud-Verhalten teils offiziell belegt, teils Fachwissen; mehrere Punkte sind ausdrücklich als "Test nötig" markiert)

## Lesehilfe

- Dieses Dokument wiederholt die im Spike und in der Recherche vom 04.11. bereits belegten Fallstricke (Overlay, inkrementelle Updates, OCR-Textebene, PoPETs-2023-Glyphenleck, Glyphen-Fehlzuordnung in Extraktoren, Amtsträger-Regel nimmt Privatpersonen aus, Presidio-Telefonerkenner, Domänenverschiebung) **nur als Verweis**. Neu sind die Vertiefungen und die fehlenden Klassen.
- Belegstufen je Punkt: **[belegt]** offizielle Doku oder Primärquelle abgerufen am 07.11.2026; **[Spike]** im Spike gemessen; **[Fachwissen]** bekannte Format- oder Produktmechanik, nicht neu abgerufen; **[Test nötig]** plausibel, muss im Projekt mit einer Testdatei bestätigt oder widerlegt werden.
- Phasennamen sind Vorschläge für die Roadmap (die tatsächliche Nummerierung legt der Roadmapper fest):
  - **P-Gerüst**: Zwei-App-Umbau, Auftragsmodell, Speicherorte, Logging-Grundsätze
  - **P-Eingang**: sicherer Dateieingang, Sandbox, Parser-Härtung, Ressourcen-Grenzen
  - **P-Extraktion**: Textebene, Lesereihenfolge, OCR, Koordinaten
  - **P-Erkennung**: Erkennerstapel, Normalisierung, EN/FR-Regeln
  - **P-Prüf-UI**: Prüfseite, Entscheidungen, Vier-Augen
  - **P-PDF**: echte Schwärzung PDF inkl. Scans
  - **P-Office**: echte Schwärzung DOCX/ODT, LibreOffice-PDF-Ausgabe
  - **P-Pseudo**: Pseudonymisierung
  - **P-Nachprüfung**: automatische Leck-Nachprüfung
  - **P-Nextcloud**: Ausgabe, Rechte, Versionen, Freigaben, Suche
  - **P-Protokoll**: Schwärzungsprotokoll, Aufbewahrung, Rechtsgrundlagen
  - **P-Testsatz**: Testsatz, Leck-Zoo, CI-Gate (beginnt früh, läuft begleitend)
  - **P-Release**: Härtung, Volltest DE/EN/FR, Store

---

## Critical Pitfalls

### Pitfall 1: Die Nachprüfung prüft nur, was der Schwärzer auch kennt (Leck-Zoo fehlt)

**What goes wrong:**
Die automatische Nachprüfung meldet "sauber", weil sie dieselben Orte durchsucht, die der Schwärzer bereinigt (Seitentext, Info, XMP, Annotationen). Lecks in Orten, die beide nicht kennen (Strukturbaum, Seitenlabels, benannte Ziele, Bild-EXIF, Diagramm-Cache, Textbox-Fallback), bleiben unsichtbar. Der Spike bestätigt die Mechanik bereits im Kleinen: exakter Abgleich übersah 7/88 Namen im ungeschwärzten Original [Spike].

**Why it happens:**
Positivkontrollen werden aus denselben Testdokumenten gebaut, die der Schwärzer kennt. Owner-Regel "Gegenprobe nie mit dem Muster der Umsetzung" wird auf Bibliotheksebene erfüllt (pypdf statt PyMuPDF), aber nicht auf Ebene der **Fundorte**.

**How to avoid:**
- Einen **Leck-Zoo** als eigenes Korpus aufbauen: je Fundort dieses Dokuments eine Datei mit einem Kanarienwert (eindeutige Zeichenkette, z. B. `KANARIE-7F3A-Strukturbaum`), erzeugt mit einem **anderen Werkzeug** als dem Schwärzer (Word, LibreOffice, Acrobat-Export, qpdf, Scanner-PDF, nicht nur PyMuPDF).
- Nachprüfung zusätzlich als **Rohsuche über die ganze Datei**: alle Streams dekomprimiert, alle Strings, alle ZIP-Einträge, in UTF-8, UTF-16BE (PDF-Textstrings), PDF-Hex-Strings, PDFDocEncoding, XML-Entitäten (`&#252;`), Base64 in XMP/customXml.
- **Mutationstest der Nachprüfung**: für jede Leckklasse eine absichtlich kaputte Ausgabe; die Nachprüfung muss jede melden. Kennzahl "Nachprüfer-Recall je Leckklasse" ist Release-Gate.
- Zuerst **Allowlist statt Blocklist**: Ausgabe-PDF nur aus bekannten Objekttypen aufbauen (siehe Pitfall 3), unbekannte Schlüssel entfernen und protokollieren.

**Warning signs:**
Nachprüfung meldet über Wochen nie einen Fund; neue Testdateien kommen nur aus dem eigenen Generator; Leckklasse ohne eigenen Testfall.

**Phase to address:** P-Testsatz (Leck-Zoo früh anlegen), P-Nachprüfung (Mutationstest als Gate), P-Release.

---

### Pitfall 2: PDF-Seiteninhalt sauber, PDF-Struktur leckt (Strukturbaum, ActualText, Alt, Seitenlabels, benannte Ziele)

**What goes wrong:**
`apply_redactions` entfernt Zeichen aus dem Inhaltsstrom, aber nicht die Zeichenketten in:
- **Tagged-PDF-Strukturbaum** (`/StructTreeRoot`): `/ActualText`, `/Alt`, `/E` (Abkürzungsauflösung), `/T` (Titel) an Strukturelementen; Word und LibreOffice schreiben bei barrierefreiem Export z. B. Alternativtexte von Bildern ("Foto von Herrn Müller") und Überschriften in den Baum. iText pdfSweep 5.0.8 führte genau diesen Fehler als Bug "Redacted text recoverable from tagged PDF structure elements" [belegt]; pdf-tools dokumentiert, dass Marked Content beim Schwärzen nicht entfernt wird und ActualText lecken kann [belegt].
- **Marked-Content-Eigenschaften im Inhaltsstrom** (`/Span <</ActualText (Müller)>> BDC`): Text-Operatoren werden entfernt, das Eigenschaften-Dictionary bleibt stehen [Test nötig für PyMuPDF].
- **Seitenlabels** (`/PageLabels` mit `/P`-Präfix, z. B. "Akte Müller 1").
- **Benannte Ziele** (`/Dests`, `/Names/Dests`): Word exportiert Überschriften und Textmarken als Ziele; Namen wie `_Toc_Anhörung_Müller` oder Textmarken `Adresse_Schmidt`.
- **Link-Ziele**: `mailto:k.mueller@...`, URLs mit Namen oder IDs im Query-String, `/Launch`- und `/GoToR`-Aktionen mit Dateipfaden (`C:\Users\kmueller\...`). PyMuPDF entfernt nur Links, die eine Schwärzungsfläche überlappen [belegt, PyMuPDF-Doku `apply_redactions`]; Links an anderer Stelle bleiben.
- **Dokument-ID** (`/ID` im Trailer): verknüpft die Ausgabe eindeutig mit dem Original (kein Name, aber ein Identifikator, der eine spätere Zuordnung zu einer geleakten Originalkopie erlaubt).
- **XMP-Historie** (`xmpMM:History`, `xmpMM:DerivedFrom`, `stEvt:instanceID`), **`/PieceInfo`** (private Anwendungsdaten, bei Illustrator/InDesign teils das ganze Quelldokument) und **Objekt-Metadaten**: auch einzelne Bild-XObjects können einen eigenen `/Metadata`-Stream tragen.
- **Signaturen**: Signaturfeld `/V` mit PKCS#7 in `/Contents`, darin das Zertifikat mit vollem Namen des unterzeichnenden Beamten; Signatur-Erscheinungsbild als Bild.

**Why it happens:**
`Document.scrub()` deckt eine feste Liste ab (Anhänge, versteckter Text, JavaScript, Metadaten, XMP, Links, Thumbnails, Formularfelder, Annotationen) [Fachwissen, PyMuPDF-Doku nur teilweise abrufbar]; Strukturbaum, Seitenlabels, benannte Ziele, `/PieceInfo`, `/ID` und Objekt-Metadaten stehen nicht sicher darauf. Der Spike hat diese Orte nicht erzeugt [Spike: nicht abgedeckt].

**How to avoid:**
- pikepdf-Nachlauf als **Allowlist** umbauen: Katalog nur mit `/Type /Pages /Lang?` neu aufbauen; `/StructTreeRoot`, `/MarkInfo`, `/PageLabels`, `/Dests`, `/Names`, `/Outlines`, `/OpenAction`, `/AA`, `/AcroForm`, `/Metadata`, `/PieceInfo`, `/OCProperties`, `/Perms`, `/Legal`, `/URI` entfernen; Seiten nur mit `/Type /Parent /MediaBox /CropBox /Rotate /Resources /Contents`.
- In Inhaltsströmen alle `BDC`-Eigenschaften mit `/ActualText`, `/Alt`, `/E` entfernen oder durch leere Werte ersetzen (Inhaltsstrom-Filter mit pikepdf `parse_content_stream`).
- `/ID` neu erzeugen (zufällig, beide Teile).
- Signierte PDFs vor der Analyse erkennen und den Nutzer informieren: Ausgabe ist unsigniert, Signatur wird entfernt (nicht nur ungültig).
- Barrierefreiheit-Konflikt bewusst entscheiden: Strukturbaum entfernen bricht PDF/UA und BITV 2.0; sauberer Weg wäre ein bereinigter Neuaufbau des Baums (späterer Meilenstein, Synergie mit der Schwester-App PDF Accessibility). In v1: Baum entfernen, im Protokoll und in der UI ausweisen.

**Warning signs:**
Ausgabe-PDF besteht einen PAC/veraPDF-Check auf Tagged PDF (Baum ist also noch da); `qpdf --show-object=trailer` zeigt dieselbe `/ID` wie das Original; Leck-Zoo-Datei aus Word "barrierefrei exportiert" fehlt.

**Phase to address:** P-PDF (Allowlist-Nachlauf), P-Nachprüfung (Rohsuche UTF-16BE), P-Testsatz (Word-, LibreOffice- und Acrobat-Exporte mit Tags).

---

### Pitfall 3: Geteilte Ressourcen über Seiten (Form XObjects, Bilder, Fonts, JBIG2Globals)

**What goes wrong:**
- **Form XObjects**: Briefkopf, Fußzeile, Stempel oder ganze Seiten (bei manchen Erzeugern und nach Seiten-Import) liegen als Form XObject, das mehrere Seiten referenzieren. Wird der Name auf Seite 1 geschwärzt, muss das XObject verändert werden; entweder trifft die Änderung alle Seiten (Überschwärzung an falscher Stelle) oder das XObject bleibt unverändert und der Name ist auf Seite 1 weiter da [Test nötig: Verhalten von MuPDF bei verschachtelten und geteilten XObjects nicht in der abgerufenen Doku beschrieben].
- **Bilder**: Bei `PDF_REDACT_IMAGE_REMOVE` entfernt PyMuPDF nur die Referenzen dieser Seite, nicht das Bild selbst [belegt]. Ist dasselbe Bild auf einer anderen Seite **beschnitten** (Clipping) eingebunden, ist es dort nur teilweise sichtbar; der volle Inhalt steckt im Objekt. Gleiches gilt für Bilder in DOCX (`a:srcRect`-Beschnitt, siehe Pitfall 6).
- **Fonts**: Teilmengen-Fonts enthalten nur verwendete Glyphen. Nach dem Entfernen eines Namens bleiben Glyphenumrisse, `/Widths`-Einträge und ToUnicode-Zuordnungen seltener Zeichen (z. B. "ğ", "ł", "Ý" eines nicht-deutschen Namens) im Font, wenn nicht neu untergesetzt wird. Das verrät einzelne Zeichen des geschwärzten Namens, besonders bei kleinen Dokumenten [Fachwissen; PyMuPDF bietet `Document.subset_fonts()`, Wirkung nach Schwärzung Test nötig].
- **JBIG2Globals**: Gescannte Seiten mit JBIG2 teilen sich ein globales Symbolwörterbuch. Die Pixel-Schwärzung ersetzt das Seitenbild durch ein neues PNG [belegt: PyMuPDF erzeugt bei `PDF_REDACT_IMAGE_PIXELS` ein neues PNG], das globale Wörterbuch bleibt aber stehen, solange andere Seiten es referenzieren. Es enthält Glyphenformen, keine Anordnung; Leckgehalt gering, aber nicht null (z. B. Unterschriftsfragmente) [Test nötig, Ableitung nicht belegt].

**Why it happens:**
Schwärzung wird als Seitenoperation gedacht, PDF ist aber ein Objektgraph. `garbage=4` entfernt nur unreferenzierte Objekte.

**How to avoid:**
- Vor der Schwärzung jede Seite **entflechten**: geteilte Form XObjects und Bilder je Seite kopieren (pikepdf), damit jede Änderung lokal ist; danach erst `apply_redactions`.
- Fonts nach dem Schwärzen neu untersetzen (`subset_fonts()`), Ergebnis im Leck-Zoo prüfen (Datei mit Namen aus seltenen Zeichen).
- Bilder mit Clipping oder `/SMask`: nach der Schwärzung die **ungeclippte** Bildfläche gegen die Schwärzungsrechtecke prüfen; im Zweifel Bild auf den sichtbaren Ausschnitt zuschneiden.
- Leck-Zoo-Fälle: Briefkopf als geteiltes XObject mit Namen der Sachbearbeiterin; Bild mit beschnittenem Namensschild; JBIG2-Mehrseiter.

**Warning signs:**
Nach Schwärzung auf Seite 1 verschwindet derselbe Kopfbereich auf allen Seiten; `qpdf --check` zeigt Bildobjekte, deren Pixelfläche größer als die sichtbare Fläche ist; Fontdatei der Ausgabe enthält Glyphen, die im Ausgabetext nicht vorkommen.

**Phase to address:** P-PDF, P-Testsatz.

---

### Pitfall 4: Textebene stimmt nicht mit dem sichtbaren Bild überein (Erkennung blind, Prüfer sieht den Namen)

**What goes wrong:**
Der Spike hat Glyphen-Fehlzuordnung als Problem der **Nachprüfung** gezeigt [Spike 5.2]. Dasselbe Problem trifft die **Erkennung**, und zwar schlimmer:
- **Kaputte oder absichtlich verfremdete ToUnicode-CMaps** (Fachverfahren, Altdrucker-Treiber, manche Fachanwendungen der Justiz): extrahierter Text ist Zeichensalat, die Erkennung findet keinen Namen, die Seite zeigt ihn klar.
- **Text als Vektorpfade** (Briefköpfe aus Grafikprogrammen, "Text in Kurven", manche Druck-PDF-Erzeuger): keine Textebene, aber sichtbarer Name.
- **Bilder mit Text in Text-PDFs** (eingebettete Ausweiskopie, eingescannte Anlage, Screenshot, Unterschrift als Bild, Eingangsstempel): Born-digital-Dokument, aber PII nur im Bild.
- **Unsichtbarer Text**: Render-Modus 3 (alte OCR-Ebene), weißer Text, Text außerhalb der CropBox, Text unter Bildern, Text in ausgeschalteten optionalen Inhaltsebenen (OCG `/OFF`). Die Erkennung findet ihn vielleicht, der Prüfer sieht ihn auf dem Seitenbild nicht und lehnt den "Phantomfund" ab, oder die Erkennung findet ihn nicht und er bleibt in der Datei.
- **Ligaturen, weiche Trennstriche, NBSP, Nullbreitenzeichen**: "Schiffer" mit U+FB00-Ligatur, "Mül\u00ADler", "Herr\u00A0Müller", Homoglyphen aus Copy-Paste. Regex und Namensweitergabe greifen nicht.
- **Lesereihenfolge**: Tabellen und Mehrspaltensatz trennen Kontextwort und Wert ("geb." in einer Zelle, Datum in der nächsten); pdfminer, pypdf und PyMuPDF liefern unterschiedliche Reihenfolgen.

**Why it happens:**
Erkennung arbeitet auf extrahiertem Text, der Mensch auf dem Seitenbild. Niemand prüft, ob beide dasselbe zeigen.

**How to avoid:**
- **Zweiter Erkennungskanal im gründlichen Modus: jede Seite rendern und OCR laufen lassen**, auch bei Text-PDFs. OCR-Text mit Textebene vergleichen (Zeichenübereinstimmung je Zeile); bei Abweichung über Schwelle Seite als "Textebene unzuverlässig" markieren und Erkennung auf OCR-Text stützen.
- Bilder in Text-PDFs immer OCRen; Seiten mit großem Vektoranteil und wenig Text als Verdachtsseiten markieren.
- Unsichtbare Inhalte vor der Erkennung entfernen oder sichtbar machen: OCGs auflösen (ausgeschaltete Ebenen entfernen), Inhalte außerhalb der CropBox entfernen, Render-Modus-3-Text verwerfen (wird ohnehin neu geOCRt), weißen Text als Fund "verborgener Text" anzeigen.
- Normalisierung mit Offset-Abbildung: NFKC, Ligaturen auflösen, U+00AD/U+200B/U+FEFF entfernen, NBSP zu Leerzeichen; Rückabbildung auf Zeichen-Bboxen muss erhalten bleiben.
- Erkennung pro Zeile **und** pro Block laufen lassen, Kontextregeln auch über Tabellenzellen (Zeile links/rechts, Zelle darüber).

**Warning signs:**
Seite mit vielen sichtbaren Wörtern und wenig extrahiertem Text; hoher Anteil von U+FFFD oder `(cid:N)`; Funde, deren Bbox auf leerem Seitenbild liegt; Prüfer lehnt viele Funde mit "steht da nicht" ab.

**Phase to address:** P-Extraktion (Kanalvergleich, Normalisierung), P-Erkennung, P-Prüf-UI (Hinweis "verborgener Text").

---

### Pitfall 5: Scans: OCR-Koordinaten, Rotation, MRC-Schichten und verfälschte Ziffern

**What goes wrong:**
- **Koordinatenfehler**: OCR auf entzerrtem oder gedrehtem Bild (Deskew, OSD), Schwärzungsrechteck aber auf dem Originalbild; oder `/Rotate 90` plus CropBox-Versatz falsch umgerechnet. Ergebnis: Balken neben dem Namen, Name lesbar, Nachprüfung per Text sauber (weil alte Textebene verworfen und neue OCR den teilweise verdeckten Namen nicht mehr liest).
- **Alte Scanner-OCR-Ebene als Koordinatenquelle**: Scanner-OCR ist oft versetzt; wer ihre Bboxen nutzt, schwärzt daneben.
- **Zu enge Boxen**: OCR-Wortboxen schneiden Ober- und Unterlängen und Kantenglättung ab; Reste reichen zum Lesen.
- **MRC-Schichtung**: Hochkomprimierende Scan-PDFs (Scanner, ABBYY, Kofax) zerlegen eine Seite in Hintergrund-JPEG, Vordergrundfarbe und **Text als Bitmaske** (JBIG2/CCITT als `/Mask` oder `/SMask`). Pixel-Schwärzung des Hintergrundbilds lässt die Textmaske unberührt [Test nötig für PyMuPDF].
- **Mehrere Bildkacheln pro Seite**, Bild-Stapel, Bilder mit Farbschlüssel-Maske.
- **Verlustbehaftetes JBIG2 (Pattern Matching and Substitution)**: Symbole werden zwischen ähnlichen Zeichen vertauscht (Xerox-Fall 2013) [belegt: Wikipedia JBIG2, Substitutionsfehler]. Folge für uns: IBAN, Steuer-ID, RV-Nummer haben im Scan eine falsche Ziffer, **Prüfziffer schlägt fehl, Erkenner verwirft den echten Fund**. Gleiches bei OCR-Verwechslungen (O/0, l/1/I, S/5, B/8).
- **Was OCR nicht sieht**: Handschrift (Randnotizen, Unterschriften mit Namenszug), Stempel (Eingangsstempel mit Bearbeiternamen), Faxkopfzeilen in kleiner Schrift auf jeder Seite, gedrehte Seiten ohne OSD-Daten (Tesseract `osd.traineddata` fehlt oft), niedrige Auflösung unter 200 dpi.
- **Dateigröße**: PyMuPDF speichert das neue PNG bei Pixel-Schwärzung derzeit unkomprimiert [belegt]; 300-dpi-Scans wachsen stark, ohne `deflate` beim Speichern explodiert die Ausgabe.

**Why it happens:**
Der Spike hat Scans nicht gemessen [Spike 7]. Synthetische Testdaten sind gerade, sauber und ohne Handschrift.

**How to avoid:**
- Eine **einzige Koordinatenquelle**: eigenes OCR auf dem gerenderten Seitenbild in genau der Geometrie, in der geschwärzt wird; jede Transformation (Deskew, Rotation, CropBox, `/UserUnit`) als Matrix speichern und rückrechnen; Rundweg-Test (Box auf Bild zeichnen, wieder einlesen).
- Boxen um feste Pixelzahl plus Prozentsatz der Zeilenhöhe erweitern.
- MRC erkennen (Seite mit mehreren Bildern oder Bild mit `/Mask`/`/SMask`) und im Zweifel die Seite **vor** der Schwärzung zu einem Bild flach rendern.
- Für Scans: ID-Erkenner mit Prüfziffer **zusätzlich** ohne Prüfziffer als "niedrige Konfidenz" laufen lassen; OCR-Verwechslungstabelle für Ziffernfelder.
- Pflicht in der Prüf-UI bei Scans: jede Seite visuell bestätigen ("Seite geprüft"), Flächenschwärzung prominent; Hinweis "Handschrift und Stempel werden nicht erkannt".
- Tesseract mit `deu`, `eng`, `fra` und `osd` ausliefern; Auflösungsprüfung mit Warnung unter 200 dpi.
- Nachprüfung für Scans: Ausgabe rendern, OCR, und **Pixelprüfung**: unter jedem Schwärzungsrechteck plus Rand dürfen keine Nicht-Balken-Pixel liegen.

**Warning signs:**
Schwärzungsbalken visuell leicht versetzt; Funde auf gedrehten Seiten mit wenigen Treffern; IBAN-Erkennung auf Scans deutlich schlechter als auf Text; Ausgabedatei 10-mal größer als das Original.

**Phase to address:** P-Extraktion (OCR, Geometrie), P-PDF (MRC, Pixelprüfung), P-Erkennung (Scan-Fallback ohne Prüfziffer), P-Prüf-UI, P-Testsatz (echte Scans aus Scannern verschiedener Hersteller).

---

### Pitfall 6: DOCX: Text steht an viel mehr Orten als in `w:t` (doppelte Kopien, Daten-Caches, Wiederbefüllung)

**What goes wrong:**
Über die vom Spike behandelten Orte hinaus (Änderungen, Kommentare, verborgener Text, Kopf/Fuß, Metadaten, Vorschaubild, mailto) [Spike 5.3]:
- **Textfelder doppelt**: DrawingML-Textfelder stehen in `mc:AlternateContent` als `mc:Choice` (wps) **und** `mc:Fallback` (VML `v:textbox`). Wer nur die erste Kopie schwärzt, lässt die zweite stehen; ältere Leser (und LibreOffice in manchen Fällen) zeigen die Fallback-Kopie [Fachwissen].
- **SmartArt**: Text in `word/diagrams/data*.xml` **und** als vorgerenderte Form in `drawing*.xml`.
- **Diagramme**: `word/charts/chart*.xml` mit `c:strCache`/`c:numCache` plus eingebettete Arbeitsmappe `word/embeddings/*.xlsx` mit der vollen Datentabelle (z. B. Namensliste hinter einem Balkendiagramm).
- **OLE-Objekte**: `word/embeddings/oleObject*.bin` oder eingebettete xlsx/docx (vollständige Dokumente, rekursiv) plus EMF/WMF-Vorschaubild in `word/media`.
- **Felder mit Zwischenergebnis**: `w:instrText` (Anweisung, z. B. `HYPERLINK "mailto:..."`, `INCLUDEPICTURE "C:\\Users\\kmueller\\..."`, `MERGEFIELD`, `DOCPROPERTY Bearbeiter`) und das Ergebnis zwischen `separate` und `end`; `w:fldSimple`. `w:dirty="true"` oder eine Feldaktualisierung beim Rendern (LibreOffice) kann Text aus einer Quelle neu einsetzen, die nicht bereinigt wurde [Test nötig].
- **Inhaltssteuerelemente mit Datenbindung**: `w:sdt` mit `w:dataBinding` auf `customXml/item*.xml`. Word zeigt beim Öffnen die Werte aus dem Custom-XML-Teil an [belegt: Microsoft-Doku "When you open the document, the content controls display the values of the XML elements"]. Wird nur der sichtbare Text geschwärzt und customXml bleibt, **setzt Word den Namen beim Öffnen wieder ein**. Der Spike entfernt `customXml/` bereits, aber die `w:dataBinding`-Verweise und `w:placeholder`/Glossar-Platzhalter müssen mit.
- **Glossar**: `word/glossary/document.xml` (Bausteine, AutoText) mit Vorlagen voller Namen und Anschriften.
- **Weitere Textknoten**: `m:t` (Formeln, OMML), `w:delText`, `w:sym`, Ruby-Text, `v:textpath string=` (WordArt), Alternativtexte `wp:docPr/@descr` und `@title`, Bildnamen `wp:docPr/@name`, Textmarkennamen `w:bookmarkStart/@w:name`, Hyperlink-Anker `w:hyperlink/@w:anchor`, Kommentar-Erweiterungen (`commentsExtended.xml`, `commentsIds.xml`, `commentsExtensible.xml`), `w:author` an Änderungen.
- **Kopf- und Fußzeilen je Abschnitt**: erste Seite (`w:titlePg`), gerade Seiten (nur sichtbar mit `w:evenAndOddHeaders` in `settings.xml`). Ist die Einstellung aus, existiert die Fußzeile trotzdem in der Datei, wird aber **nie angezeigt**: der Prüfer sieht sie nie.
- **Einstellungen und Beziehungen**: `settings.xml` mit `w:attachedTemplate` (Pfad mit Windows-Benutzername), `w:mailMerge` (Datenquelle, SQL-Abfrage), `w:rsids` und `w:rsid*` an jedem Absatz (Sitzungskennungen, verknüpfen Bearbeitungsstände über Dokumente hinweg); `webSettings.xml`; `docProps/app.xml` (`Company`, `Manager`); `docProps/custom.xml`.
- **Bilder**: EXIF/XMP in JPEGs unter `word/media` (Autor, Kamera-Seriennummer, GPS, **EXIF-Vorschaubild des unbeschnittenen Originalbilds**); Beschnitt per `a:srcRect` lässt den abgeschnittenen Bildteil in der Datei.
- **Makros**: `vbaProject.bin`, `vbaData.xml` (bei `.docm`, aber auch bei umbenannten Dateien); Makrocode kann Namen enthalten und ist ein Sicherheitsrisiko.
- **Verwaiste Teile**: ZIP-Einträge ohne Beziehung, die Word ignoriert, die aber ausgeliefert werden.

**Why it happens:**
Bearbeitung über bekannte Teilnamen und `w:t` statt über "alles, was Text tragen kann". python-docx bildet viele dieser Teile gar nicht ab.

**How to avoid:**
- **Allowlist-Ansatz für das ZIP**: nur Teile übernehmen, die über `_rels` erreichbar und in einer Liste erlaubter Inhaltstypen sind; alles andere (Glossar, customXml, embeddings, vbaProject, people, comments*, Thumbnails, verwaiste Teile) entfernen und im Protokoll nennen.
- Textersetzung über **jeden Textknoten und jedes Textattribut** aller verbleibenden XML-Teile (generischer Durchlauf, nicht Elementliste), plus Attribute `descr`, `title`, `name`, `w:name`, `w:anchor`, `w:author`, `string`.
- `mc:AlternateContent`: Fallback entfernen oder beide Zweige gleich behandeln.
- Felder: Anweisung und Ergebnis schwärzen, Felder danach **in statischen Text umwandeln** (Feldklammern entfernen), `w:dirty` entfernen, `updateFields` in `settings.xml` entfernen.
- Diagramme und SmartArt in v1 in Bilder umwandeln (über LibreOffice-Rendering) oder entfernen mit Hinweis; OLE-Objekte entfernen und durch ihr bereinigtes Vorschaubild ersetzen oder melden.
- Bilder: alle Metadaten entfernen (neu kodieren), Beschnitt anwenden (Bild physisch zuschneiden).
- `rsid` entfernen, `settings.xml` auf Allowlist reduzieren.
- Alle Kopf-/Fußzeilen-Varianten bearbeiten **und** im Prüfdokument sichtbar machen (eigener Bereich "nicht angezeigte Kopf-/Fußzeilen").

**Warning signs:**
Leck-Zoo-Datei aus Word mit Textfeld, Diagramm oder Inhaltssteuerelement fehlt; ZIP der Ausgabe enthält Teile, die nicht in der Allowlist stehen; Ausgabe in Word geöffnet zeigt anderen Text als in LibreOffice.

**Phase to address:** P-Office, P-Testsatz (Leck-Zoo mit echten Word-Dateien, nicht python-docx-erzeugt), P-Nachprüfung (ZIP-Rohsuche über alle Einträge inkl. dekodierter Bilder-EXIF und eingebetteter ZIPs, rekursiv).

---

### Pitfall 7: ODT: bedingter, versteckter und automatisch befüllter Text

**What goes wrong:**
Über den Spike hinaus [Spike 5.3]:
- `text:conditional-text` speichert **beide** Zweige (`text:string-value-if-true`/`-if-false`); `text:hidden-text` und `text:hidden-paragraph` mit Bedingung; Bereiche mit `text:display="none"` oder Bedingung.
- Felder: `text:user-field-decls` (Wert in der Deklaration), `text:variable-set`, `text:author-name`, `text:sender-*` (Absenderfelder werden beim Rendern aus dem **LibreOffice-Benutzerprofil des Containers** gefüllt, wenn nicht fixiert).
- Eingebettete Objekte: `Object 1/` (eigenes `content.xml`), `ObjectReplacements/` (Vorschaubild), Diagrammdaten in eingebetteten Objekten.
- Bilder: `svg:title`, `svg:desc`, `draw:name`, Bild-EXIF in `Pictures/`.
- `settings.xml`: Druckername, Ansichtseinstellungen, teils Pfade; `meta.xml` mit `meta:user-defined`, `meta:editing-cycles`, `meta:print-date`, `meta:printed-by`.
- Textmarken- und Verweisnamen, Fußnoten (`text:note` inline), Notizen der Präsentationsansicht (bei ODT selten, bei Folgeformaten relevant).

**How to avoid:**
Wie Pitfall 6: Allowlist der ZIP-Einträge, generischer Textknoten- und Attributdurchlauf über `content.xml`, `styles.xml`, `meta.xml`, `settings.xml` und eingebettete Objekte (rekursiv); bedingte Inhalte entfernen oder in den sichtbaren Zweig auflösen; Felder in Text wandeln.

**Warning signs:**
Text-Export von LibreOffice und odfpy unterscheiden sich in der Länge deutlich; Leck-Zoo ohne bedingten Text.

**Phase to address:** P-Office, P-Testsatz.

---

### Pitfall 8: Die Ausgabe wird in Nextcloud sichtbar, bevor sie freigegeben ist, und Altstände bleiben über Versionen erhalten

**What goes wrong:**
- **Ablage neben dem Original erbt Freigaben**: Liegt das Original in einem per Link oder mit Gruppen geteilten Ordner (typisch: Ordner "IFG-Antrag 2026-123" mit dem Antragsteller oder einer anderen Behörde geteilt), ist jede Datei dort **sofort** für alle Freigabeempfänger sichtbar. Eine Zwischen- oder Entwurfsausgabe ist damit herausgegeben, bevor die Vier-Augen-Freigabe erfolgt ist.
- **Versionen**: Nextcloud legt bei jeder Änderung einer Datei automatisch eine neue Version an; benannte Versionen werden nie gelöscht; Aufbewahrung standardmäßig stündlich am ersten Tag, täglich 30 Tage, danach wöchentlich [belegt: Nextcloud Admin Manual "Controlling file versions and aging"]. Überschreibt die App beim zweiten Lauf `Bescheid_geschwärzt.pdf`, bleibt der erste (vielleicht unvollständige) Stand als Version abrufbar, für alle mit Zugriff.
- **Nutzer überschreibt das Original mit der geschwärzten Fassung** (häufiger Arbeitsablauf "jetzt teilen"): Die Klartextfassung lebt als Version weiter und ist für Empfänger mit Bearbeitungsrecht wiederherstellbar.
- **Papierkorb**: Gelöschte Dateien bleiben standardmäßig mindestens 30 Tage [belegt: Admin Manual Data retention]; in Gruppenordnern ist der Papierkorb für Gruppenmitglieder sichtbar; löscht ein Freigabeempfänger, landet die Datei beim Besitzer im Papierkorb.
- **Volltextsuche und Findling**: Jede Datei, die die App in den Nutzerspeicher schreibt (Zwischenstände, JSON-Prüfzustand als Datei, temporäre PDFs), wird von Findling oder `files_fulltextsearch` indexiert und versioniert; der Index wird verzögert aktualisiert und kann den Klartext länger halten als die Datei.
- **Aktivität und Benachrichtigungen**: Dateinamen mit Personenbezug erscheinen im Aktivitätsstrom aller Freigabeempfänger; Benachrichtigungstexte mit Fundausschnitten ("3 Funde, u. a. Müller") landen in Push-Diensten (Nextcloud-Push-Proxy über externe Dienste).
- **Vorschauen**: Vorschaubilder werden bei Bedarf erzeugt und unter `appdata_*/preview` abgelegt; eigene gerenderte Seitenbilder der Prüfseite dürfen nicht unter Pfaden landen, die ohne Rechteprüfung ausgeliefert werden.

**Why it happens:**
"Kopie neben dem Original" ist bequem, aber Nextcloud-Ordner sind Freigabe-Einheiten. Versions- und Papierkorb-Apps arbeiten unabhängig von der App.

**How to avoid:**
- **Ausgabe erst nach Freigabe schreiben**; bis dahin bleibt alles im App-Speicher (Datenbank plus ExApp-Volume) und wird nur über die Prüfseite gerendert.
- Vor dem Schreiben prüfen, ob der Zielordner geteilt ist (Link, Gruppe, Föderation); dann Rückfrage "Zielordner ist geteilt mit ... ; trotzdem dort ablegen?" oder anderen Zielordner wählen lassen.
- **Nie überschreiben**: jeder Lauf erzeugt einen neuen Dateinamen (`_geschwärzt (2)`); falls doch ein Ersetzen nötig wird, danach die Versionen dieser Datei über die Versions-API löschen [Test nötig: verfügbare API je Nextcloud 33 bis 35].
- In der UI deutlich warnen, das Original nicht durch die Schwärzung zu ersetzen; Hilfetext zu Versionen und Papierkorb.
- Keine Zwischenstände in den Nutzerspeicher; Prüfzustand nie als Datei.
- Dateinamen-Prüfung (schon geplant) auch auf den **Ordnerpfad** ausdehnen; Benachrichtigungen ohne Fundinhalt, nur "Analyse fertig".
- Seitenbilder der Prüfseite nur über eine PHP-Route mit Rechteprüfung je Anfrage ausliefern, mit `Cache-Control: no-store`.

**Warning signs:**
Ausgabedatei erscheint in einem Ordner, bevor der Status "freigegeben" gesetzt ist; Versionsliste einer Ausgabe hat mehr als einen Eintrag; Findling-Suche nach einem geschwärzten Namen liefert einen Treffer in einer App-Datei.

**Phase to address:** P-Nextcloud (Schreibzeitpunkt, Freigabeprüfung, kein Überschreiben), P-Gerüst (Speicherorte), P-Prüf-UI (Hinweise), P-Release (Integrationstest mit Findling und Versions-App).

---

### Pitfall 9: Rechteprüfung nur beim Start des Auftrags (Gruppenordner-ACL, Freigaben, ExApp als beliebiger Nutzer)

**What goes wrong:**
- Der Auftrag wird mit den Rechten des Startenden angelegt; später entzieht ein Admin per Gruppenordner-ACL das Leserecht für einen Unterordner, oder eine Freigabe läuft ab. Die Prüfseite zeigt den Klartext trotzdem weiter an.
- Die zweite Person der Vier-Augen-Freigabe hat **keinen** Zugriff auf das Original, sieht aber über die Prüfseite den vollen Klartext.
- Freigabeempfänger mit "nur Lesen" oder Datei-Drop-Ordner: Ausgabe kann nicht neben dem Original abgelegt werden; die App fällt stumm auf das Nutzer-Stammverzeichnis zurück oder scheitert ohne Grund.
- Die ExApp greift über AppAPI im Namen beliebiger Nutzer zu. Ein Fehler in der Nutzerzuordnung (Auftrags-ID statt Nutzer-ID, fehlende Prüfung auf PHP-Seite) erlaubt das Lesen fremder Dateien.
- Ende-zu-Ende-verschlüsselte Ordner: Inhalt serverseitig nicht lesbar; ohne Erkennung entstehen kryptische Fehler.
- Sperren: Die Datei wird während der Analyse in Collabora oder OnlyOffice bearbeitet. Die Offsets der Funde beziehen sich auf einen alten Stand; die Schwärzung trifft falsche Stellen.

**How to avoid:**
- Rechteprüfung **bei jeder Anfrage** der Prüfseite gegen die aktuelle Sicht des Nutzers (`IRootFolder::getUserFolder($uid)` und Knotenrechte), nicht gegen gespeicherte Rechte.
- Vier-Augen: zweite Person muss selbst Leserecht auf das Original haben; Selbstfreigabe (gleicher Nutzer, auch über Zweitkonto mit gleicher E-Mail ist nicht verhinderbar, aber gleiche UID schon) sperren.
- Auftrag an **Datei-ID plus ETag** binden; vor dem Schwärzen ETag erneut prüfen, bei Änderung neu analysieren; während des Schreibens die Ausgabe sperren.
- E2EE-Ordner und externe Speicher ohne Versionierung erkennen und mit klarem Grund ablehnen bzw. warnen.
- Zielordner-Logik mit explizitem Rückfall und Meldung, nie stumm.

**Warning signs:**
Prüfseiten-Endpunkte ohne Rechteprüfung im Code; Tests nur mit Admin-Konto; kein Testfall "ACL nachträglich entzogen".

**Phase to address:** P-Gerüst (Auftragsmodell mit Datei-ID/ETag), P-Nextcloud, P-Prüf-UI (Vier-Augen-Regeln), P-Release (Negativtests mit Gruppenordner-ACL, Freigaben, E2EE).

---

### Pitfall 10: Prüfzustand, Protokoll und Logs werden selbst zum Leck

**What goes wrong:**
- **Fundtexte in der Datenbank**: Der Prüfzustand mit Klartext-PII landet in `oc_*`-Tabellen und damit in **jeder Datenbanksicherung**, oft jahrelang; Löschen in der App löscht die Backups nicht.
- **Hashes im Protokoll sind keine Anonymisierung**: Das geplante Protokoll enthält Hashes. Ein ungesalzener SHA-256 einer Steuer-ID, IBAN, eines Geburtsdatums oder eines Nachnamens ist per Wörterbuch- oder Vollsuche in Sekunden umkehrbar (Steuer-IDs haben rund 10^10 Kandidaten, Nachnamen ein paar Hunderttausend). Hashes einzelner Funde im Protokoll sind damit ein Leck mit Rechtsfolge.
- **Logs**: Python-Tracebacks mit lokalen Variablen oder Fehlermeldungen mit Textausschnitten (Presidio, spaCy, GLiNER-Warnungen "Sentence of length N has been truncated" mit Satz), FastAPI-Zugriffslogs mit Anfrageinhalt, ExApp-Logs, die über AppAPI in `nextcloud.log` landen, Docker-Logs, Crash-Dumps von LibreOffice, Tesseract-Debugdateien.
- **Temporäre Dateien**: Seitenbilder, OCR-hOCR, LibreOffice-Konvertierungen in `/tmp` des Containers bleiben nach Abstürzen liegen; Volumes werden nie geleert.
- **Pseudonym-Zuordnungstabelle** ("Person A = Müller") ist die "zusätzliche Information" im Sinne von Art. 4 Nr. 5 DSGVO; liegt sie neben der Ausgabe oder im Protokoll, ist die Pseudonymisierung wertlos.
- **Besondere Kategorien (Art. 9) und Strafdaten (Art. 10 DSGVO)**: Die App verarbeitet sie zwangsläufig im Prüfzustand; die Behörde braucht dafür Verzeichnis und ggf. Datenschutz-Folgenabschätzung.

**How to avoid:**
- Im Prüfzustand **keinen Klartext speichern**: nur Datei-ID, ETag, Offsets/Bboxes, Kategorie, Konfidenz, Entscheidung. Den Text zur Anzeige zur Laufzeit aus dem Original lesen (der Nutzer hat ohnehin Zugriff). "Für alle gleichen Funde" über einen HMAC mit **pro Auftrag zufälligem Schlüssel** lösen, Schlüssel nur im Speicher bzw. mit dem Auftrag löschen.
- Protokoll: Hashes nur über **ganze Dateien** (Original, Ausgabe); pro Fund nur Kategorie, Seite, Position, Rechtsgrundlage, Prüfer. Keine Hashes einzelner Werte.
- Feste Lebensdauer für Prüfzustand und Temporärdateien (z. B. 14 Tage nach Freigabe, admin-einstellbar), Hintergrundjob zum Löschen, `occ`-Befehl zum sofortigen Löschen; temporäre Dateien in `tmpfs` bzw. je Auftrag eigenes Verzeichnis mit Aufräumen im `finally` und beim Start.
- Logging mit **Allowlist strukturierter Felder** (Auftrags-ID, Phase, Dauer, Fehlerklasse); nie Text, nie Exception-Nachrichten von Drittbibliotheken ungefiltert; Warnungen von GLiNER/transformers abfangen. **CI-Test mit Kanarienwert**: Lauf über ein Dokument mit Kanarie, danach alle Logs, die Datenbank und das Volume auf die Kanarie durchsuchen.
- Pseudonym-Zuordnung standardmäßig nicht speichern; falls Rückführung gewünscht, getrennt, verschlüsselt, mit eigener Löschfrist und eigenem Recht.
- Mustertexte für Verzeichnis (Art. 30) und DSFA-Bausteine in der Admin-Doku.

**Warning signs:**
Spalten wie `text`, `value`, `snippet` in der Migration; `logger.exception` in Erkennungscode; Protokoll-JSON mit `sha256` je Fund.

**Phase to address:** P-Gerüst (Datenmodell, Logging-Regeln), P-Protokoll, P-Pseudo (Zuordnungstabelle), P-Release (Kanarien-Scan).

---

### Pitfall 11: Bösartige Dokumente übernehmen die ExApp (und damit alle Nutzerdateien)

**What goes wrong:**
Behörden bekommen Dokumente von außen (Bürgerbriefe, Anlagen). Die ExApp parst sie mit MuPDF, pypdf, pdfminer, lxml, LibreOffice und Tesseract. Die ExApp hält das AppAPI-Geheimnis und kann **im Namen jedes Nutzers** Dateien lesen und schreiben. Eine Codeausführung oder Dateilesen im Parser ist damit ein Zugriff auf die ganze Nextcloud.
- **XXE und Entitäten**: lxml expandiert seit 5.0 keine externen Entitäten im normalen Parser, aber `iterparse()` und `ETCompatXMLParser()` taten es bis lxml 6.1.0 weiter (CVE-2026-41066, lokales Dateilesen, CVSS 7,5) [belegt]. Interne Entitäten (Billion Laughs) werden weiter expandiert.
- **ZIP-Bomben und ZIP-Tricks**: hohe Kompressionsrate, viele Einträge, verschachtelte ZIPs (eingebettete docx in docx), **doppelte Eintragsnamen** (Python `zipfile` nimmt einen, Word oder LibreOffice einen anderen: der Schwärzer bereinigt eine andere `document.xml` als die, die gerendert wird), Pfade mit `../`.
- **PDF-Bomben**: Flate-Bomben, riesige Bilddimensionen, tief verschachtelte Arrays, zyklische Seitenbäume oder XObjects, Millionen Objekte. pypdf hatte 2025/2026 eine Reihe von DoS-CVEs zu FlateDecode (CVE-2025-55197, CVE-2026-27026, CVE-2026-41312, CVE-2026-41314, CVE-2026-27888) [belegt über Aggregatoren, Versionsgrenzen in NVD/GitHub prüfen]. pdfminer.six ist auf manchen Dateien sehr langsam.
- **LibreOffice**: Makros (Basic, Python), Ereignisbindungen, mitgelieferte Python-Makros mit Ausnahme von der Makrosicherheit (CVE-2018-16858, LibreLogo CVE-2019-9848/9850/9855) [belegt über Vortrag IT-SECX 2019]. **Externe Ressourcen beim Konvertieren**: LibreOffice lädt verlinkte Bilder und Objekte selbst per HTTP (eigener libcurl-Zugriff, an Proxy-Filtern vorbei) und kann lokale Dateien als Bildquelle einbinden; Gotenberg-CVEs 2026 (CVE-2026-42591, CVE-2026-55229) zeigen SSRF und Lesen lokaler Dateien über DOCX mit `TargetMode="External"` [belegt]. Folge bei uns: Ausgabe-PDF enthält Inhalte aus dem Container oder dem internen Netz, oder Anfragen an Angreifer-URLs verraten, dass und wann die Behörde das Dokument verarbeitet. DDE-Felder (`DDEAUTO`) und verknüpfte Abschnitte sind weitere Wege.
- **Tesseract/Leptonica** auf manipulierten Bildern (Speicher, Laufzeit).

**How to avoid:**
- **Parser-Sandbox**: jede Datei in einem Unterprozess ohne Netzwerk (eigener Netz-Namespace, z. B. `unshare -n` oder bubblewrap, falls im ExApp-Container möglich [Test nötig: Rechte unter HaRP/Docker]), ohne AppAPI-Geheimnis in der Umgebung, mit `RLIMIT_AS`, CPU-Zeitlimit, Wanduhr-Timeout, Schreibrecht nur im Auftragsverzeichnis, als unprivilegierter Nutzer.
- XML: eigener Parser mit `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`; Dokumente mit `<!DOCTYPE` ablehnen (OOXML und ODF brauchen keine DTD); lxml mindestens 6.1.0 pinnen.
- ZIP: vor dem Entpacken Summe der unkomprimierten Größen, Rate, Eintragszahl, Verschachtelungstiefe begrenzen; doppelte Namen, absolute Pfade und `..` ablehnen; Groß-/Kleinschreibungs-Duplikate ablehnen.
- PDF: Seitenzahl-, Objektzahl-, Bildpixel- und Stream-Größen-Grenzen; `qpdf --check` bzw. pikepdf-Öffnung als Vorprüfung mit Timeout; Bibliotheken auf gepinnte, gepatchte Versionen.
- LibreOffice: externe Beziehungen und verknüpfte Objekte **vor** der Übergabe entfernen; Makrosicherheit über Profil-Registry auf "sehr hoch" setzen und Makros aus der Datei vor der Konvertierung entfernen; Konvertierung ohne Netzwerk; eigenes Profil je Lauf.
- Fuzzing-Korpus bösartiger Dateien in CI (bekannte Bomben, XXE, doppelte ZIP-Namen, externe Rels).

**Warning signs:**
Parser laufen im Hauptprozess der ExApp; Umgebung des Parsers enthält `APP_SECRET`; LibreOffice-Prozess hat Netzwerk; kein Testfall mit Bombe.

**Phase to address:** P-Eingang (vor jeder Format-Phase), P-Office (LibreOffice-Härtung), P-Release (Sicherheitsaudit, Negativtests; Owner-Regel "Security-Teile höchste Sorgfalt").

---

### Pitfall 12: Pseudonymisierung verrät mehr als gedacht

**What goes wrong:**
- **Deterministische Pseudonyme über Dokumente**: Wer dieselbe Person in allen Dokumenten gleich benennt (oder Pseudonyme aus einem Hash des Namens ableitet), ermöglicht Verknüpfung über Dokumente und mit Hashes ohne Geheimnis die Rückrechnung über Namenslisten.
- **Pseudonym aus dem echten Anfangsbuchstaben** ("Müller" -> "M."): verbreitete Gerichtspraxis, reduziert aber den Suchraum stark; zusammen mit Ort und Beruf oft eindeutig.
- **Quasi-Identifikatoren bleiben**: Wohnort, Beruf, Arbeitgeber, Alter, seltene Ereignisse, Familienkonstellation. Pseudonymisierte Daten bleiben personenbezogen (Art. 4 Nr. 5 DSGVO); der EuGH hat in C-413/23 P (EDSB/SRB, 04.09.2025) die Identifizierbarkeit aus dem Kontext beurteilt, das ändert nichts daran, dass beim Verantwortlichen der Personenbezug bleibt [belegt über Fachkommentare, Volltext prüfen]. Wer die Ausgabe "anonymisiert" nennt, verspricht zu viel.
- **Deutsche Grammatik**: Genitiv "Müllers Antrag", "des Herrn Müller", "Herrn" statt "Herr", Familienplural "die Müllers", adjektivische Ableitungen "Müller'sche"/"Müllersche Grundstück", Bindestrichkomposita "Müller-Klage". Ersetzung "Person A" erzeugt "Person As Antrag" oder lässt "-sche" stehen. Französisch: Elision "d'Alpha" vs "de Bernard", "l'"; Englisch "Smith's".
- **Geschlecht**: Pronomen und Artikel ("der Zeuge", "sie") werden nicht ersetzt. Ein Pseudonym mit anderem Geschlecht macht den Text widersprüchlich; ein gleichgeschlechtliches Pseudonym aus einer Namensliste (Faker-artig "Hans Schmidt") kann mit realen Personen kollidieren und Leser in die Irre führen.
- **Schreibvarianten derselben Person**: "Müller", "Mueller" (E-Mail-Adressen, Dateinamen, URLs), "MÜLLER" (Kopfzeilen), "Muller" (OCR), "k.mueller@..."; Namensweitergabe greift nur auf die exakte Form.
- **Namen, die Wörter sind**: Koch, Bauer, Fischer, Schmidt, Wolf, Fuchs, Becker, Richter, Kaiser. Namensweitergabe markiert dann "der Koch", "die Bauern", "Richter am Amtsgericht" (Überschwärzung) oder die Regel nimmt sie aus (Leck). Straßen nach Personen ("Goethestraße") und Firmen mit Personennamen.
- **Initialen-Kollision**: bekannt [Spike 6, 73 %]; zusätzlich: bei Unsicherheit darf der Clusterer **nicht raten**, sonst bekommen zwei Personen dasselbe Pseudonym (Datenfehler im veröffentlichten Urteil) oder eine Person zwei.
- **PDF-Ersetzungstext**: PyMuPDF unterstützt für den Ersetzungstext nur Base-14- und CJK-Fonts; längerer Ersatz kann zu Umbruch, abgeschnittenem oder **gar keinem** neuen Text führen [belegt, PyMuPDF-Doku]. Ein fehlendes Pseudonym ist datenschutzmäßig harmlos, macht aber das veröffentlichte Urteil unlesbar, und niemand merkt es.
- **Längenleck**: Pseudonym fester Länge ist gut; Balken mit Ursprungslänge verrät die Namenslänge (siehe PoPETs 2023, schon bekannt).

**How to avoid:**
- Pseudonyme **pro Dokument zufällig** (bzw. pro Vorgang, wenn mehrere Dokumente gemeinsam veröffentlicht werden, als bewusste Option); nie aus Hash oder echtem Anfangsbuchstaben ableiten; Schema mit Rolle ("Klägerin K1", "Zeuge Z2") statt Fantasienamen.
- Flexionsregeln je Sprache als eigene, getestete Komponente: Genitiv-s, "Herrn", "-sche", Bindestrich, Elision; Ersatztext grammatisch passend erzeugen ("der Klägerin K1").
- Geschlecht aus Anrede übernehmen, sonst neutrales Schema; keine realistischen Fantasienamen.
- Variantenabgleich: Transliteration (ü/ue, ß/ss), Groß-/Kleinschreibung, Diakritika, OCR-Verwechslungen; E-Mail-Lokalteile gegen Namen prüfen.
- Gazetteer "Namen, die Wörter sind": Weitergabe nur mit Großschreibung plus Anrede- oder Namenskontext, sonst Konfidenz "niedrig".
- Unklare Zuordnung als eigener Fund "Zuordnung prüfen" in der UI.
- Nach dem Schreiben prüfen, dass jedes Pseudonym im Ausgabetext tatsächlich steht (Positivprüfung neben der Leckprüfung).
- UI-Text und Doku: "pseudonymisiert", nie "anonymisiert"; Hinweis auf Quasi-Identifikatoren.

**Warning signs:**
Ausgabetexte mit "Person As"; zwei Personen im selben Cluster in der Testauswertung; Pseudonyme fehlen in der PDF-Ausgabe; gleiche Pseudonyme in unabhängigen Dokumenten.

**Phase to address:** P-Pseudo, P-Erkennung (Varianten, Wort-Namen), P-PDF (Ersatztext und Font), P-Testsatz (Flexionsfälle DE/EN/FR).

---

### Pitfall 13: Amtsträger und Rechtsgrundlagen: eine Regel, die nach Rechtssicherheit aussieht

**What goes wrong:**
- Bekannt: Amtsträger-Regel nimmt Privatpersonen aus [Spike 6]. Neu und rechtlich tiefer:
- **"Bearbeiter" ist eng**: Nach BVerwG 7 C 27/15 sind Bearbeiter im Sinne von § 5 Abs. 4 IFG nur Bedienstete, die mit dem konkreten Verwaltungsvorgang befasst waren [belegt über Leitsatz-Wiedergabe, Volltext prüfen]. Andere Bedienstete im selben Dokument (Verteiler, Vorgesetzte, Mitarbeiter anderer Behörden, Externe) fallen unter die Abwägung nach § 5 Abs. 1 und ggf. die Drittbeteiligung nach § 8 IFG. Eine Regel "Rollenwort = Amtsträger = nicht schwärzen" ist deshalb in beide Richtungen falsch.
- § 5 Abs. 4 erfasst nur bestimmte Angaben (Name, Titel, akademischer Grad, Berufs- und Funktionsbezeichnung, Büroanschrift und -telefonnummer) und nur, soweit sie Ausdruck und Folge der amtlichen Tätigkeit sind; private Anschrift oder Mobilnummer einer Amtsträgerin sind nicht erfasst [Fachwissen, Gesetzestext].
- **Landesrecht weicht ab** (Transparenzgesetze Hamburg, Rheinland-Pfalz, Berlin; IFG NRW; Länder ohne IFG), Gerichtsentscheidungen folgen eigenen Anonymisierungsrichtlinien (Richternamen meist nicht geschwärzt, Anwälte uneinheitlich). Ein fester Regelsatz "IFG Bund" verführt Landesbehörden zu falschen Labels.
- **Überschwärzung ist ein Rechtsfehler**, nicht nur Mehrarbeit (Teilablehnung muss begründet sein); **Unterschwärzung ist eine Datenpanne** (Art. 33 DSGVO, 72-Stunden-Meldung). Die UI darf keine der beiden Richtungen als "sicher" darstellen.
- **Art. 9 DSGVO**: Gesundheit, Religion, Gewerkschaft, Sexualleben, ethnische Herkunft stehen in Bescheiden oft als Fließtext ("aufgrund ihrer Depression"); Name geschwärzt, Diagnose stehen geblieben plus Ort und Datum führt zur Re-Identifikation besonders schutzwürdiger Daten. Die App erkennt das in v1 nicht (bewusst außer Scope), Nutzer könnten es aber annehmen.
- **Labels als Rechtsberatung**: Vorbelegte Rechtsgrundlagen werden ungeprüft übernommen; das Protokoll dokumentiert dann eine falsche Begründung mit Prüfernamen.

**How to avoid:**
- Amtsträger-Kategorie mit Unterscheidung "im Vorgang tätig (Bearbeiter)" vs. "sonstige Bedienstete" als Vorschlag; Voreinstellung wie geplant "bis zur Prüfung geschwärzt"; je Fund Pflichtentscheidung, kein Sammelannehmen über Amtsträger hinweg ohne Bestätigungsdialog.
- Private Kontaktdaten neben Amtsträgernamen immer als eigene Funde, nie mit ausgenommen.
- Rechtsgrundlagen-Sätze **je Rechtsrahmen** (Bund, Länder, Urteilsveröffentlichung) mit Admin-Auswahl beim Einrichten, kein stiller Standard; Hinweistext "keine Rechtsberatung".
- Art.-9-Hinweis in v1 als Wörterbuch-Markierung "besondere Kategorie, bitte prüfen" (schon als "höchstens Hinweis" im Scope), deutlich als unvollständig gekennzeichnet.
- Prüf-UI zeigt vor Freigabe eine Zusammenfassung "nicht geschwärzt: N Amtsträger, M Daten, ..." zur bewussten Bestätigung.

**Warning signs:**
Sammelaktion "alle Amtsträger annehmen" ohne Rückfrage; Rechtsgrundlagen-Standard "IFG Bund" bei einer Landesbehörde; Testsatz ohne Fall "Bedienstete anderer Behörde".

**Phase to address:** P-Erkennung (Kategorien), P-Prüf-UI, P-Protokoll (Rechtsgrundlagen-Sätze), P-Release (fachliche Abnahme mit einer Behörde, falls möglich).

---

### Pitfall 14: Evaluation misst das eigene Spiegelbild

**What goes wrong:**
Bekannt: gleicher Autor für Generator und Regeln, WikiNER-Kontamination bei spaCy-fr, nachträglich abgeleitete Filter [Spike 7]. Neu:
- **Überlappungs-Recall verdeckt Teillecks**: Im Spike zählt eine Spanne als gefunden, wenn **ein Zeichen** bedeckt ist [Spike 1.4]. "Müller-Lüdenscheidt" mit nur "Müller" geschwärzt gilt als gefunden. Die Leckrate (Zeichenebene) fängt das teilweise, aber Release-Gates auf Überlappungs-Recall wären gefährlich.
- **Zeichen-Leckrate verdeckt Dokument-Lecks**: 1,1 % der PII-Zeichen klingt gut; für eine IFG-Herausgabe zählt aber "Dokument mit mindestens einem ungeschwärzten Identifikator". Bei rund 23 Funden pro Dokument kann das ein großer Anteil der Dokumente sein.
- **Namensherkunft**: Faker de_DE erzeugt überwiegend deutschstämmige Namen; GLiNER-Trainingsdaten sind ebenfalls synthetisch (Mistral-erzeugt) [Spike 8.4]. In Behördenakten sind türkische, arabische, polnische, ukrainische (Transliteration), vietnamesische Namen häufig, oft mit mehreren Vornamen, Namenszusätzen, abweichender Reihenfolge. Recall-Unterschiede nach Herkunft bedeuten **ungleichen Schutz**; ungemessen bleibt das unsichtbar.
- **Text-Evaluation statt Ende-zu-Ende**: Erkennung auf sauberem JSONL-Text misst nicht Extraktionsfehler, Silbentrennung, Lesereihenfolge, OCR (Pitfall 4 und 5).
- **Schwellen und Regeln am Testsatz nachgezogen**: Jede Änderung nach Blick auf Testfehler verbraucht den Testsatz; ohne verdeckten Teil (Holdout) misst man nur noch Anpassung.
- **Modell-Updates und Architektur**: Andere torch- oder Modellversion, amd64 vs. arm64 (Gleitkomma, Threads) können Ergebnisse nahe der Schwelle 0,5 kippen; ohne Messung auf beiden Architekturen ist das Gate nur für eine gültig.
- **Korpora nicht im Repo** (Lizenz, richtige Entscheidung) heißt: CI kann das Gate nicht fahren, wenn es nur auf diesen Korpora basiert.
- **Mensch im Ablauf ungemessen**: Automatisierungsvertrauen; Prüfer klicken "alle annehmen" bei 23 Funden, 8 davon unnötig. Die echte Leckrate ist Erkennung **plus** Prüferverhalten.
- **Zielmaterial fehlt**: FAU/ALeKS-Goldstandard ist angefragt, aber offen; ohne echte Akten (Bescheide mit Tabellen, E-Mail-Ausdrucke, Scans) bleibt Domänenverschiebung ungemessen.

**How to avoid:**
- Hauptkennzahlen festlegen: **Leckrate Zeichen**, **Anteil Dokumente mit Leck**, **exakter Recall je Kategorie**, je Dokumenttyp und Format (Text-PDF, Scan, DOCX, ODT); Überlappung nur ergänzend.
- Testsatz dreiteilen: Entwicklung, Validierung, **verdeckter Holdout** (nur vor Release, von anderer Hand erzeugt; z. B. Vorlagen von einer zweiten Person oder aus FragDenStaat-Antworten mit ersetzten Platzhaltern).
- Namenslisten nach Herkunft im Generator; Recall je Herkunftsgruppe berichten.
- Ende-zu-Ende-Lauf über gerenderte Dateien (Word, LibreOffice, Scan mit Rauschen, gedreht, 200/300 dpi) als Gate.
- Ein **kleines synthetisches, im Repo liegendes CI-Korpus** (lizenzfrei, selbst erzeugt) plus größere lokale Korpora; Gate in CI auf dem kleinen, Release-Gate lokal auf allen.
- Messung auf amd64 und arm64; Modell- und Bibliotheksversionen samt sha256 im Protokoll und in den Testergebnissen.
- Kleiner Nutzertest der Prüf-UI (Zeit pro Seite, Fehlannahmen) vor Release.

**Warning signs:**
Kennzahl steigt nach jeder Regeländerung; kein Holdout; Testnamen fast nur "Schmidt, Müller, Weber"; Gate läuft nur auf einer Architektur.

**Phase to address:** P-Testsatz (früh, vor P-Erkennung), P-Erkennung, P-Prüf-UI (Nutzertest), P-Release.

---

### Pitfall 15: Ressourcen: 4-GB-Stapel, Zombie-LibreOffice und hängende Aufträge

**What goes wrong:**
- **OOM-Kill mitten im Auftrag**: Der Kernel beendet den Prozess (3,96 GB Spitze [Spike]); der Auftrag bleibt für immer "läuft", der Nutzer wartet.
- **Speicherwachstum über viele Aufträge** (torch-Allocator, Fragmentierung, spaCy-Vokabular wächst mit jedem neuen Token).
- **Thread-Überbelegung**: torch nutzt die Kernzahl des Hosts, nicht das CPU-Kontingent des Containers; mit Tesseract-OpenMP und LibreOffice gleichzeitig wird es langsamer statt schneller.
- **Stille Kürzung bei GLiNER**: Eingaben über `max_len` (Standard 384 Wörter je Checkpoint) werden **ohne Fehler** auf den Anfang gekürzt; Funde im Rest gehen verloren, nur eine UserWarning erscheint [belegt: GLiNER-Doku "Input limits and truncation"]. Tabellenzeilen ohne Zeilenumbruch, OCR-Text ohne Absätze oder sehr lange Sätze in Urteilen überschreiten das leicht. Grenzen von Stücken teilen Namen.
- **LibreOffice**: hängt bei kaputten Dateien mit 100 % CPU; `soffice` beendet sich, `soffice.bin` lebt weiter (Zombies); zweite Instanz mit **gleichem Profil** übergibt an die erste und liefert ohne Ausgabe zurück [Fachwissen, Test nötig]; fehlende Schriften im Container ändern Umbrüche, die Ausgabe sieht anders aus als das, was der Prüfer gesehen hat [Fachwissen]; Kaltstart mehrere Sekunden.
- **Große Dokumente**: 500-Seiten-Akte, 300-dpi-Rendering einer A4-Seite in RGB rund 26 MB pro Seite; alle Seiten im Speicher sprengen das Budget.
- **Modelldownload beim ersten Start** ohne Internet (Behördennetz) oder mit Proxy: Start schlägt fehl; Download ohne sha256-Prüfung wäre ein Lieferkettenrisiko.

**How to avoid:**
- Ein Arbeitsprozess pro Auftrag (oder Neustart nach N Aufträgen), Heartbeat in der Auftragstabelle, Wiederaufnahme bzw. Fehlerstatus mit Grund nach Timeout; RAM-Wächter prüft vor dem Start den freien Speicher (geplant) **und** setzt `RLIMIT_AS`.
- `OMP_NUM_THREADS`, `torch.set_num_threads`, Tesseract `OMP_THREAD_LIMIT=1` aus dem cgroup-Kontingent ableiten.
- Text in Stücke mit **Überlappung** zerlegen (Presidio-PR mit 20 % Überlappung als Vorbild [belegt]), Stückgrenze an Satz- und Zeilengrenzen, Wortzahl gegen `max_len` des geladenen Checkpoints prüfen; GLiNER-Warnungen als Fehler behandeln (Test).
- LibreOffice: je Aufruf eigenes `-env:UserInstallation=file:///...`, Prozessgruppe starten und bei Timeout die ganze Gruppe beenden, Aufräumen beim Start; metrisch kompatible Schriften (Liberation, Carlito, Caladea, DejaVu) im Image; Prüfansicht für DOCX/ODT aus **demselben** LibreOffice-Rendering erzeugen wie die Ausgabe.
- Seitenweise Verarbeitung, Seitenbilder nach Gebrauch freigeben, Obergrenzen für Seitenzahl je Auftrag (admin-einstellbar).
- Modelle per Admin-Ablage oder Download mit festem sha256 (geplant); klarer Status "Modelle fehlen" statt Absturz.

**Warning signs:**
Aufträge im Status "läuft" älter als das Doppelte der geschätzten Dauer; `ps` zeigt `soffice.bin` ohne Auftrag; Log-Warnung "truncated to 384"; Laufzeit pro Seite im Container deutlich höher als im Spike.

**Phase to address:** P-Gerüst (Auftragsmodell, Wächter), P-Erkennung (Stückelung), P-Office (LibreOffice-Lebenszyklus), P-Release (Lasttest auf kleiner Zielmaschine, arm64).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Blocklist bekannter Leckorte statt Allowlist für PDF-Katalog und ZIP-Teile | schneller lauffähig, Ausgabe näher am Original | jeder neue Erzeuger bringt neue Leckorte; Nachprüfung findet sie nicht | nie für die Auslieferung; nur im ersten Prototyp |
| Klartext-Funde in der Datenbank speichern | einfache Prüf-UI, "für alle gleichen" trivial | Klartext in allen Backups, Löschpflichten unerfüllbar | nie |
| Fund-Hashes im Protokoll | wirkt nachvollziehbar | per Wörterbuch umkehrbar, Protokoll wird Leck | nie (nur Dateihashes) |
| Ausgabe direkt neben das Original schreiben, auch als Entwurf | Nutzer sieht sofort Ergebnis | Herausgabe vor Freigabe über geteilte Ordner, Versionen, Index | nie vor Freigabe |
| Überschreiben der Ausgabe bei erneutem Lauf | ordentliche Ordner | Altstände in Versionen | nie |
| Parser im Hauptprozess der ExApp | weniger Code | ein Parserfehler gibt Zugriff auf alle Nutzerdateien | nur in lokaler Entwicklung |
| Strukturbaum entfernen statt bereinigt neu aufbauen | sicher und einfach | Ausgabe nicht barrierefrei (BITV 2.0) | v1, mit Hinweis im Protokoll; später Neuaufbau |
| Rastermodus als einzige Abwehr gegen Glyphenpositions-Leck | sofort sicher | Barrierefreiheit weg, Dateien 3- bis 6-mal größer [Spike] | als wählbarer Modus, nicht als Standard |
| Diagramme, SmartArt, OLE entfernen statt schwärzen | kein Leck | Inhaltsverlust für den Antragsteller | v1, mit Meldung im Protokoll und in der UI |
| Regeln nur am eigenen Generator messen | schnelle Iteration | optimistische Zahlen, Domänenschock beim Kunden | nur bis Holdout und Zielmaterial verfügbar sind |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PyMuPDF `apply_redactions` | Standardparameter vertrauen; Links, Annotationen, geteilte XObjects, Strukturbaum für erledigt halten | Parameter explizit setzen, Seiten vorher entflechten, Annotationen vorher flach rendern oder entfernen, pikepdf-Allowlist danach |
| PyMuPDF Ersetzungstext | Pseudonym mit beliebigem Font und beliebiger Länge einsetzen | Base-14-Font, Länge prüfen, Vorhandensein im Ausgabetext prüfen [belegt: Einschränkung in der Doku] |
| PyMuPDF `set_small_glyph_heights` | Standard-Glyphhöhen bei der Suche | Laut Doku gegen Mitlöschen benachbarter Zeilen hilfreich; mit Testsatz entscheiden, Nachbarzeilen-Verlust messen |
| pikepdf | Speichern mit Standardoptionen übernimmt `/ID` | `/ID` explizit neu setzen, Objektstreams neu aufbauen, `qpdf --check` danach |
| lxml | `iterparse` oder Standardparser auf fremdem XML | eigener gehärteter Parser, DTD ablehnen, lxml >= 6.1.0 |
| Python `zipfile` | Doppelte Einträge, Pfade, Größen ungeprüft | Vorprüfung aller `ZipInfo`, Ablehnung bei Auffälligkeiten |
| LibreOffice headless | gemeinsames Profil, Netzwerk an, keine Prozessgruppe | Profil je Aufruf, kein Netz, Timeout mit Gruppenkill, externe Rels vorher entfernen |
| Tesseract | ohne `osd`, ohne Auflösungsprüfung, Thread-Standard | `osd` mitliefern, dpi prüfen, `OMP_THREAD_LIMIT=1` |
| GLiNER/GLiNER2 | lange Texte direkt übergeben | Stückelung mit Überlappung unter `max_len`, Warnung als Fehler |
| Presidio | ungepinnt, Projektwechsel zu Data Privacy Stack | Version pinnen, eigene Erkenner, Telefonerkenner mit Datumsfilter [Spike] |
| Nextcloud Dateien | Ausgabe mit App-Kontext schreiben, Rechte einmal prüfen | im Nutzerkontext schreiben, Rechte je Anfrage, Datei-ID plus ETag |
| Nextcloud Versionen/Papierkorb | ignorieren | nie überschreiben, Nutzer warnen, Versionen gezielt löschen falls nötig |
| Findling / Volltextsuche | Zwischenstände im Nutzerspeicher | nur freigegebene Ausgaben in den Nutzerspeicher |
| Benachrichtigungen | Fundinhalt im Text | nur Status und Link |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Zwei Aufträge parallel mit vollem Stapel | Auslagerung, OOM-Kill | eine Warteschlange, RAM-Wächter, `RLIMIT_AS` | ab zwei Aufträgen auf Servern unter 8 GB |
| Alle Seitenbilder im Speicher | RAM steigt linear mit Seitenzahl | seitenweise rendern, OCR, freigeben | ab ca. 100 Seiten bei 300 dpi |
| OCR-Zweitkanal auf jeder Seite | Laufzeit pro Seite verdoppelt | im gründlichen Modus bewusst, Fortschritt ehrlich anzeigen; Schnellmodus ohne | ab Akten über 50 Seiten |
| Unkomprimierte PNGs nach Pixel-Schwärzung | Ausgabe viel größer als Original | beim Speichern `deflate`, ggf. Bild neu als JBIG2/CCITT/JPEG kodieren | jede gescannte Seite |
| torch-Threads gleich Host-Kernzahl | langsam im Container trotz freier CPU | Threads aus cgroup ableiten | Container mit CPU-Limit |
| LibreOffice-Kaltstart je Datei | Sekunden Overhead pro Datei | ein Prozess je Auftrag, nicht je Datei; sauber beenden | Stapel mit vielen kleinen Dateien |
| pdfminer auf pathologischen Dateien | Minuten für eine Seite | Timeout je Extraktor, Abbruch mit Grund | einzelne Fachverfahrens-PDFs |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Parser mit AppAPI-Geheimnis im selben Prozess | Codeausführung im Parser liest alle Nutzerdateien | Sandbox-Unterprozess ohne Geheimnis, ohne Netz |
| LibreOffice mit Netzwerk | SSRF, Lesen lokaler Dateien in die Ausgabe, Verarbeitungs-Beacon | externe Rels entfernen, Konvertierung ohne Netz |
| Makros in DOCX/ODT bei Konvertierung | Codeausführung | Makroteile entfernen, Makrosicherheit "sehr hoch" im Profil |
| XML mit DTD verarbeiten | XXE, Entitätsbomben | DOCTYPE ablehnen, lxml >= 6.1.0 |
| ZIP-Parser-Differenz (doppelte Namen) | Schwärzer bereinigt andere Datei als der Renderer zeigt | doppelte und auffällige Einträge ablehnen |
| Fundtext in Prüf-UI per `v-html` | XSS über präparierten Namen im Dokument | nur Textbindung, CSP |
| Original-PDF im Browser mit Skripten anzeigen | PDF-JavaScript im Prüferbrowser | Seiten serverseitig als Bilder rendern |
| Prüfseiten-Endpunkte ohne Rechteprüfung je Anfrage | Klartext für Nutzer ohne Zugriff | Rechte je Anfrage gegen aktuelle Knotenrechte |
| Selbstfreigabe im Vier-Augen-Ablauf | Kontrolle umgangen | zweite UID erzwingen, Admin-Ausnahme protokollieren |
| Fund-Hashes im Protokoll | Rückrechnung der PII | nur Dateihashes |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| "Alle annehmen" als prominente Schaltfläche | Automatisierungsvertrauen, Amtsträger und Fehlfunde ungeprüft übernommen | Sammelaktionen nur je Kategorie und Konfidenz, mit Zusammenfassung vor Freigabe |
| Funde, die auf dem Seitenbild nicht sichtbar sind, ohne Erklärung | Prüfer lehnt echten verborgenen Text als Fehlalarm ab | Kennzeichnung "verborgener Text", "nicht angezeigte Fußzeile", "Metadaten" |
| Scan-Seiten ohne Pflichtsichtung | Handschrift, Stempel, Unterschriften bleiben | "Seite geprüft"-Haken je Scan-Seite, Flächenschwärzung sichtbar |
| Fehlermeldung ohne Grund ("Analyse fehlgeschlagen") | Nutzer lädt erneut hoch, Zwischenstände vervielfachen sich | konkrete Gründe (zu groß, verschlüsselt, signiert, Speicher, Zeitlimit) |
| Erfolgsanzeige "anonymisiert" | rechtlich falsches Versprechen | "geschwärzt" bzw. "pseudonymisiert", Hinweis auf Quasi-Identifikatoren |
| Prüfansicht aus anderem Renderer als die Ausgabe | Prüfer gibt etwas frei, das anders aussieht | Prüfansicht aus demselben Rendering wie die Ausgabe |
| Signiertes PDF wird kommentarlos unsigniert | Nutzer wundert sich, Empfänger misstraut | Hinweis vor Analyse, Protokolleintrag |
| Barrierefreiheit geht im Rastermodus verloren, ohne Hinweis | Verstoß gegen BITV bei Veröffentlichung | Modus-Erklärung mit Folgen, Standard nicht Raster |
| Nur Deutsch geprüft | Sprachfehler in EN/FR (Owner: No-Go) | Volltest DE/EN/FR vor Store |

## "Looks Done But Isn't" Checklist

- [ ] **PDF-Schwärzung:** Strukturbaum, `BDC`-ActualText, Seitenlabels, benannte Ziele, `/PieceInfo`, Bild-Metadaten, `/ID`, Signaturen entfernt; prüfen mit Leck-Zoo-Dateien aus Word, LibreOffice und Acrobat.
- [ ] **Geteilte Objekte:** Form XObjects und Bilder je Seite entflochten; prüfen mit Briefkopf-XObject-Datei.
- [ ] **Fonts:** neu untersetzt; prüfen mit Name aus seltenen Zeichen ("Gülşen Ołowska").
- [ ] **Scans:** eigene OCR als einzige Koordinatenquelle, Rotation und Deskew rückgerechnet, MRC-Seiten flach gerendert, Pixelprüfung unter jedem Balken; prüfen mit gedrehten, schiefen und MRC-Scans verschiedener Scanner.
- [ ] **Text-PDF mit Bild-PII:** Bilder geOCRt; prüfen mit eingebetteter Ausweiskopie.
- [ ] **DOCX:** Textfeld-Fallback, SmartArt, Diagramm-Cache und eingebettete Arbeitsmappe, Felder, Inhaltssteuerelemente mit Datenbindung, Glossar, alle Kopf-/Fußzeilen-Varianten, `rsid`, `attachedTemplate`, Bild-EXIF und Beschnitt; prüfen mit in **Word** erzeugten Dateien.
- [ ] **ODT:** bedingter Text, Benutzerfelder, eingebettete Objekte, `settings.xml`; prüfen mit in LibreOffice erzeugten Dateien.
- [ ] **Nachprüfung:** Rohsuche in UTF-16BE, Hex-Strings, XML-Entitäten, rekursiv in eingebetteten ZIPs; Mutationstest je Leckklasse grün.
- [ ] **Nextcloud-Ausgabe:** erst nach Freigabe geschrieben, nie überschrieben, geteilte Zielordner bestätigt; prüfen mit Link-geteiltem Ordner und Versionsliste.
- [ ] **Rechte:** Prüfseite verweigert nach ACL-Entzug; zweite Prüferin ohne Dateizugriff wird abgewiesen.
- [ ] **Logs und DB:** Kanarien-Scan über `nextcloud.log`, Docker-Logs, Datenbank-Dump, ExApp-Volume ohne Treffer.
- [ ] **Protokoll:** keine Fund-Hashes, keine Klartexte, Modellversionen mit sha256.
- [ ] **Pseudonymisierung:** Genitiv, "Herrn", "-sche", Elision korrekt; jedes Pseudonym im Ausgabetext vorhanden; Pseudonyme pro Dokument zufällig.
- [ ] **Sandbox:** Parser ohne Netz und ohne Geheimnis; Bomben-Korpus bricht sauber mit Grund ab.
- [ ] **GLiNER-Stückelung:** keine "truncated"-Warnung über den gesamten Testsatz.
- [ ] **LibreOffice:** keine `soffice.bin`-Reste nach 100 Läufen inkl. absichtlich hängender Datei.
- [ ] **Evaluation:** Holdout von anderer Hand, Recall nach Namensherkunft, Messung auf amd64 und arm64.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Leckende Ausgabe bereits herausgegeben | HIGH | Behörde unterstützen: Liste betroffener Ausgaben aus Protokoll (Dateihash, Modus, Version), Datenpannen-Meldung Art. 33 DSGVO ist Sache der Behörde; App-Update mit neuer Leckklasse im Leck-Zoo; Sicherheitshinweis im Store und im Repo |
| Klartext in Datenbank oder Logs gefunden | MEDIUM | Migration zum Löschen, `occ`-Befehl, Hinweis an Admins zu Backups und Log-Rotation; Kanarien-Test ergänzen |
| Ausgabe vor Freigabe in geteiltem Ordner | MEDIUM | Datei, Versionen und Papierkorb-Eintrag löschen, Freigabe-Zugriffslog prüfen lassen; Schreibzeitpunkt-Logik korrigieren |
| Parser-Ausbruch | HIGH | AppAPI-Geheimnis rotieren (ExApp neu registrieren), betroffene Nutzerdaten prüfen, Sandbox nachrüsten, Sicherheitsmeldung |
| Falsche Pseudonym-Zuordnung in veröffentlichtem Urteil | MEDIUM | Korrekturfassung, Testfall in Pseudo-Testsatz, "Zuordnung prüfen"-Funde schärfen |
| Zombie- oder Hängeaufträge | LOW | Heartbeat-Bereinigung, Prozessgruppen-Kill, Neustart des Arbeitsprozesses |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Nachprüfung ohne Leck-Zoo | P-Testsatz, P-Nachprüfung | Mutationstest: Nachprüfer-Recall 100 % je Leckklasse |
| 2 PDF-Struktur leckt | P-PDF | Leck-Zoo Tagged-PDF, Labels, Ziele, Signatur: 0 Funde; `/ID` neu |
| 3 Geteilte Ressourcen | P-PDF | Briefkopf-XObject, beschnittenes Bild, seltene Glyphen: 0 Funde, keine Fremdseiten geschwärzt |
| 4 Textebene ungleich Seitenbild | P-Extraktion, P-Erkennung | Testdateien mit kaputter CMap, Vektortext, Bild-PII, OCG: alle als Fund oder Verdachtsseite |
| 5 Scans | P-Extraktion, P-PDF | Pixelprüfung unter Balken, Rundweg-Koordinatentest, MRC-Scan: 0 Funde |
| 6 DOCX-Orte | P-Office | Word-Leck-Zoo: 0 Funde in allen Prüfern inkl. Öffnen in Word (Wiederbefüllung) |
| 7 ODT-Orte | P-Office | LibreOffice-Leck-Zoo: 0 Funde |
| 8 Nextcloud-Sichtbarkeit und Versionen | P-Nextcloud, P-Gerüst | Integrationstest: keine Datei vor Freigabe, eine Version je Ausgabe, Findling-Suche ohne Treffer |
| 9 Rechte und Sperren | P-Gerüst, P-Nextcloud, P-Prüf-UI | Negativtests ACL-Entzug, Zweitprüfer ohne Zugriff, ETag-Wechsel |
| 10 Prüfzustand, Protokoll, Logs | P-Gerüst, P-Protokoll | Kanarien-Scan DB, Logs, Volume; Protokoll-Schema ohne Fundwerte |
| 11 Bösartige Dokumente | P-Eingang, P-Office | Bomben- und XXE-Korpus in CI; Parser ohne Netz und Geheimnis nachgewiesen |
| 12 Pseudonymisierung | P-Pseudo | Flexionstestsatz DE/EN/FR, Positivprüfung Pseudonyme, Zufälligkeit je Dokument |
| 13 Amtsträger und Recht | P-Erkennung, P-Prüf-UI, P-Protokoll | Testfälle Bedienstete fremder Behörde, private Kontaktdaten von Amtsträgern; Rechtsrahmen-Auswahl beim Einrichten |
| 14 Evaluation | P-Testsatz | Holdout von anderer Hand, Dokument-Leckanteil, Recall nach Herkunft, beide Architekturen |
| 15 Ressourcen | P-Gerüst, P-Erkennung, P-Office | Lasttest kleine Zielmaschine, 100 LibreOffice-Läufe ohne Reste, keine Kürzungswarnung |

**Reihenfolge-Folgerungen für die Roadmap:**
- P-Testsatz mit Leck-Zoo **vor** P-PDF und P-Office beginnen: ohne Leckklassen-Korpus lässt sich Pitfall 1 bis 7 nicht nachweisen.
- P-Eingang (Sandbox, Parser-Härtung) **vor** der ersten Format-Phase, weil alle Formate dieselbe Sandbox brauchen und ein späterer Umbau den Prozessaufbau der ExApp ändert.
- P-Gerüst muss Datenmodell ohne Klartext, Datei-ID plus ETag und Logging-Regeln festlegen, bevor die Prüf-UI Daten speichert; spätere Migration von Klartextspalten ist teuer (Backups).
- P-Nextcloud-Entscheidung "Ausgabe erst nach Freigabe schreiben" beeinflusst P-Prüf-UI (Vorschau aus App-Speicher) und muss früh feststehen.
- Tiefere Recherche nötig in: P-PDF (MuPDF-Verhalten bei Form XObjects, MRC-Masken, ActualText in `BDC`, `subset_fonts` nach Schwärzung), P-Office (Feldaktualisierung in LibreOffice, Textfeld-Fallback), P-Eingang (Netz-Namespace unter HaRP/Docker), P-Nextcloud (Versions-API je Nextcloud 33 bis 35).

## Sources

- Spike 06.11.2026: `C:/Users/Student/pii-spike-2026-11-06/SPIKE-REPORT.md` (Abschnitte 1.4, 5.1 bis 5.3, 6, 7, 8.4)
- Recherche 04.11.2026: `C:/Users/Student/neue-apps-recherche-2026-11-04/bigtech-pii-redaction-2026-11-04.md`
- PyMuPDF Doku `Page.apply_redactions` (Parameter, Links, Bildreferenzen, unkomprimiertes PNG, Ersetzungsfonts, `set_small_glyph_heights`): https://pymupdf.readthedocs.io/en/latest/page.html (HIGH)
- PyMuPDF Doku Document (Methodenliste `scrub`, `subset_fonts`, Seitenlabels, OCG): https://pymupdf.readthedocs.io/en/latest/document.html (MEDIUM, Seite nur teilweise abrufbar)
- iText pdfSweep 5.0.8 Release, Bug "Redacted text recoverable from tagged PDF structure elements": https://github.com/itext/itext-pdfsweep-java/releases/tag/5.0.8 (MEDIUM)
- pdf-tools Smart Redact Referenz zu Marked Content und ActualText: https://www.pdf-tools.com/docs/smart-redact/references/redaction/ (MEDIUM)
- WebAIM-Diskussion zu Tags nach Schwärzung: https://webaim.org/discussion/mail_message?id=22607 (LOW, widersprüchlich)
- Bland, Iyer, Levchenko, PoPETs 2023: https://crysp.petsymposium.org/popets/2023/popets-2023-0069.php (HIGH)
- JBIG2 Pattern Matching and Substitution, Xerox-Fall: https://en.wikipedia.org/wiki/JBIG2 (MEDIUM)
- Nextcloud Admin Manual, Versionen: https://docs.nextcloud.com/server/stable/admin_manual/configuration_files/file_versioning.html (HIGH)
- Nextcloud Admin Manual, Data retention: https://docs.nextcloud.com/server/stable/admin_manual/gdpr/data_retention.html (HIGH)
- Nextcloud Preview Generator und Vorschau-Verhalten: https://github.com/nextcloud/previewgenerator, https://help.nextcloud.com/t/why-is-preview-pre-generation-not-a-built-in-feature/110551 (MEDIUM)
- lxml XXE CVE-2026-41066 und Standardänderung 5.0/6.1: https://researcher.branch.zeropath.com/blog/cve-2026-41066-lxml-xxe-local-file-disclosure, https://github.com/nextcloud/appstore/pull/1745 (MEDIUM)
- pypdf DoS-CVEs: https://vulert.com/vuln-db/pypdf-s-manipulated-flatedecode-streams-can-exhaust-ram, https://www.sentinelone.com/vulnerability-database/cve-2026-27026/, https://vulert.com/vuln-db/CVE-2026-41314 (MEDIUM, Versionsgrenzen in NVD/GitHub prüfen)
- Gotenberg/LibreOffice SSRF und lokales Dateilesen: https://osv.dev/vulnerability/CVE-2026-55229, https://vuln.today/cve/CVE-2026-42591 (MEDIUM)
- LibreOffice Makro-CVEs (CVE-2018-16858, CVE-2019-9848/9850/9855): https://itsecx.fhstp.ac.at/content/download/165858/file/IT-SECX-2019_Inf%C3%BChr-Alexander_Hunting-for-Remote-Code-Execution-in-your-LibreOffice-Suite.pdf (MEDIUM)
- LibreOffice headless hängt (Makro-Rückfrage, kaputte DOCX): https://bugs.freedesktop.org/show_bug.cgi?id=37441, https://ask.libreoffice.org/t/convert-to-headless-hangs-on-ubuntu-14-04/14023 (LOW, alt)
- Word Inhaltssteuerelemente mit Custom-XML-Bindung: https://learn.microsoft.com/en-us/previous-versions/visualstudio/visual-studio-2012/bb398244(v=vs.110) (HIGH für die Mechanik)
- GLiNER Eingabegrenzen und stille Kürzung: https://urchade.github.io/GLiNER/input_limits.html; Presidio-PR mit überlappender Stückelung: https://github.com/microsoft/presidio/pull/1805 (HIGH/MEDIUM)
- EuGH C-413/23 P (EDSB/SRB), 04.09.2025: https://www.beck-aktuell.de/heute-im-recht/rechtsprechung/eugh-c41323p-pseudonymisierte-daten-personenbezogen-weitergabe-dritte-2025-09-05, https://www.fieldfisher.com/en-be/locations/belgium/insights/edps-v-srb-cjeus-contextual-approach-to-pseudonym (MEDIUM, Volltext prüfen)
- BVerwG 7 C 27/15 (Bearbeiterbegriff § 5 Abs. 4 IFG): https://rewis.io/urteile/urteil/p4t-20-10-2016-7-c-2715/ (MEDIUM, Volltext prüfen)
- Fachwissen ohne neuen Abruf (als solches markiert): OOXML `mc:AlternateContent`, SmartArt/Diagramm-Caches, `rsid`, `attachedTemplate`, ODF bedingter Text und Absenderfelder, MRC-Scan-Schichtung, LibreOffice-Profilsperre, Thread-Verhalten von torch in Containern

---
*Pitfalls research for: lokale PII-Schwärzung und Pseudonymisierung als Nextcloud-App für Behörden*
*Researched: 2026-11-07*
