# Requirements: PII Redaction

**Defined:** 2026-11-07
**Core Value:** Eine Datei aus Nextcloud wird mit einem Klick lokal auf personenbezogene Daten geprüft; nach menschlicher Prüfung entsteht neben dem Original eine geschwärzte oder pseudonymisierte Kopie, in der nachweislich nichts Geschwärztes mehr steckt (Text, Metadaten, Altversionen, OCR-Ebene). Kein Inhalt verlässt den Server.

Quellen: PROJECT.md, research/SUMMARY.md (mit Konfliktauflösung), Spike 06.11.2026 (SPIKE-REPORT.md). Owner-Entscheide vom 06. und 07.11.2026 (alle 14 Empfehlungen der Recherche übernommen).

## v1 Requirements

### Plattform (PLAT)

- [ ] **PLAT-01**: Admin installiert zwei Apps aus dem Store: PHP-App `pii_redaction` und ExApp `pii_redaction_backend`; beide laufen im Lockstep (gleiche Version, Upgrade-Beweis in CI)
- [ ] **PLAT-02**: Admin sieht eine klare Meldung, wenn die Gegen-App fehlt, nicht erreichbar ist oder eine andere Version hat
- [ ] **PLAT-03**: Läuft auf Nextcloud 33, 34 und 35 mit AppAPI/HaRP, amd64 und arm64, nur CPU
- [ ] **PLAT-04**: Kein Dokumentinhalt, kein Fund, keine Telemetrie verlässt den Server; einzige ausgehende Verbindung ist der Modell-Download mit festem sha256 von einer Host-Allowlist; Admin-Ablage für Offline-Instanzen; belegt durch einen CI-Lauf des ganzen Pfads im Container ohne Netz
- [ ] **PLAT-05**: Der Container hat keine Browser-Routen; jede Nutzeranfrage geht über die PHP-App, die bei jeder Anfrage die Rechte an der Originaldatei neu prüft

### Start und Auftrag (JOB)

- [ ] **JOB-01**: Nutzer startet "Schwärzen / Pseudonymisieren" als Dateiaktion in der Dateien-App für PDF, DOCX und ODT
- [ ] **JOB-02**: Die Analyse läuft als Hintergrundauftrag; Nutzer sieht ehrlichen Fortschritt und bekommt eine Benachrichtigung ohne Fundinhalt, wenn die Prüfung bereit ist
- [ ] **JOB-03**: Nur Nutzer mit Leserecht auf die Originaldatei können starten und prüfen (auch Gruppenordner-ACL und Freigaben); eine Freigabe mit Download-Sperre blockiert den Start
- [ ] **JOB-04**: Der Auftrag ist an Datei-ID und Etag gebunden; ändert sich das Original, wird der Auftrag ungültig und das gemeldet
- [ ] **JOB-05**: Verschlüsselte, Ende-zu-Ende-verschlüsselte, defekte oder zu große Dateien (über 300 Seiten) werden mit konkretem Grund abgelehnt; signierte PDFs werden vorher gemeldet (Signatur fällt weg, steht im Protokoll)
- [ ] **JOB-06**: Ein Auftrag zur Zeit je Container, Zulassung über RAM-Wächter; Warteschlange mit sichtbarer Position

### Sicherer Eingang (SAFE)

- [ ] **SAFE-01**: Alle Parser (PDF, ZIP, XML, LibreOffice, OCR) laufen in Kindprozessen ohne AppAPI-Geheimnis in der Umgebung, mit Zeit- und Speichergrenzen und Kill der ganzen Prozessgruppe
- [ ] **SAFE-02**: Vorprüfung vor dem Parsen: Dateityp über Magic-Bytes, Grenzen für Seiten, Objekte, Pixel, ZIP-Größe, Kompressionsrate, Einträge, Pfade und doppelte Namen; XML ohne DOCTYPE und Entitäten
- [ ] **SAFE-03**: Makros und externe Beziehungen werden vor LibreOffice entfernt; ein Test-DOCX mit externem Bild löst keinen Netzaufruf aus
- [ ] **SAFE-04**: Bomben-, XXE-, Doppelnamen- und External-Rels-Korpus läuft in CI und wird abgewiesen, ohne den Container zu gefährden

### Dokumentmodell (DOC)

