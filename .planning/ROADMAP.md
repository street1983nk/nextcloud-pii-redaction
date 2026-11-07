# Roadmap: PII Redaction

## Overview

Zuerst werden die Grundlagen gelegt, die sich später nicht mehr billig ändern lassen: zwei Apps (PHP-App `pii_redaction` und ExApp `pii_redaction_backend`) beweisen im Lockstep auf NC 33 bis 35 den ganzen Weg von der Dateiaktion bis zur Dummy-Kopie, mit einem Datenmodell ohne Klartext in Nextcloud, Etag-Bindung und Logging-Allowlist. Danach kommt Sicherheit vor Funktion: Kindprozess-Sandbox und gehärteter Dateieingang vor jedem Format, ein einziger Positionsindex vor allem, was markiert oder entfernt, und ein mit fremden Werkzeugen erzeugter Leck-Zoo samt unabhängigem Leck-Prüfer, bevor echte Schwärzung als erledigt gilt. Auf diesem Fundament entstehen Schwärzung für Text-PDF, DOCX/ODT mit Ausgabe-PDF, die Erkennung, die Prüfseite, Freigabe und Ablage, Rechtsgrundlagen und Protokoll (damit steht der Kernwert), dann Scans, Pseudonymisierung, EN/FR auf DE-Niveau und zum Schluss die Release-Härtung mit Volltest.

Projektmodus: standard, Owner-Entscheid "Schichten mit Sicherheit zuerst". 15 Phasen bei Granularität standard; begründet durch den Umfang (79 Anforderungen, zwei Apps, drei Formate plus Scans, zwei Ausgabemodi) und durch harte Reihenfolge-Regeln aus der Recherche (Sandbox vor Formaten, Index vor Markieren, Prüfer vor Schwärzung). Gegenüber dem 14-Phasen-Vorschlag der Recherche ist "Workflow, Ablage, Rechtsgrundlagen, Protokoll" in zwei Phasen geteilt (Freigabe und Ablage, dann Rechtsgrundlagen und Protokoll), weil beide eigenständig prüfbar sind und zusammen 13 Anforderungen tragen würden. Testsatz und `logic/` laufen ab Phase 1 begleitend.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Zwei-App-Gerüst und Integrationsbeweis** - PHP-App und ExApp im Lockstep, Dateiaktion bis Dummy-Kopie, Auftrag an Datei-ID und Etag, kein Klartext in Nextcloud, Warteschlange
- [ ] **Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox** - Parser nur in Kindprozessen ohne Geheimnis, Vorprüfung, Bomben-/XXE-Korpus, Ablehnung mit Grund, versteckte Netzaufrufe abgestellt
- [ ] **Phase 3: Positionsindex und Dokumentmodell** - Ein Index für Anzeige, Suche, Erkennung und Schwärzung, Normalisierung mit Rückabbildung, unsichtbare Inhalte, OCR für Bilder in Text-PDFs
- [ ] **Phase 4: Testsatz, Leck-Zoo und Eval-Harness** - Leckklassen-Korpus mit Kanarienwerten aus fremden Werkzeugen, Leckrate als Hauptkennzahl, Holdout von anderer Hand
- [ ] **Phase 5: Unabhängiger Leck-Prüfer** - Eigenes Paket ohne PyMuPDF und ohne gemeinsamen Code, fünf Prüfwege, fail-closed
- [ ] **Phase 6: Echte Schwärzung Text-PDF** - Entfernen unter jeder Fläche, Allowlist-Bereinigung, Neuschreiben, gerundete Balken, Modus "Höchste Sicherheit"
- [ ] **Phase 7: Echte Schwärzung DOCX/ODT und Ausgabe-PDF** - ZIP-Allowlist über alle Teile, Diagramme/SmartArt/OLE entfernt, getaggtes PDF über LibreOffice, E2E-Lecktest in CI
- [ ] **Phase 8: Erkennung** - Gründlicher Stapel als Standard, deutsche Prüfziffer-Erkenner, drei Stufen, Entitäten, Amtsträger, Modelle mit sha256, RAM-Wächter
- [ ] **Phase 9: Prüfseite** - Seitenübersicht, Kästchen, Entitätenliste, Annehmen/Ablehnen, Suchen und schwärzen, Flächen, Tastaturfluss, BITV
- [ ] **Phase 10: Freigabe und Ablage** - Status, Vier-Augen, Kopie neben dem Original nach bestandener Nachprüfung, Lebensdauer und Löschung des Prüfzustands, Netzfreiheit belegt
- [ ] **Phase 11: Rechtsgrundlagen und Protokoll** - Label-Sätze je Schwärzung, Länder-Sätze "ungeprüft", Protokoll PDF + JSON ohne Klartext, Begründungsliste
- [ ] **Phase 12: Scans und OCR** - Eigene OCR als einzige Koordinatenquelle, OCR-Qualität je Seite, Pixelschwärzung und frische Textebene
- [ ] **Phase 13: Pseudonymisierung** - Gleichwertiger Modus, konsistente Pseudonyme ohne echte Initialen, Flexion DE/EN/FR, Positivprüfung
- [ ] **Phase 14: EN/FR auf DE-Niveau** - Eigene Regeln und Modelle für EN und FR, Leckrate je Sprache als Gate
- [ ] **Phase 15: Release-Härtung und Volltest** - Admin-Zustände, Dreisprachigkeit, Messung amd64/arm64, Sicherheitsaudit, Playwright-Abnahme und Volltest DE/EN/FR