- [ ] **DOC-01**: Ein einziger Positionsindex je Dokument trägt Anzeige, Suche, Erkennung und Schwärzung (PDF Zeichen-Boxen, DOCX/ODT Textstrom mit Quellanker über alle Teile)
- [ ] **DOC-02**: Text wird normalisiert (Ligaturen, weiche Trennstriche, geschützte Leerzeichen, Nullbreite) und auf Originalpositionen zurückgeführt
- [ ] **DOC-03**: Unsichtbare Inhalte (unsichtbarer oder weißer Text, ausgeschaltete Ebenen, außerhalb des Seitenbereichs, verborgener Text, nicht angezeigte Kopf- und Fußzeilen, Metadaten) werden erkannt und in der Prüfung als Hinweis gezeigt
- [ ] **DOC-04**: Bilder in Text-PDFs werden per OCR in die Erkennung einbezogen

### Erkennung (DET)

- [ ] **DET-01**: Gründlicher Modus ist Standard: Presidio + eigene deutsche Erkenner + spaCy + GLiNER2-PII + Rollenwortfilter + Namensweitergabe im Dokument; Personen-Leckrate auf dem DE-Testsatz höchstens auf Spike-Niveau (1,1 % der PII-Zeichen)
- [ ] **DET-02**: Schnellmodus (ohne GLiNER2) nur als bewusste Wahl mit Hinweis auf die höhere Leckrate
- [ ] **DET-03**: Deutsche IDs mit Prüfziffer werden erkannt (IBAN, Steuer-ID, Steuernummer, Personalausweis, Pass, RV-Nummer, KVNR, Kfz, auch mit Leerzeichen); Fristdaten, Aktenzeichen und PLZ ohne Anschrift werden nicht markiert
- [ ] **DET-04**: Telefon, E-Mail, Anschrift (Straße + Hausnummer, PLZ + Ort), Geburtsdatum mit Kontextwort; Hinweis "Datum in Personenzeile" für Daten ohne Kontextwort
- [ ] **DET-05**: Drei Konfidenzstufen (hoch, mittel, niedrig); niedrige Stufe wird nie automatisch angenommen
- [ ] **DET-06**: Funde werden zu Entitäten gebündelt (eine Person über "Herr Müller", "Müller", "M."); Namen, die zugleich Wörter sind, werden gesondert behandelt
- [ ] **DET-07**: Amtsträger werden als eigene Kategorie erkannt (Bearbeiter im Vorgang, sonstige Bedienstete), bleiben aber bis zur menschlichen Entscheidung geschwärzt
- [ ] **DET-08**: Hinweise statt Versprechen für besondere Kategorien (Art. 9 DSGVO-Begriffe) und Beruf neben Name
- [ ] **DET-09**: Lange Texte werden mit Überlappung gestückelt; stilles Abschneiden durch ein Modell gilt als Fehler
- [ ] **DET-10**: EN und FR mit eigenen Regeln (Aktenzeichen, Anschriften, IDs) und Modellen; Leckrate je Sprache gemessen und als Gate festgehalten

### Prüfseite (REV)

- [ ] **REV-01**: Nutzer prüft auf einer eigenen Seite der PHP-App: Seitenübersicht mit Fundmarkern, Seitenbild mit Kästchen, Entitätenliste nach Kategorie mit Zähler
- [ ] **REV-02**: Nutzer nimmt Funde an, lehnt sie ab oder markiert sie als unsicher, einzeln und "für alle gleichen Funde"; Sammelannahme nur für hohe Konfidenz, mit Anzahl-Bestätigung und Rückgängig
- [ ] **REV-03**: Nutzer sucht Text oder Muster und schwärzt alle Treffer (Umlaut-Varianten, Zeilenumbruch, Silbentrennung)
- [ ] **REV-04**: Nutzer markiert Text von Hand und zieht Flächen (auch ganze Seite), mit Tastaturalternative; Fläche auf DOCX/ODT ergibt nur eine PDF-Ausgabe (Ausnahme: Fläche auf eingebettetem Bild)
- [ ] **REV-05**: Nutzer schaltet zwischen Original und Ergebnis-Vorschau um
- [ ] **REV-06**: Tastaturfluss mit Legende; Einbuchstaben-Kürzel nur bei Fokus in der Liste oder abschaltbar (WCAG 2.1.4)
- [ ] **REV-07**: Zugängliche Textansicht neben dem Seitenbild; Prüfseite erfüllt WCAG 2.1 AA / BITV 2.0, Kategorien nie nur über Farbe
- [ ] **REV-08**: Gleichzeitige Bearbeitung wird erkannt (Revision); kein Fundtext gelangt in HTML ohne Escaping

### Schwärzung und Ausgabe (RED)

- [ ] **RED-01**: PDF: Text, Bildpixel und Vektoren unter jeder Fläche werden entfernt, geteilte Objekte vorher je Seite entflochten, Fonts neu untersetzt, Datei vollständig neu geschrieben (keine Altversion)
- [ ] **RED-02**: PDF-Bereinigung als Allowlist: Metadaten, XMP, Kommentare, Formulare, Anhänge, JavaScript, Lesezeichen, Seitenlabels, benannte Ziele, Strukturbaum, ActualText, Dokument-ID neu
- [ ] **RED-03**: DOCX/ODT: alle Teile per ZIP-Allowlist; Änderungsverfolgung, Kommentare, verborgener Text, Kopf/Fuß aller Varianten, Fußnoten, Felder, Textfeld-Fallback, Datenbindung, customXml, Glossar, Metadaten, Vorschaubilder, Bild-EXIF und Beschnitt, Links, ODT-Bedingungstext und Benutzerfelder
- [ ] **RED-04**: Diagramme, SmartArt und OLE-Objekte werden entfernt und gemeldet
- [ ] **RED-05**: Ausgabe immer zusätzlich als PDF (LibreOffice headless); aus DOCX/ODT als getaggtes, barrierefreies PDF; aus PDF-Quellen als "nicht barrierefrei" ausgewiesen
- [ ] **RED-06**: Gerundete Balkenbreite als Standard; Rechtsgrundlage optional sichtbar im Balken
- [ ] **RED-07**: Modus "Höchste Sicherheit" (Seiten rastern, frische OCR) bewusst wählbar, Folgen erklärt, im Protokoll und Dateinamen kenntlich

### Leck-Nachprüfung (LEAK)

- [ ] **LEAK-01**: Jede Ausgabe wird von einem eigenständigen Prüfer kontrolliert, der keinen Code mit Erkennung oder Schwärzung teilt und kein PyMuPDF nutzt (Importgrenze per Test)
- [ ] **LEAK-02**: Prüfer kombiniert zwei Text-Extraktoren mit unscharfem Abgleich, Rohsuche in allen Kodierungen (rekursiv in eingebetteten Containern), Revisionszählung, OCR mit unabhängigem Renderer, LibreOffice-Textexport und Positionsprüfung für kurze Werte
- [ ] **LEAK-03**: Bei einem Fund entsteht keine Ausgabe (fail-closed, kein Abschaltschalter); das Ergebnis steht im Protokoll
- [ ] **LEAK-04**: Leck-Zoo mit Kanarienwerten je Leckklasse, erzeugt mit fremden Werkzeugen; Mutationstest mit Prüfer-Recall 100 % je Leckklasse ist Release-Gate

### Workflow und Ablage (FLOW)

- [ ] **FLOW-01**: Status Entwurf, geprüft, freigegeben mit Prüfer und Zeitstempel
- [ ] **FLOW-02**: Vier-Augen-Freigabe (zweite Person aus Freigabegruppe, keine Selbstfreigabe, Freigeber braucht Leserecht), per Admin abschaltbar; Freigabe gilt genau für einen Entscheidungsstand
- [ ] **FLOW-03**: Vor der Freigabe zeigt eine Zusammenfassung, was nicht geschwärzt wird (z. B. N Amtsträger)
- [ ] **FLOW-04**: Die Ausgabe entsteht erst nach Freigabe und bestandener Nachprüfung, als Kopie neben dem Original im Namen des Auftraggebers (`_geschwärzt`, `_redacted`, `_caviardé`, `_pseudonymisiert`); nie überschreiben; Original unverändert
- [ ] **FLOW-05**: Liegt der Zielordner in einer Freigabe, bestätigt der Nutzer vor dem Schreiben; Personenbezug in Dateiname oder Ordnerpfad wird gewarnt
- [ ] **FLOW-06**: Prüfzustand mit Klartext liegt nur im Container-Volume, 14 Tage Lebensdauer (verlängerbar), Löschung bei Veröffentlichung, Abbruch, Ablauf, Löschen oder Ändern des Originals; Nextcloud-Datenbank und Logs enthalten nie Fundtext (Kanarien-Scan in CI)