## Phase Details

### Phase 1: Zwei-App-Gerüst und Integrationsbeweis
**Goal**: Der Admin installiert beide Apps, und ein berechtigter Nutzer startet aus der Dateien-App einen Auftrag, der als Hintergrundarbeit läuft, eine Platzhalter-Seite über die PHP-App zeigt und eine Benachrichtigung schickt; Datenmodell, Etag-Bindung, Warteschlange und Logging-Regeln stehen, bevor irgendeine Phase Klartext speichert.
**Depends on**: Nothing (first phase)
**Requirements**: PLAT-01, PLAT-02, PLAT-03, PLAT-05, JOB-01, JOB-02, JOB-03, JOB-04, JOB-06
**Success Criteria** (what must be TRUE):
  1. Admin installiert `pii_redaction` (PHP) und `pii_redaction_backend` (ExApp) auf NC 33, 34 und 35 (amd64 und arm64, HaRP); CI belegt Lockstep-Version und ein Upgrade beider Apps; fehlt die Gegen-App, ist sie nicht erreichbar oder hat sie eine andere Version, sieht der Admin eine klare Meldung.
  2. Ein Nutzer wählt bei einer PDF-, DOCX- oder ODT-Datei "Schwärzen / Pseudonymisieren", sieht ehrlichen Fortschritt und Warteschlangenposition, bekommt eine Benachrichtigung ohne Fundinhalt und öffnet eine Platzhalter-Prüfseite mit Seite 1 als Bild, ausgeliefert über die PHP-App mit Rechte-Recheck bei jeder Anfrage; eine Dummy-Kopie entsteht per `newFile()` als Auftraggeber neben dem Original.
  3. Ein Nutzer ohne Leserecht (auch über Gruppenordner-ACL oder entzogene Freigabe) kann weder starten noch die Seite öffnen; eine Freigabe mit Download-Sperre blockiert den Start; der Container hat keine Browser-Routen (Test).
  4. Ändert sich das Original nach dem Start, wird der Auftrag als ungültig gemeldet (Etag-Wechsel im Test).
  5. Es läuft höchstens ein Auftrag zur Zeit je Container; Nextcloud-Tabellen und Logs enthalten nur geschlossene Status- und Grundlisten, ein Kanarienwert aus dem Dummy-Dokument taucht weder in der DB noch in Logs auf.
**Plans**: 21 plans in 10 Wellen

Plans:
- [x] 01-01-PLAN.md: Gerüst: backend/ und php/, Paketfreigabe, Lockstep-Gate, php.yml (Welle 1)
- [x] 01-02-PLAN.md: Datenmodell: Migration ohne Klartext, Enums, JobMapper mit Sperrzeile und Lease (Welle 2)
- [x] 01-03-PLAN.md: Kataloge DE/de_DE/EN/FR, PHP-Gates, Log-AST-Gate, Dreisprachigkeits-Test mit U+00A0 (Welle 2)
- [x] 01-04-PLAN.md: FileAccess-Recheck mit Download-Sperre, ReaderContext, ExAppService, Handshake (Welle 2)
- [x] 01-05-PLAN.md: Kindprozesse ohne Geheimnis, Magic-Bytes, Rendering, LibreOffice, Platzhalter-PDF, Image (Welle 2)
- [x] 01-06-PLAN.md: Container-Kern: Logs ohne Inhalt, Enums, nc.py, Companion, RAM-Wächter (Welle 3)
- [x] 01-07-PLAN.md: Früher Push auf phase-01 mit Owner-Freigabe, php.yml und python.yml grün (Welle 4)
- [x] 01-08-PLAN.md: JobService, NotificationSender, JobController: Start und Status mit Recheck und Etag (Welle 5)
- [x] 01-09-PLAN.md: Dateiaktion, Prüfseite (Vue), Admin-Skript, Vite-Build (Welle 5)
- [x] 01-10-PLAN.md: Runner mit Semaphore und Zulassung, signierte Container-Endpunkte, main.py (Welle 5)
- [x] 01-11-PLAN.md: Admin-Statusbereich mit sieben Zuständen und Apps-Link (Welle 5)
- [x] 01-12-PLAN.md: QueueController und auftragsgebundenes Gateway (Welle 6)
- [x] 01-13-PLAN.md: ReviewController: Prüfseite, Seitenbild-Proxy, Platzhalter-Aktion (Welle 6)
- [x] 01-14-PLAN.md: Notifier, Suffix, PublishService/PublishJob, Listener, Application (Welle 6)
- [x] 01-21-PLAN.md: Zweiter früher Push auf phase-01 mit Owner-Freigabe, phpunit der Wellen 5 und 6 grün (Welle 7)
- [x] 01-15-PLAN.md: deploy-harp.yml mit sieben Beinen, Saat, Fixtures, Kernweg (Welle 8)
- [ ] 01-16-PLAN.md: Playwright-Suite nach UI-SPEC-Prüfvertrag (Welle 8)
- [ ] 01-17-PLAN.md: CI-Prüfskripte Rechte, Etag, Warteschlange, Routen, Kanarie, Messung (Welle 8)
- [ ] 01-18-PLAN.md: Upgrade-Job, Drift-Schritte, zwei Store-Archive (Welle 9)
- [ ] 01-19-PLAN.md: Doku DE/EN/FR, DESIGN, PRODUCT, CHANGELOG, Umlaut-Audit (Welle 9)
- [ ] 01-20-PLAN.md: Owner: Push, CI, Messwerte, Zertifikatsstatus, gemeinsame Playwright-Abnahme (Welle 10)
**UI hint**: yes
**Research flag**: Standardmuster (AVS-Zwei-App-Muster, Gateway, Queue mit Lease, ExAppService). Zu klären: Dateiaktion über `@nextcloud/files` 4.x mit Vite-Build auf NC 33 bis 35, Streaming über HaRP, Zertifikat `pii_redaction_backend` (#1419). Container-Messwerte (RSS, Kaltstart) hier oder in Phase 2 erheben, RAM-Schwellen erst danach festschreiben.

### Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox
**Goal**: Keine bösartige oder kaputte Datei kann die ExApp übernehmen oder ins Netz rufen: alle Parser laufen isoliert und begrenzt, gefährliche Eingaben werden vor dem Parsen mit konkretem Grund abgewiesen.
**Depends on**: Phase 1
**Requirements**: SAFE-01, SAFE-02, SAFE-03, SAFE-04, JOB-05, RES-02
**Success Criteria** (what must be TRUE):
  1. Ein Test belegt, dass jeder Parser-Kindprozess (PDF, ZIP, XML, LibreOffice, OCR) kein AppAPI-Geheimnis in der Umgebung sieht, Zeit- und Speichergrenzen hat und bei Überschreitung mit der ganzen Prozessgruppe beendet wird (keine LibreOffice-Zombies).
  2. Der Bomben-, XXE-, Doppelnamen- und External-Rels-Korpus läuft in CI und wird abgewiesen, ohne dass der Container abstürzt oder hängt; ein Test-DOCX mit externem Bild und Makro löst keinen Netzaufruf aus.
  3. Ein Nutzer, der eine verschlüsselte, Ende-zu-Ende-verschlüsselte, defekte, falsch benannte (Magic-Bytes) oder zu große Datei (über 300 Seiten) startet, sieht einen konkreten Ablehnungsgrund; bei einer signierten PDF wird vor der Analyse gemeldet, dass die Signatur wegfällt.
  4. Ein Lauf im Container mit `--network none` zeigt, dass Presidio, tldextract und GLiNER2 keine versteckten Netzaufrufe mehr auslösen.
**Plans**: TBD
**Research flag**: Netz-Namespace/Prozessisolation unter HaRP/Docker (bubblewrap meist durch seccomp gesperrt, sonst Restrisiko dokumentieren), LibreOffice-25.2-Härtungsschlüssel (Makros, externe Links) mit Netzwerkmitschnitt.

### Phase 3: Positionsindex und Dokumentmodell
**Goal**: Jedes Dokument hat genau einen Positionsindex, auf dem Anzeige, Suche, Erkennung und Schwärzung arbeiten, so dass die Oberfläche nie etwas anderes markiert, als die Schwärzung entfernt; verborgene Inhalte werden sichtbar gemacht statt übersehen.
**Depends on**: Phase 2
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):
  1. Für Text-PDF liefert der Index Zeichen-Boxen, für DOCX/ODT einen Textstrom mit Quellanker über alle Teile (Kopf/Fuß, Fußnoten, Kommentare, Textfelder); ein Rundweg-Test bildet jede Textspanne auf dieselbe Stelle in Seitenbild bzw. Vorschau-PDF ab.
  2. Text mit Ligaturen, weichen Trennstrichen, geschützten Leerzeichen und Nullbreite-Zeichen wird normalisiert gefunden und exakt auf die Originalpositionen zurückgeführt (Testkorpus).
  3. Unsichtbarer oder weißer Text, ausgeschaltete Ebenen, Text außerhalb des Seitenbereichs, verborgener Text, nicht angezeigte Kopf- und Fußzeilen und Metadaten erscheinen als Hinweise im Dokumentmodell.
  4. Personenbezogener Text in einem eingebetteten Bild einer Text-PDF wird per OCR in den Index aufgenommen und ist für die Erkennung sichtbar.
**Plans**: TBD
**Research flag**: Abbildung DOCX/ODT-Fund auf Vorschau-Kästchen (Tabellen, Silbentrennung, Felder), Verfahren über Nachher-Rendering vorbereiten (Festlegung in Phase 7), Umgang mit unsichtbaren Inhalten.