### Rechtsgrundlagen und Protokoll (LEGAL)

- [ ] **LEGAL-01**: Nutzer wählt je Schwärzung eine Rechtsgrundlage aus einem Satz; vorbelegt IFG Bund und Veröffentlichung von Entscheidungen, dazu UIG, VIG
- [ ] **LEGAL-02**: Länder-Sätze werden mitgeliefert und als "juristisch ungeprüft" gekennzeichnet; Admin wählt den Rechtsrahmen beim Einrichten und kann Sätze je Behörde anpassen; Hinweis "keine Rechtsberatung"
- [ ] **LEGAL-03**: Label für bewusstes Nicht-Schwärzen (z. B. § 5 Abs. 4 IFG) wird protokolliert
- [ ] **LEGAL-04**: Schwärzungsprotokoll als PDF und JSON ohne Klartext und ohne Hashes einzelner Werte: Dateihashes, Prüfer, Freigeber, Modus, je Schwärzung lfd. Nr., Seite, Kategorie, Rechtsgrundlage, Herkunft, Konfidenz, Ergebnis der Nachprüfung, Modellversionen; Abruf über die Prüfseite, nicht neben der Kopie
- [ ] **LEGAL-05**: Begründungsliste für den Bescheid (Seite, Umfang, Rechtsgrundlage, Kurzbegründung) als eigene Datei

### Scans (SCAN)

- [ ] **SCAN-01**: Gescannte PDFs werden lokal per OCR (deu/eng/fra) erkannt; OCR-Qualität je Seite ist sichtbar, schlechte Seiten verlangen Sichtung
- [ ] **SCAN-02**: Eine einzige Koordinatenquelle (eigene OCR) für Anzeige und Schwärzung, auch bei gedrehten und schiefen Seiten; Kästchen werden erweitert
- [ ] **SCAN-03**: Alte Textebene wird verworfen, Pixel unter Flächen werden ersetzt, nach dem Schwärzen entsteht eine neue OCR-Ebene aus dem geschwärzten Bild; Pixelprüfung unter jedem Balken
- [ ] **SCAN-04**: Prüfziffer-Erkenner melden auf Scans auch Kandidaten mit fehlerhafter Prüfziffer als "niedrig"

### Pseudonymisierung (PSEU)

- [ ] **PSEU-01**: Nutzer wählt den Modus Pseudonymisieren gleichwertig zum Schwärzen
- [ ] **PSEU-02**: Jede Entität bekommt ein konsistentes Pseudonym über alle Varianten; Standard fortlaufende Buchstaben je Kategorie nach erstem Auftreten ("A.", "B.", "A-Stadt", "A GmbH"), echte Initiale wird übersprungen, nichts aus Hash oder Name abgeleitet; keine Option mit echten Initialen
- [ ] **PSEU-03**: Schema in DE, EN, FR; Flexion wird beachtet (Genitiv, "Herrn", "-sche", Bindestrich, französische Elision)
- [ ] **PSEU-04**: Nutzer kann Entitäten verknüpfen und trennen; Pseudonyme werden dann neu vergeben; unsichere Zuordnungen erscheinen als Fund "Zuordnung prüfen"
- [ ] **PSEU-05**: Ausgabe enthält jedes Pseudonym nachweislich (Positivprüfung) und keinen Originalwert (Nachprüfung); keine gespeicherte Zuordnung nach der Löschung; UI sagt "pseudonymisiert", nie "anonymisiert"

### Modelle und Ressourcen (RES)

- [ ] **RES-01**: Modelle liegen nicht im Image, sondern im persistenten Speicher mit festem sha256; DE-Stapel wird beim Einrichten geladen, EN/FR (französisches Modell zur Laufzeit wegen LGPL-LR) bei Bedarf
- [ ] **RES-02**: Versteckte Netzaufrufe der Bibliotheken sind abgestellt (Modell-Nachladen, Public Suffix List, Remote-Config)
- [ ] **RES-03**: RAM-Wächter lässt Erkenner (ca. 4 GB) und LibreOffice nie gleichzeitig laufen; Erkenner bleibt warm, solange Arbeit ansteht, und endet im Leerlauf

### Admin und Zustände (ADM)

- [ ] **ADM-01**: Admin sieht Zustand beider Apps, Modelle, Warteschlange und Fehlgründe ohne Dateinamen und ohne Inhalt
- [ ] **ADM-02**: Admin stellt Vier-Augen-Pflicht, Freigabegruppe, Rechtsrahmen, Standardmodus und Lebensdauer des Prüfzustands ein

### Qualität und Release (REL)

- [ ] **REL-01**: Eigener Testsatz mit Leckrate (Zeichen) und Anteil Dokumente mit Leck als Hauptkennzahlen, je Kategorie, Format und Dokumenttyp; Recall nach Namensherkunft; Holdout von anderer Hand
- [ ] **REL-02**: Ende-zu-Ende-Lecktest in CI über alle Formate; Release-Gate vor jedem Store-Release
- [ ] **REL-03**: Gemessen im Container: Image-Größe, RAM, Laufzeit je Seite auf amd64 und arm64
- [ ] **REL-04**: Sicherheitsaudit mit Negativtests (Rechteentzug, Etag-Wechsel, Download-Sperre, Zweitprüfer ohne Zugriff) und Integrationstest mit Versionen-App und Findling
- [ ] **REL-05**: Gemeinsame UI-Abnahme per Playwright (3 Breiten, hell/dunkel) und großer Volltest DE/EN/FR vor Store-Release

### Sprache und Texte (I18N)

- [ ] **I18N-01**: Alle nutzersichtbaren Texte, Pseudonym-Schemata, Protokoll und README in DE, EN, FR im Gleichstand, Deutsch zuerst, echte Umlaute, keine Gedankenstriche, keine Emojis (Test)

## v2 Requirements

### Erweiterungen

- **V2-01**: Eigenes feinjustiertes deutsches Erkennungsmodell auf Behörden- und Urteilstexten (Owner 07.11.; braucht Goldstandard, FAU/ALeKS angefragt)
- **V2-02**: Rollen-Pseudonyme aus dem Rubrum ("Kläger", "Beklagte 1", "Zeuge 1")
- **V2-03**: Gleiche Pseudonyme über einen Vorgang mit mehreren Dateien
- **V2-04**: Stapel-Analyse eines Ordners (Prüfung weiter je Datei)
- **V2-05**: Barrierefreie Ausgabe aus getaggten PDF-Quellen (Platzhalter-Tags), Synergie mit PDF Accessibility
- **V2-06**: Glyphen-Normalisierung ohne Rastern gegen Positionslecks
- **V2-07**: Unterschrift-, Stempel- und Gesichtserkennung
- **V2-08**: Fristen und Drittbeteiligung nach § 8 IFG
- **V2-09**: Weitere Formate (XLSX, PPTX, E-Mail, Bilder)
- **V2-10**: Label-Import und -Export, Prüfexemplar (audit copy)
- **V2-11**: Diagramme, SmartArt, OLE schwärzen statt entfernen

## Out of Scope

| Feature | Reason |
|---------|--------|
| Inhalte an externe Dienste (Cloud-Erkennung, Cloud-OCR, LLM-APIs, externe Embeddings) | Owner-Regel Datenschutz zuerst |
| Vollautomatische Schwärzung ohne Prüfung | Kein Anbieter mit Behördenbezug macht das; AWS-Pilot 5 % Fehler bei "sicheren" Fällen |
| Overlay-Annotationen als Ausgabe | Epstein-/Manafort-Fehler |
| Echte Initialen als Pseudonym | Am leichtesten zu knacken (USENIX Security 2023), Owner 07.11. |
| Umkehrbare Pseudonymisierung mit gespeicherter Zuordnung | Zuordnung wäre selbst ein Leck |
| Hashes einzelner Werte im Protokoll | Per Wörterbuch umkehrbar, Owner 07.11. |
| Flair im Auslieferpfad | Lizenz ungeklärt, 7,2 GB RAM, 42 s/Seite |
| Generatives LLM als Haupterkenner | Keine stabilen Offsets, CPU-Laufzeit |
| Rechtsberatung in der App | Haftung; nur Label-Sätze mit Hinweis |
| Rastern als Standard | Zerstört Barrierefreiheit, 3 bis 6-fache Größe |
| Teilen oder Ablegen vor Abschluss | Entwurf wäre über Freigaben, Versionen und Suche sichtbar |
| Geschwärzte Dokumente als Trainingsdaten weitergeben | Datenschutzregel |

## Traceability

(wird bei der Roadmap-Erstellung gefüllt)

---
*Requirements defined: 2026-11-07*