### Phase 4: Testsatz, Leck-Zoo und Eval-Harness
**Goal**: Es gibt einen nachprüfbaren Maßstab für "nichts Geschwärztes steckt mehr drin": ein Leck-Zoo je Leckklasse aus fremden Werkzeugen und ein eigener Testsatz mit Leckrate als Hauptkennzahl, beides unabhängig von der späteren Umsetzung. Läuft begleitend ab Phase 1, muss vor Abschluss von Phase 6 fertig sein.
**Depends on**: Phase 1 (begleitend)
**Requirements**: LEAK-04, REL-01
**Success Criteria** (what must be TRUE):
  1. Der Leck-Zoo enthält je Leckklasse (u. a. Strukturbaum, ActualText, Seitenlabels, Ziele, Signatur, geteiltes Briefkopf-XObject, beschnittene Bilder, seltene Glyphen, MRC, Textfeld-Fallback, SmartArt, Diagramm-Cache, Datenbindung, Glossar, Kopf/Fuß-Varianten, ODT-Bedingungstext) Dateien mit Kanarienwerten, erzeugt mit Word, LibreOffice, Acrobat, qpdf oder Scannern, nicht mit dem eigenen Code.
  2. Die Positivkontrollen aus dem Spike (Overlay, inkrementelles Speichern) werden vom Harness als Leck erkannt.
  3. Der Harness berichtet Leckrate (Zeichen), Anteil Dokumente mit Leck, Recall je Kategorie, Format und Dokumenttyp sowie Recall nach Namensherkunft; ein Holdout-Teil stammt von anderer Hand und wird nur zum Gate geöffnet.
  4. Ein kleines lizenzfreies CI-Korpus liegt im Repo, große Korpora nur lokal mit sha256-Manifest.
**Plans**: TBD
**Research flag**: Keiner in der Recherche; Herkunft und Lizenz der Zoo-Dateien und des Holdouts (FAU/ALeKS-Goldstandard am 07.11. abgelehnt). OWNER 07.11.: EIGENER GOLDSTANDARD aus öffentlichen Dokumenten (Urteile, Ratsvorlagen; Lizenz je Quelle prüfen, amtliche Werke § 5 UrhG). Holdout "von anderer Hand" = ZWEI fremde Modelle (Owner 07.11.: Gemini 3.1 Pro und GPT-6.1-sol über API, NICHT Claude, weil der Erkenner mit Claude gebaut wird), unabhängig, ohne Erkenner-Ergebnisse; Übereinstimmung gilt, Widersprüche entscheidet der Owner; nur zum Gate geöffnet. Modell, Version und Prompt werden festgeschrieben (reproduzierbar). Zusätzlich Stichprobe je Kategorie und Namensherkunft und Abgleich gegen die Kanarienwerte des Leck-Zoos. Nur öffentliche Dokumente an die APIs. Kosten ca. 8 bis 11 $ je Durchlauf (Stand 07.11.). Nutzungsbedingungen GEPRÜFT 07.11.: Gemini API Terms ("You may not use the Services to develop models that compete with the Services") und OpenAI Services Agreement ("use Output to develop artificial intelligence models that compete with OpenAI's products and services" verboten; Output gehört uns; keine Nutzung der API-Daten zum Training). Im EWR gelten bei Gemini die Paid-Regeln auch für die kostenlose Quote (keine Produktverbesserung mit unseren Daten). Folge: Auszeichnungen NUR zur Messung (Holdout/Gate). Für V2-01 (eigenes Modell) keine Modell-Auszeichnungen als Trainingsdaten, sondern eigene/menschliche Auszeichnung oder vorher rechtliche Klärung.

### Phase 5: Unabhängiger Leck-Prüfer
**Goal**: Jede Ausgabe wird von einem eigenständigen Prüfer kontrolliert, der andere Werkzeuge als die Schwärzung nutzt und bei jedem Fund die Ausgabe verhindert; er ist fertig und gegen den Leck-Zoo kalibriert, bevor die Schwärzung entsteht.
**Depends on**: Phase 3, Phase 4
**Requirements**: LEAK-01, LEAK-02, LEAK-03
**Success Criteria** (what must be TRUE):
  1. Ein AST-Test belegt, dass das Paket `leakcheck/` weder PyMuPDF noch Code aus Schwärzung, Erkennung oder Dokumentmodell importiert.
  2. Der Prüfer findet Kanarienwerte über zwei Text-Extraktoren mit unscharfem Abgleich, Rohsuche in allen Kodierungen (rekursiv in eingebetteten Containern), Revisionszählung, OCR mit unabhängigem Renderer, LibreOffice-Textexport und Positionsprüfung für kurze Werte.
  3. Der Mutationstest über den Leck-Zoo erreicht Prüfer-Recall 100 % je Leckklasse und ist als Gate in CI verankert.
  4. Findet der Prüfer etwas, entsteht keine Ausgabe, es gibt keinen Abschaltschalter, und das Ergebnis steht im Prüfergebnis für das Protokoll.
**Plans**: TBD
**Research flag**: pypdfium2 als unabhängiger Renderer (Positivkontrollen wiederholen), Regel für erlaubte Vorkommen abgelehnter gleicher Werte.

### Phase 6: Echte Schwärzung Text-PDF
**Goal**: Aus einer Text-PDF mit festgelegten Schwärzungsflächen (zunächst Gold-Spannen) entsteht eine neu geschriebene PDF, in der der unabhängige Prüfer nichts Geschwärztes mehr findet, weder im Text noch in Bildern, Vektoren, Struktur oder Altversionen.
**Depends on**: Phase 2, Phase 3, Phase 5
**Requirements**: RED-01, RED-02, RED-06, RED-07
**Success Criteria** (what must be TRUE):
  1. Für alle PDF-Leckklassen des Zoos meldet der Leck-Prüfer 0 Funde; Text, Bildpixel und Vektoren unter jeder Fläche sind entfernt, geteilte XObjects und Bilder je Seite entflochten, Fonts neu untersetzt, die Datei hat genau eine Revision.
  2. Metadaten, XMP, Kommentare, Formulare, Anhänge, JavaScript, Lesezeichen, Seitenlabels, benannte Ziele, Strukturbaum und ActualText sind entfernt, die Dokument-ID ist neu; die Ausgabe ist als "nicht barrierefrei" ausgewiesen.
  3. Balken haben standardmäßig eine gerundete Breite; die Rechtsgrundlage kann optional im Balken stehen.
  4. Der Modus "Höchste Sicherheit" rastert die Seiten und legt frische OCR an, ist nur bewusst wählbar, erklärt seine Folgen und ist im Dateinamen kenntlich.
**Plans**: TBD
**Research flag**: MuPDF-Verhalten bei geteilten Form XObjects, `BDC`-ActualText, `subset_fonts` nach Schwärzung, Strukturbaum nach `apply_redactions` (mit Zoo-Dateien klären).

### Phase 7: Echte Schwärzung DOCX/ODT und Ausgabe-PDF
**Goal**: Aus DOCX und ODT entsteht eine geschwärzte Office-Datei und immer zusätzlich ein neu geschriebenes PDF; beide bestehen den Leck-Prüfer, und ein Ende-zu-Ende-Lecktest über alle Formate sichert das in jedem Build.
**Depends on**: Phase 6
**Requirements**: RED-03, RED-04, RED-05, REL-02
**Success Criteria** (what must be TRUE):
  1. Für alle DOCX/ODT-Leckklassen des Zoos (Änderungen, Kommentare, verborgener Text, Kopf/Fuß aller Varianten, Fußnoten, Felder, Textfeld-Fallback, Datenbindung, customXml, Glossar, Metadaten, Vorschaubilder, Bild-EXIF und Beschnitt, Links, ODT-Bedingungstext und Benutzerfelder) meldet der Prüfer in Office-Datei und Ausgabe-PDF 0 Funde.
  2. Diagramme, SmartArt und OLE-Objekte fehlen in der Ausgabe und werden dem Nutzer gemeldet.
  3. Aus DOCX/ODT entsteht über LibreOffice headless ein getaggtes, barrierefreies PDF; eine Flächenschwärzung auf DOCX/ODT ergibt nur eine PDF-Ausgabe (Ausnahme: Fläche auf eingebettetem Bild), gesetzt auf dem Nachher-Rendering.
  4. Der Ende-zu-Ende-Lecktest über Text-PDF, DOCX und ODT läuft in CI und blockiert jedes Store-Release bei einem Leck.
**Plans**: TBD
**Research flag**: Feldaktualisierung in LibreOffice, Textfeld-Fallback, PDF/UA-Export im Container, Flächen-Verfahren über Nachher-Rendering.

### Phase 8: Erkennung
**Goal**: Die App schlägt lokal und mit gemessener Qualität vor, was personenbezogen ist: gründlicher Modus als Standard, deutsche IDs mit Prüfziffer, drei Konfidenzstufen, Funde gebündelt zu Entitäten, Amtsträger erkannt aber geschwärzt, alles innerhalb der RAM-Grenzen.
**Depends on**: Phase 3, Phase 4
**Requirements**: DET-01, DET-02, DET-03, DET-04, DET-05, DET-06, DET-07, DET-08, DET-09, RES-01, RES-03
**Success Criteria** (what must be TRUE):
  1. Im gründlichen Modus liegt die Personen-Leckrate auf dem DE-Testsatz höchstens bei 1,1 % der PII-Zeichen (Gate in CI); der Schnellmodus ist nur bewusst wählbar und zeigt einen Hinweis auf die höhere Leckrate.
  2. IBAN, Steuer-ID, Steuernummer, Personalausweis, Pass, RV-Nummer, KVNR und Kfz-Kennzeichen (auch mit Leerzeichen) werden erkannt, ebenso Telefon, E-Mail, Anschrift und Geburtsdatum mit Kontextwort; Fristdaten, Aktenzeichen und PLZ ohne Anschrift werden nicht markiert; Daten ohne Kontextwort in einer Personenzeile erzeugen den Hinweis "Datum in Personenzeile", Art.-9-Begriffe und Beruf neben Name erzeugen Hinweise.
  3. Jeder Fund trägt eine Stufe hoch, mittel oder niedrig, niedrige werden nie automatisch angenommen; "Herr Müller", "Müller" und "M." bilden eine Entität; Namen, die zugleich Wörter sind, werden gesondert behandelt; Amtsträger erscheinen als eigene Kategorie (Bearbeiter im Vorgang, sonstige Bedienstete), sind aber vorbelegt geschwärzt.
  4. Lange Texte werden mit Überlappung gestückelt; ein Test mit stillem Abschneiden durch ein Modell schlägt als Fehler fehl.
  5. Modelle liegen mit festem sha256 im persistenten Speicher (DE-Stapel beim Einrichten, Admin-Ablage möglich); der RAM-Wächter lässt Erkenner und LibreOffice nie gleichzeitig laufen, der Erkenner bleibt warm, solange Arbeit ansteht, und endet im Leerlauf.
**Plans**: TBD
**Research flag**: Keiner ausdrücklich (Spike-Stapel gemessen); offen bleiben Linux-RSS des Stapels im Container und Owner-Entscheid OCR-Zweitkanal je Seite im gründlichen Modus (nach Messung im Testsatz).

### Phase 9: Prüfseite
**Goal**: Ein Nutzer prüft alle Vorschläge auf einer eigenen, barrierefreien Seite der PHP-App: er sieht, was gefunden wurde, entscheidet einzeln oder gesammelt, ergänzt eigene Schwärzungen und sieht vorab das Ergebnis.
**Depends on**: Phase 3, Phase 8 (kann mit Fake-Funden parallel zu Phase 8 beginnen)
**Requirements**: REV-01, REV-02, REV-03, REV-04, REV-05, REV-06, REV-07, REV-08
**Success Criteria** (what must be TRUE):
  1. Ein Nutzer sieht Seitenübersicht mit Fundmarkern, Seitenbild mit Kästchen und eine Entitätenliste nach Kategorie mit Zähler; Hinweise wie "verborgener Text", "nicht angezeigte Fußzeile" und "Metadaten" sind sichtbar.
  2. Ein Nutzer nimmt Funde an, lehnt sie ab oder markiert sie als unsicher, einzeln und "für alle gleichen Funde"; die Sammelannahme gilt nur für hohe Konfidenz, verlangt eine Anzahl-Bestätigung und lässt sich rückgängig machen.
  3. Ein Nutzer sucht Text oder Muster und schwärzt alle Treffer inklusive Umlaut-Varianten, Zeilenumbruch und Silbentrennung; er markiert Text von Hand und zieht Flächen bis zur ganzen Seite, auch per Tastatur; er schaltet zwischen Original und Ergebnis-Vorschau um.
  4. Die Seite ist vollständig per Tastatur mit Legende bedienbar (Einbuchstaben-Kürzel nur bei Fokus in der Liste oder abschaltbar), bietet eine zugängliche Textansicht, unterscheidet Kategorien nie nur über Farbe und besteht WCAG 2.1 AA / BITV 2.0 (axe plus manueller Durchgang, Playwright 3 Breiten hell/dunkel).
  5. Arbeiten zwei Personen gleichzeitig, wird der Konflikt erkannt (Revision, 409); Fundtext erscheint nie ungeschützt im HTML (kein `v-html`, Test mit Skript im Dokument).
**Plans**: TBD
**UI hint**: yes
**Research flag**: Standardmuster (Nextcloud-Vue-Komponenten, UI-Ablauf nach Owner-Regel: DESIGN.md, nextcloud-ui, Varianten, Playwright). Kleiner Nutzertest der Prüfseite vor Release vormerken.

### Phase 10: Freigabe und Ablage
**Goal**: Nach Prüfung und Freigabe entsteht die geschwärzte Kopie neben dem Original, aber erst nach bestandener Nachprüfung; der Klartext-Prüfzustand verschwindet nachweislich, und kein Inhalt verlässt den Server.
**Depends on**: Phase 6, Phase 7, Phase 9
**Requirements**: FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, FLOW-06, PLAT-04, ADM-02
**Success Criteria** (what must be TRUE):
  1. Ein Auftrag durchläuft Entwurf, geprüft und freigegeben mit Prüfer und Zeitstempel; bei Vier-Augen-Pflicht gibt nur eine zweite Person aus der Freigabegruppe mit Leserecht frei, nie der Prüfer selbst, und die Freigabe gilt genau für einen Entscheidungsstand (Änderung danach verlangt neue Freigabe).
  2. Vor der Freigabe sieht der Freigeber eine Zusammenfassung dessen, was nicht geschwärzt wird (z. B. N Amtsträger).
  3. Erst nach Freigabe und bestandener Nachprüfung liegt die Kopie neben dem Original im Namen des Auftraggebers (`_geschwärzt`, `_redacted`, `_caviardé`, `_pseudonymisiert`); nichts wird überschrieben, das Original bleibt unverändert; ein geteilter Zielordner verlangt eine Bestätigung, Personenbezug in Dateiname oder Ordnerpfad wird gewarnt.
  4. Der Prüfzustand mit Klartext liegt nur im Container-Volume und wird nach 14 Tagen (verlängerbar), bei Veröffentlichung, Abbruch, Löschen oder Ändern des Originals gelöscht; der Kanarien-Scan in CI findet keinen Fundtext in Nextcloud-DB, Logs oder Volume nach dem Löschen.
  5. Der Admin stellt Vier-Augen-Pflicht, Freigabegruppe, Rechtsrahmen, Standardmodus und Lebensdauer ein; ein CI-Lauf des ganzen Pfads (Erkennung, Schwärzung, Nachprüfung) im Container ohne Netz gelingt, einzige ausgehende Verbindung ist der Modell-Download mit festem sha256 von der Host-Allowlist.
**Plans**: TBD
**UI hint**: yes
**Research flag**: Versions-API NC 33 bis 35, Erkennung geteilter Zielordner.

### Phase 11: Rechtsgrundlagen und Protokoll
**Goal**: Jede Schwärzung trägt eine nachvollziehbare Rechtsgrundlage, und die Behörde erhält ein Protokoll und eine Begründungsliste für den Bescheid, ohne dass darin personenbezogene Daten stehen. Damit ist der Kernwert für Text-PDF, DOCX und ODT vollständig.
**Depends on**: Phase 10
**Requirements**: LEGAL-01, LEGAL-02, LEGAL-03, LEGAL-04, LEGAL-05
**Success Criteria** (what must be TRUE):
  1. Ein Nutzer wählt je Schwärzung eine Rechtsgrundlage aus dem Satz (vorbelegt IFG Bund und Veröffentlichung von Entscheidungen, dazu UIG und VIG) und vergibt für bewusstes Nicht-Schwärzen ein eigenes Label (z. B. § 5 Abs. 4 IFG), das protokolliert wird.
  2. Der Admin wählt beim Einrichten den Rechtsrahmen und passt Sätze je Behörde an; Länder-Sätze sind als "juristisch ungeprüft" gekennzeichnet, ein Hinweis "keine Rechtsberatung" ist sichtbar.
  3. Über die Prüfseite (nicht neben der Kopie) ruft ein Berechtigter das Schwärzungsprotokoll als PDF und JSON ab: Dateihashes, Prüfer, Freigeber, Modus, je Schwärzung lfd. Nr., Seite, Kategorie, Rechtsgrundlage, Herkunft, Konfidenz, Ergebnis der Nachprüfung, Modellversionen; ein Kanarien-Test belegt, dass weder Klartext noch Hashes einzelner Werte darin stehen.
  4. Eine Begründungsliste für den Bescheid (Seite, Umfang, Rechtsgrundlage, Kurzbegründung) entsteht als eigene Datei.
**Plans**: TBD
**UI hint**: yes
**Research flag**: Juristisches Gegenlesen der Label-Sätze (Bund HIGH, Länder LOW bis HIGH gemischt) vor Store.

### Phase 12: Scans und OCR
**Goal**: Gescannte PDFs werden lokal per OCR erkannt, geprüft und so geschwärzt, dass weder Pixel noch alte oder neue Textebene den geschwärzten Inhalt enthalten.
**Depends on**: Phase 8, Phase 9, Phase 11
**Requirements**: SCAN-01, SCAN-02, SCAN-03, SCAN-04
**Success Criteria** (what must be TRUE):
  1. Ein Nutzer startet eine gescannte PDF (deu, eng, fra) und sieht die OCR-Qualität je Seite; Seiten mit schlechter Qualität verlangen eine Sichtung, bevor freigegeben werden kann.
  2. Kästchen auf der Prüfseite und Schwärzungsflächen stammen aus derselben eigenen OCR, auch bei gedrehten und schiefen Seiten (Rundweg-Test), und werden erweitert.
  3. Die Ausgabe hat die alte Textebene verworfen, die Pixel unter jeder Fläche ersetzt (Pixelprüfung je Balken) und eine neue OCR-Ebene aus dem geschwärzten Bild; der Leck-Prüfer findet in Scan-Dateien des Zoos (inkl. MRC) 0 Funde.
  4. Prüfziffer-Erkenner melden auf Scans auch Kandidaten mit fehlerhafter Prüfziffer als "niedrig".
**Plans**: TBD
**UI hint**: yes
**Research flag**: Komplett offen, Messung Pflicht: OCR-Qualität deutscher Behördenscans, MRC-Masken, Laufzeit, Glyphenpositions-Leck (PoPETs 2023), ggf. `tessdata_best`. Echte Scans verschiedener Hersteller vorher in den Zoo.

### Phase 13: Pseudonymisierung
**Goal**: Ein Nutzer wählt statt Balken gleichwertig Pseudonyme und erhält ein lesbares Dokument, in dem jede Person über alle Varianten dasselbe, nicht rückführbare Pseudonym trägt und kein Originalwert mehr steht.
**Depends on**: Phase 6, Phase 7, Phase 8, Phase 9
**Requirements**: PSEU-01, PSEU-02, PSEU-03, PSEU-04, PSEU-05
**Success Criteria** (what must be TRUE):
  1. Ein Nutzer wählt "Pseudonymisieren" gleichwertig zu "Schwärzen"; die UI sagt "pseudonymisiert", nie "anonymisiert".
  2. Jede Entität bekommt über alle Varianten ein konsistentes Pseudonym aus fortlaufenden Buchstaben je Kategorie nach erstem Auftreten ("A.", "B.", "A-Stadt", "A GmbH"); ein Buchstabe gleich der echten Initiale wird übersprungen, nichts wird aus Hash oder Name abgeleitet, es gibt keine Option mit echten Initialen.
  3. Schemata gibt es in DE, EN und FR, Flexion (Genitiv, "Herrn", "-sche", Bindestrich, französische Elision) bleibt grammatisch korrekt (Testsätze).
  4. Ein Nutzer verknüpft und trennt Entitäten, Pseudonyme werden neu vergeben; unsichere Zuordnungen erscheinen als Fund "Zuordnung prüfen".
  5. Die Positivprüfung findet jedes Pseudonym in der Ausgabe, der Leck-Prüfer keinen Originalwert; nach der Löschung des Prüfzustands existiert keine gespeicherte Zuordnung.
**Plans**: TBD
**UI hint**: yes
**Research flag**: Ersatztext im PDF bei längeren Pseudonymen (Base-14-Font, Längenprüfung), Flexionsregeln, Initialen-Cluster (Spike 73 %).

### Phase 14: EN/FR auf DE-Niveau
**Goal**: Englische und französische Dokumente werden mit derselben gemessenen Sorgfalt erkannt wie deutsche.
**Depends on**: Phase 4, Phase 8
**Requirements**: DET-10
**Success Criteria** (what must be TRUE):
  1. Aktenzeichen, Anschriften und IDs in EN und FR werden mit eigenen Regeln erkannt (Testsätze je Sprache).
  2. EN- und FR-Modelle werden bei Bedarf mit festem sha256 nachgeladen, das französische Modell zur Laufzeit (LGPL-LR), nie im Image.
  3. Die Leckrate je Sprache ist gemessen und als Gate in CI festgehalten; ein Rückschritt lässt den Build fehlschlagen.
**Plans**: TBD
**Research flag**: Keiner ausdrücklich; Testmaterial EN/FR und Lizenzprüfung `fr_core_news_lg` (LGPL-LR) vor dem Plan klären.

### Phase 15: Release-Härtung und Volltest
**Goal**: Vor dem Store-Release ist belegt, dass Sicherheit, Tempo und Sprache auf beiden Architekturen stimmen, und alle Funktionen und Meldungen in DE, EN und FR sind gemeinsam mit dem Owner abgenommen.
**Depends on**: Phase 11, Phase 12, Phase 13, Phase 14
**Requirements**: ADM-01, REL-03, REL-04, REL-05, I18N-01
**Success Criteria** (what must be TRUE):
  1. Der Admin sieht Zustand beider Apps, Modelle, Warteschlange und Fehlgründe ohne Dateinamen und ohne Inhalt.
  2. Image-Größe, RAM und Laufzeit je Seite sind im Container auf amd64 und arm64 gemessen und dokumentiert; Fortschrittsanzeige und Gates halten auf beiden Architekturen.
  3. Das Sicherheitsaudit mit Negativtests (Rechteentzug, Etag-Wechsel, Download-Sperre, Zweitprüfer ohne Zugriff) und der Integrationstest mit Versionen-App und Findling sind grün; das Holdout-Gate ist bestanden.
  4. Alle nutzersichtbaren Texte, Pseudonym-Schemata, Protokoll und README liegen in DE, EN und FR im Gleichstand; das Sprach-Gate in CI findet keine fehlenden Texte, ASCII-Ersatzumlaute, Gedankenstriche oder Emojis.
  5. Die gemeinsame UI-Abnahme per Playwright (3 Breiten, hell/dunkel) und der große Volltest DE/EN/FR sind mit dem Owner abgeschlossen.
**Plans**: TBD
**UI hint**: yes
**Research flag**: Standardmuster (AVS-Gates, Release-/Zertifikats-Pipeline); arm64-Tempo (GLiNER2 auf Cortex-A76) ungemessen.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15. Phase 4 läuft begleitend ab Phase 1 und muss vor Abschluss von Phase 6 fertig sein; die `logic/`-Teile von Phase 8 können offline gegen Spike-Daten vorgezogen werden; Phase 9 kann mit Fake-Funden parallel zu Phase 8 beginnen; Phase 14 hängt nur an Phase 4 und 8.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Zwei-App-Gerüst und Integrationsbeweis | 16/21 | In Progress|  |
| 2. Sicherer Dateieingang und Kindprozess-Sandbox | 0/TBD | Not started | - |
| 3. Positionsindex und Dokumentmodell | 0/TBD | Not started | - |
| 4. Testsatz, Leck-Zoo und Eval-Harness | 0/TBD | Not started | - |
| 5. Unabhängiger Leck-Prüfer | 0/TBD | Not started | - |
| 6. Echte Schwärzung Text-PDF | 0/TBD | Not started | - |
| 7. Echte Schwärzung DOCX/ODT und Ausgabe-PDF | 0/TBD | Not started | - |
| 8. Erkennung | 0/TBD | Not started | - |
| 9. Prüfseite | 0/TBD | Not started | - |
| 10. Freigabe und Ablage | 0/TBD | Not started | - |
| 11. Rechtsgrundlagen und Protokoll | 0/TBD | Not started | - |
| 12. Scans und OCR | 0/TBD | Not started | - |
| 13. Pseudonymisierung | 0/TBD | Not started | - |
| 14. EN/FR auf DE-Niveau | 0/TBD | Not started | - |
| 15. Release-Härtung und Volltest | 0/TBD | Not started | - |

---
*Roadmap created: 2026-11-07*
