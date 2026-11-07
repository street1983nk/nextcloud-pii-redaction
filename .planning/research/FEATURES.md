# Feature Research

**Domain:** Lokale Erkennung und Schwärzung/Pseudonymisierung personenbezogener Daten in PDF, DOCX und ODT als Nextcloud-App (Behörden: IFG-Herausgaben, Veröffentlichung von Gerichtsentscheidungen; Schulen; kleine Organisationen)
**Researched:** 07.11.2026
**Confidence:** MEDIUM (Produktfunktionen der Wettbewerber überwiegend aus Herstellerseiten; JANO-Oberfläche aus Primärquelle belegt; Paragrafen IFG Bund HIGH, Länder MEDIUM bis LOW, siehe Abschnitt "Rechtsgrundlagen-Labels")

Ergänzt die Marktrecherche vom 04.11.2026 (`neue-apps-recherche-2026-11-04/bigtech-pii-redaction-2026-11-04.md`) und den Spike vom 06.11.2026. Dort Belegtes (Purview, Presidio, AWS, Google DLP, Epstein/Manafort, PoPETs 2023, FAU-Zahlen) wird hier nicht wiederholt, nur referenziert. Feststehende Owner-Entscheidungen aus PROJECT.md gelten als gesetzt; dieses Dokument ordnet sie ein und ergänzt, was für Anforderungen noch fehlt.

---

## 0. Neue Befunde gegenüber der Recherche vom 04.11.

| Befund | Beleg | Folge für Anforderungen |
|---|---|---|
| **JANO-Oberfläche** (Primärquelle, Folien 8 und 9): Dokumentansicht mit farbigen Markierungen je Kategorie (Namen blau, Anschriften rot, Kanzlei/Organisation violett, Aktenzeichen grau); rechte Liste **gruppiert nach Kategorie mit Anzahl** ("Namen (10)"), je Zeile: Fundtext, Vorkommen "(11)", Pfeil, Ersetzungstext, Löschen, Auswahlkästchen; oben Eingabezeile "Eingabe für ausgewählten Text -> Ersetzungstext"; Symbol zum Verknüpfen. Schwärzungsmodus zeigt "XXXXXX", Ersetzungsmodus **rollenbasierte Pseudonyme**: "Kläger", "Beklagte 1", "Beklagte 2", "Zeuge 1", "Person 1", "Richtername 1" | Präsentation Hess. Justizministerium, 51. AK Informationsfreiheit, 21.04.2026, lda.brandenburg.de (PDF lokal ausgewertet) | Vorschlagsliste **je Entität (Cluster) statt je Vorkommen**, mit Zähler; Verknüpfen/Trennen von Clustern; Pseudonym je Cluster editierbar. Farbe allein reicht nicht (WCAG 1.4.1), Kategorie zusätzlich als Text/Symbol |
| **Initialen sind die schwächste Anonymisierungstechnik** in deutschen Urteilen: 54 Jurastudierende, 50 Entscheidungen, alle Techniken angreifbar, "most notably the use of initials" | Deuber, Keuchen, Christin, USENIX Security 2023 (Abstract) | Pseudonym-Schema darf **standardmäßig keine echten Initialen** verwenden; fortlaufende Buchstaben in Reihenfolge des Auftretens oder Rollen |
| **FAU-Tagset** für Urteile: Kategorien Formales (Az., Gericht), Natürliche Person (Name, juristische Funktionsträger, Sonstiges), Juristische Person, Adresse/Ortsangabe, Datum, Fahrzeug (Kennzeichen, Fahrgestellnummer), Immaterialgut, Kontaktdaten, Geschäftszeichen, plus Merkmale je Fund: **Risikoniveau hoch/mittel/niedrig, "Informationserhaltung notwendig", "unsicher/diskussionswürdig"**; FAU fordert > 99 % Recall für PII, AG-Modell erreicht Recall (PII) 99,16 % | Doan Dang, Werner, FAU, Folien "Wie robust ist die vollautomatische Anonymisierung", AnGer 2025 (PDF lokal ausgewertet) | Fundstatus "unsicher, zweite Meinung" als eigener Zustand im Vier-Augen-Ablauf; Kategorie Fahrzeug-Identnummer (FIN) ergänzen |
| **Conduction hat umbenannt**: DocuDesk-Funktionen heißen jetzt "Filinq", OpenAnonymiser heißt "Anonymiq" (Beta, niederländisch zuerst, Presidio, EUPL-1.2, ExApp Light/CPU und GPU). Filinq-Ablauf: Tabelle mit Typ, Konfidenz, Kontextausschnitt; je Zeile **Accept / Reject / Edit**; Ersatz durch Typ-Platzhalter `[PERSON]`; PDFs mit komplexem Layout **fallen auf Klartext-Export zurück**, nur DOCX layouttreu; keine Rechtsgrundlagen-Labels und kein Woo-Grund dokumentiert | filinq.conduction.nl/docs/tutorials/user/anonymise-document, conduction.nl/solutions/openanonymiser, abgerufen 07.11.2026 (Herstellerangaben) | Abgrenzung schärfer: wir liefern layouttreues PDF mit echter Schwärzung, deutsche Rechtsgrundlagen, Leck-Nachprüfung. Typ-Platzhalter `[PERSON]` ist für Urteile zu grob (keine Unterscheidung mehrerer Personen) |
| **Objective Redact**: immer Arbeitskopie, Original unverändert; "final redacted copy" plus optionale **"audit copy"**; Freigabe durch Team vor Finalisieren; Ausnahme-Code-Gruppen je Rechtsordnung (AU, NZ, UK), eigene Codes; Bericht der verwendeten Codes; Muster inkl. Text in Klammern; Stapel über Ein-/Ausgabeordner und Vorlagen; **Durchsuchbarkeit des Ergebnisses beim Finalisieren umschaltbar** | objective.com/products/objective-redact und Blog-Update, abgerufen 07.11.2026 (Herstellerangaben) | Prüfexemplar (Akte, mit sichtbaren halbtransparenten Markierungen und Labels) als eigenes Ausgabeartefakt erwägen; Code-Gruppen je Rechtsordnung = unsere Label-Sätze je Bund/Land |
| **Redactable**: Grund je Schwärzung (FOIA-Ausnahmen, HIPAA, Privileg, eigene), Grund auch bei Such- und KI-Funden, **"Find and replace" sucht, vergibt Grund, schwärzt alle Vorkommen in einem Schritt**, Entwurfsmodus, nach Finalisieren **Zertifikat** mit Anzahl, Seiten, Nutzer, Zeitstempel, Grund je Schwärzung; Metadaten- und Objektentfernung; RBAC, Kommentare, Aufgaben | redactable.com/redaction-reasons und /features, abgerufen 07.11.2026 (Herstellerangaben) | Bestätigt: Grund je Fund, Grund bei Sammelaktion vergeben, Protokoll als Abschlussdokument |
| **Acrobat**: Überlagerungstext je Schwärzung, "Auto-Size" und "Repeat Overlay Text"; Schwärzungscodes = vordefinierte Texte mit Grund oder Norm, Code-Sätze US FOIA/Privacy Act, eigene Sätze anlegbar | helpx.adobe.com Text redaction properties; Adobe Acrobat X Redaction Guide, abgerufen 07.11.2026 | Label im Balken optional, automatisch skaliert; Label-Sätze als bearbeitbare Code-Sätze |
| **Keine dokumentierten Tastenkürzel** für Annehmen/Ablehnen bei Relativity, CaseGuard, Redactable, Objective (gesucht, nicht gefunden). Relativity: Kürzel für Ganzseitenschwärzung, Kürzel-Legende im Viewer, Kürzel nur aktiv bei Fokus im Prüfbereich | help.relativity.com Markups und Keyboard shortcuts, abgerufen 07.11.2026 | Tastaturfluss ist **Differenzierung**, nicht Branchenstandard; Gestaltung siehe Abschnitt "Prüf-UI im Detail" |
| **Barrierefreie Schwärzung im PDF**: Schwärzungsfläche als Figure mit Alternativtext ("Redacted text") taggen, an richtiger Stelle der Lesereihenfolge, umgebendes Tag teilen; Acrobat entfernt geschwärzten Text aus Tag- und Inhaltsbaum, setzt aber keinen Platzhalter | Allyant/CommonLook Support-Artikel; WebAIM-Liste 2013; DHS-Memo 2010, abgerufen 07.11.2026 | Ausgabe-PDF braucht Platzhalter-Tag mit Alt-Text "Geschwärzt (Rechtsgrundlage)"; Strukturbaum ist zugleich **Leckquelle** (Alt, ActualText) |
| **BITV 2.0** regelt PDF nicht im Detail, verweist auf EN 301 549; PDF/UA (DIN ISO 14289) gilt in Bundesleitfäden als Weg zur Konformität, Prüfung mit PAC/Matterhorn | BMUV-Leitfaden barrierefreie PDF 11/2023; Bundestag-Handreichung 09/2024; vergabeblog 21.08.2025, abgerufen 07.11.2026 | Ausgabe-PDF für Veröffentlichung sollte PDF/UA-tauglich sein, wo die Quelle es war; Rastermodus zerstört das (Spike 5.1) |

---

## Feature Landscape

### Table Stakes (Users Expect These)

Ohne diese Funktionen ist das Produkt für Behörden nicht einsetzbar. Spalte "Owner" = bereits in PROJECT.md entschieden.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Arbeiten auf Kopie, Original unverändert, Ergebnis neben dem Original** | Acrobat, Purview, Objective, Filinq: alle | LOW | Owner. Schreiben erst nach Freigabe (sonst sehen Freigabe-Empfänger des Ordners einen Entwurf). Dateinamen-Warnung bei Personenbezug |
| **Echte Entfernung + Bereinigung (Sanitize) + vollständiges Neuschreiben** | Acrobat-Sanitize ist Maßstab; Redactable, Objective werben damit | HIGH | Owner; Spike: 0/88 Lecks. Ergänzung: **Strukturbaum (StructTreeRoot), /Alt, /ActualText, /T von Strukturelementen** gezielt prüfen und bereinigen; im Spike nicht getestet (LOW, unverifiziert ob PyMuPDF `apply_redactions` diese Einträge anfasst) |
| **Vorschlagsliste mit Annehmen/Ablehnen je Fund** | Filinq, JANO, Redactable, Blackout | MEDIUM | Owner. Zustände: offen, angenommen, abgelehnt, **unsicher (zweite Meinung)** |
| **Annehmen/Ablehnen "für alle gleichen Funde" (Cluster)** | JANO gruppiert je Entität mit Zähler; Acrobat "Suchen und alles schwärzen" | MEDIUM | Owner. Liste je Entität (wie JANO) mit aufklappbaren Vorkommen; Einzelvorkommen abweichend entscheidbar |
| **Suchen und alles schwärzen** | Acrobat, Redactable, Objective, CaseGuard, Smallpdf (nur kostenpflichtig) | MEDIUM | Owner. Wortgrenzen, Groß/klein ignorieren, Umlaut-Varianten (ü/ue), Treffer über Zeilenumbruch und Silbentrennung; Regex nur für Fortgeschrittene; Grund beim Sammelvorgang vergeben (Redactable) |
| **Manuelle Flächenschwärzung** | Purview Area redaction, Objective Rechteck, Acrobat | MEDIUM | Owner. Pflicht für Unterschriften, Stempel, Fotos, Logos in Scans. **Konflikt**: bei DOCX/ODT-Quelle gilt Fläche nur für die PDF-Ausgabe (siehe Abhängigkeiten) |
| **Manuelle Textmarkierung** (Text im Dokument auswählen -> schwärzen) | JANO "Eingabe für ausgewählten Text", Acrobat | MEDIUM | Fängt, was die Erkennung verpasst; erzeugt automatisch Cluster-Vorschlag für weitere Vorkommen |
| **Konfidenz sichtbar, niedrige Stufe nie automatisch angenommen** | Filinq zeigt Konfidenz; Purview 65/75/85; Anonymiq "review or auto-redact" | LOW | Owner (drei Stufen). Als Wort anzeigen, nicht nur Farbe |
| **OCR für Scans** | Redactable, Objective, CaseGuard, Smallpdf werben alle damit | HIGH | Owner. OCR-Qualität je Seite anzeigen (Tesseract-Konfidenz), schlechte Seiten markieren: dort ist die Erkennung blind |
| **Rechtsgrund/Code je Schwärzung, konfigurierbare Code-Sätze** | Acrobat (FOIA/Privacy Act), Objective (Code-Gruppen je Land), Redactable, Casepoint | MEDIUM | Owner. Deutscher Vorbelegungssatz siehe unten; Grund auch im Protokoll |
| **Protokoll/Zertifikat nach Abschluss** | Redactable-Zertifikat, Objective-Bericht, Legiscope-Abschlussakte | MEDIUM | Owner (PDF + JSON, ohne Klartext). Inhalt siehe "Schwärzungsprotokoll und Begründungsliste" |
| **Zwei Modi Schwärzen / Ersetzen** | JANO (Schwärzungs- oder Ersetzungsmodus), Filinq (Platzhalter), Anonymiq (replace, mask, hash, redact) | HIGH | Owner. Für Gerichtsentscheidungen ist Ersetzen der Normalfall |
| **Ausgabe mindestens als PDF** | Purview erzeugt immer PDF; Objective PDF/TIFF | MEDIUM | Owner (LibreOffice headless) |
| **Fortschritt und Fehlgrund bei langen Aufträgen** | 8 bis 11 s/Seite (Spike) | LOW | Owner. Nextcloud-Benachrichtigung bei Fertig |
| **Zugriff nur für Berechtigte der Originaldatei** | Redactable RBAC; Datenschutz | MEDIUM | Owner. Gilt auch für Seitenbilder der Prüfseite (keine öffentlichen Vorschau-Caches) |
| **Prüf-UI barrierefrei nach BITV 2.0 / EN 301 549 (WCAG 2.1 AA)** | Für öffentliche Stellen gesetzliche Pflicht bei interner Software ebenfalls üblich gefordert (Vergabe) | MEDIUM | Nicht in PROJECT.md als eigene Zeile. Siehe "Barrierefreiheit". Nextcloud-Vue-Komponenten helfen, die Dokumentansicht mit Markierungen ist der schwierige Teil |

### Differentiators (Competitive Advantage)

Ausgerichtet auf den Core Value (lokal, nachweislich nichts mehr drin) und die Zielgruppe deutsche Behörden.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Automatische Leck-Nachprüfung mit Bericht, blockiert bei Fund** | Kein untersuchter Anbieter dokumentiert eine unabhängige Nachprüfung; Redactable nennt nur "certificate" | HIGH | Owner. Ergebnis sichtbar im Protokoll ("4 Prüfer, 0 Funde"); bei Fund: welche Seite, welche Kategorie, nicht der Klartext in Logs |
| **Deutsche Rechtsgrundlagen-Sätze Bund + Länder, vorbelegt** | Acrobat/Redactable haben US-FOIA, Objective AU/NZ/UK, Conduction nichts dokumentiert | MEDIUM | Owner. Daten statt Code, versioniert, je Behörde/Gruppe überschreibbar; Labels für bewusstes **Nicht**-Schwärzen (§ 5 Abs. 4 IFG) |
| **Amtsträger-Kategorie mit protokollierter Entscheidung "offen gelassen nach § 5 Abs. 4 IFG"** | Überschwärzung ist bei IFG ein Rechtsfehler; kein Wettbewerber unterscheidet | MEDIUM | Owner (bis Prüfung geschwärzt). Ergänzung: Freigabe als Amtsträger wird mit Label protokolliert, damit die Begründungsliste auch Nicht-Schwärzungen erklärt |
| **Konsistente Pseudonyme je Person über Varianten, mit wählbarem Schema** | JANO "verknüpfende Ersetzung"; Filinq nur `[PERSON]` | HIGH | Owner. Schemata siehe "Pseudonym-Schemata". Standard **ohne echte Initialen** (USENIX 2023) |
| **Rollenbasierte Pseudonyme für Urteile** ("Kläger", "Beklagte zu 1", "Zeugin 2") | Genau so in JANO; lesbarer als Buchstaben | HIGH | Rollenerkennung aus Rubrum ("- Kläger -", "gegen", "1.", "2.") per Regeln; Fallback Buchstabe. v1.x, wenn Buchstaben-Schema steht |
| **Begründungsliste zum Anhängen an den Bescheid** (Seite, Stelle, Rechtsgrundlage, Kurzbegründung) | Entspricht UK/US-Praxis "redaction log"/Vaughn index; Antragsteller haben Anspruch auf Begründung von Teilablehnungen | MEDIUM | Recherche 04.11. sah das als "später"; da Labels in v1 kommen, ist die Liste ein billiges Nebenprodukt (Export aus Protokoll ohne Hashes, ohne Klartext). Empfehlung: **v1** |
| **Vier-Augen-Freigabe mit Rollen** (Bearbeiter markiert, Zweitprüfer gibt frei) | Objective "circulate working copy, when approved finalise"; Justiz trennt Richter/Servicekraft; Legiscope zweite Person | HIGH | Owner (v1, abschaltbar). Zweitprüfer sieht Prüfexemplar oder Prüfseite im Lesemodus, kann Funde zurückweisen mit Kommentar |
| **Prüfexemplar ("audit copy")** für die Akte: Original mit halbtransparenten Markierungen und Labels, nur mit Originalrechten | Objective Redact bietet es; nützlich für Gerichtsverfahren (In-camera-Prüfung), Widerspruch, Zweitprüfung | MEDIUM | Enthält PII, also nur neben dem Original und mit dessen Rechten; nie teilen. v1.x |
| **Tastaturfluss für die Prüfung** | Bei keinem Anbieter dokumentiert; Prüfarbeit ist bei Präzision 0,58 bis 0,66 (Spike) Hauptaufwand: ca. 8 unnötige von 23 Funden je Dokument | MEDIUM | Siehe "Prüf-UI im Detail"; WCAG 2.1.4 beachten |
| **Seitenübersicht mit Fundmarkern** | Schnelle Orientierung bei 50+ Seiten, zeigt Seiten ohne Funde und Seiten mit schlechter OCR | MEDIUM | Thumbnails serverseitig gerendert, nur temporär |
| **Vorher/Nachher nebeneinander** | Bei Pseudonymisierung unverzichtbar, um Lesbarkeit zu prüfen ("Kläger A. hat mit B. ..."); Objective lässt Ansicht vor/nach Ausgabe wählen | MEDIUM | Nachher-Ansicht als Textvorschau (billig) in v1, gerenderte PDF-Vorschau v1.x |
| **Offene Qualitätszahlen (Leckrate je Kategorie)** | Kein Anbieter veröffentlicht deutsche Zahlen (Recherche 5.1) | MEDIUM | Owner (Testsatz, Release-Gate). Im Store-Text und in der App-Hilfe |
| **Barrierefreies Ausgabe-PDF** (Platzhalter-Tag "Geschwärzt, § 5 Abs. 1 IFG", Lesereihenfolge erhalten) | Kein untersuchter Anbieter wirbt damit; Behörden müssen veröffentlichte Dokumente barrierefrei anbieten | HIGH | DOCX/ODT-Weg ist natürlich barrierefreier: Ersatztext im XML, dann LibreOffice-Export mit Tags. PDF-Quelle mit Strukturbaum: aufwendig. Empfehlung: DOCX/ODT-Weg v1, PDF-Quelle v2 |
| **Nextcloud-Integration**: Dateiaktion, Benachrichtigung, Aktivität, Gruppenrechte | Conduction als einziger Nextcloud-Mitbewerber, aber niederländisch und ohne echte PDF-Schwärzung | MEDIUM | Owner |
| **Hinweise statt Versprechen** für schwer Erkennbares: "Datum in Personenzeile", "Gesundheitsbegriff gefunden (Art. 9 DSGVO)", "Beruf/Funktion neben Name" | FAU: Pseudoidentifikatoren (Beruf, Titel, Gesundheit, "einziges rotes Haus") sind Hauptrisiko bei Urteilen; NER ignoriert sie | MEDIUM | Owner (Datum-Hinweis in v1). Als Hinweis-Kategorie mit eigener Farbe/Symbol, nie automatisch geschwärzt |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Vollautomatisch schwärzen ohne Prüfung, "auto-redact high confidence" | Anonymiq bietet "auto-redact"; spart Zeit | AWS-Pilot 5 % Fehler bei "sicheren" Fällen; Spike: Amtsträger-Regel nimmt 2/566 Privatpersonen aus; FAU: 5 % Fehler = 75.000 DSGVO-Fälle/Jahr | Hohe Konfidenz **vorausgewählt**, aber Abschluss nur mit menschlicher Bestätigung; Sammelannahme je Kategorie erlaubt |
| Nur Overlay/Annotation ausliefern ("schneller, Original bleibt editierbar") | Einfach, reversibel | Epstein, Manafort; Spike: 84/88 Lecks | Prüfzustand in der App-DB, Ausgabe nur echt geschwärzt |
| Echte Initialen als Pseudonym ("Kläger M." für Müller) | Üblich in Urteilen, wirkt natürlich | USENIX 2023: Initialen am leichtesten deanonymisierbar | Fortlaufende Buchstaben in Auftretensreihenfolge (A., B., C.) oder Rollen; echte Initialen nur als bewusste Option mit Warnhinweis |
| Typ-Platzhalter ohne Zähler (`[PERSON]`, `[Name]` für alle) | Einfach (Filinq-Standard) | Mehrere Personen werden ununterscheidbar, Urteil unlesbar | `[Name 1]`, `[Name 2]` oder A./B.; `[Name]` nur als Schwärzungstext, nicht als Pseudonym |
| Umkehrbare Pseudonymisierung mit gespeicherter Zuordnung ("De-Anonymisierung", Conduction bietet "replacement keys") | Wunsch nach Rückverfolgung | Zuordnungstabelle ist selbst eine PII-Sammlung; Ausgabe gilt dann nur als pseudonym, nicht anonym (DSGVO EG 26) | Zuordnung nur im Prüfzustand mit begrenzter Lebensdauer; Original bleibt die Rückverfolgung |
| Cloud-OCR oder LLM-API "für bessere Qualität" | Bessere Erkennung | Owner-Regel: nichts verlässt den Server | Lokale Modelle, Qualitätszahlen offenlegen |
| Rechtsberatung in der App ("App entscheidet, ob § 6 greift") | Nutzer wollen Sicherheit | Uneinheitliche Rechtsprechung (BVerwG eng vs. OVG weiter), Haftung | Labels als Auswahl mit Paragrafenbezug und Kurztext, Entscheidung beim Menschen, Hinweis "keine Rechtsberatung" |
| Klartext-PII im Protokoll ("damit man nachvollziehen kann, was weg ist") | Nachvollziehbarkeit | Protokoll wird selbst zum Leck, wird oft mit dem Bescheid verschickt | Hash, Kategorie, Seite, Position, Label; Klartext nur im Prüfexemplar neben dem Original |
| Standardmäßiges Rastern aller Seiten ("am sichersten") | Schützt gegen Glyphen-Leck | Text weg, nicht barrierefrei (BITV), 3,4 bis 6,3-fache Größe (Spike) | Rastermodus wählbar (Owner), Standard: echte Entfernung + gerundete Balkenbreite |
| Schwärzungsgrund im Balken standardmäßig an | Transparenz | Text im Balken kann Balkenbreite für Zeichenzahl verraten bzw. macht kurze Schwärzungen breiter; nicht jede Behörde will das | Optional (Owner), auto-skaliert wie Acrobat "Auto-Size", Balken auf Mindestbreite runden |
| Direktes Teilen/Mailen des Ergebnisses aus der App heraus vor Abschluss | Komfort | Umgeht Vier-Augen-Freigabe; Ergebnis vor Nachprüfung im Umlauf | Datei entsteht erst nach Freigabe und bestandener Nachprüfung; Teilen dann über normale Nextcloud-Freigabe |
| PII-Hervorhebung direkt in der Dateiliste/Vorschau von Nextcloud | "Sofort sehen, wo PII ist" | Würde Funde an Stellen zeigen, wo Freigabe-Empfänger sie sehen | Nur auf der Prüfseite mit Rechteprüfung |
| Stapel ohne Einzelprüfung ("Ordner mit 500 Dateien durchschwärzen") | CaseGuard, Objective bieten Stapel | Spike: 8 bis 11 s/Seite, 4 GB RAM; ohne Prüfung Anti-Feature 1 | v1: Einzeldatei; v1.x: Stapel-**Analyse** im Hintergrund, Prüfung weiterhin je Datei |
| Geschwärzte Dokumente zum Training sammeln (JANO-Perspektive) | Modellverbesserung | Owner-Datenschutzregel | Nicht anbieten; höchstens später lokales Opt-in mit synthetischen Ersatzwerten |

---

## Prüf-UI im Detail

### Aufbau (empfohlen)

Drei Bereiche, auf schmalen Bildschirmen umschaltbar statt nebeneinander:

1. **Seitenleiste links: Seitenübersicht** mit Miniaturen, je Seite Anzahl offener Funde, Symbol für "OCR schwach" und "manuelle Fläche". Komplexität MEDIUM; braucht serverseitiges Rendern der Seiten (PyMuPDF), kurzlebig, rechtegeprüft.
2. **Mitte: Dokumentansicht** (gerenderte Seite mit Markierungsebene). Markierung je Kategorie mit Farbe **und** Muster/Kürzel (WCAG 1.4.1), Zustand sichtbar (offen: Rahmen, angenommen: gefüllt, abgelehnt: durchgestrichen). Klick auf Markierung fokussiert den Eintrag in der Liste. Komplexität HIGH (Koordinaten aus Textindex, Zoom, Scans).
3. **Rechts: Vorschlagsliste** gruppiert nach Kategorie, darin je Entität (Cluster) mit Vorkommen-Zähler wie JANO, aufklappbar zu Einzelvorkommen mit Kontextausschnitt und Seite. Je Eintrag: Konfidenzwort, Label (Rechtsgrundlage), im Ersetzungsmodus Pseudonym-Feld. Filter: offen / unsicher / niedrige Konfidenz / Amtsträger / Hinweise.

Vorher/Nachher: Umschalter "Original | Ergebnis" in der Mitte; im Ersetzungsmodus zusätzlich Textvorschau des Ergebnisses. Seitengleiche Nebeneinander-Ansicht erst v1.x.

### Tastaturfluss (Vorschlag, kein Branchenstandard belegt)

| Taste | Aktion | Hinweis |
|---|---|---|
| J / K oder Pfeil runter/hoch | Nächster/vorheriger Fund (Liste und Dokument scrollen mit) | |
| N | Nächster **offener** Fund | Kernschleife |
| A | Annehmen (Fund) | |
| R | Ablehnen | |
| U | Als "unsicher" markieren (geht an Zweitprüfer) | FAU-Merkmal "diskussionswürdig" |
| Umschalt+A / Umschalt+R | Für alle gleichen Funde (ganzer Cluster) | |
| L | Label wählen (Liste öffnet, Tippen filtert) | |
| E | Pseudonym bearbeiten | nur Ersetzungsmodus |
| Strg+F | Suchen und schwärzen | Browser-Suche nicht kapern? Besser eigener Knopf plus `/` |
| G dann Seitenzahl | Gehe zu Seite | |
| Strg+Z / Strg+Umschalt+Z | Rückgängig / Wiederholen | Entscheidungen sind billig rückgängig zu machen, das senkt Angst vor Sammelaktionen |
| ? | Kürzel-Legende | wie Relativity |

**WCAG 2.1.4 (Character Key Shortcuts)**: Einbuchstaben-Kürzel kollidieren mit Screenreader-Befehlen. Pflicht: abschaltbar oder umbelegbar, oder nur aktiv, wenn der Fokus in der Vorschlagsliste liegt (wie Relativity). Empfehlung: nur bei Fokus in der Liste aktiv **und** in den persönlichen Einstellungen abschaltbar.

### Sammelaktionen

- Je Cluster annehmen/ablehnen (Owner).
- Je Kategorie: "Alle hohen Konfidenzen dieser Kategorie annehmen" (nur hoch, nie niedrig).
- Auswahlkästchen + Sammelaktion für beliebige Funde (JANO hat Kästchen je Zeile).
- Jede Sammelaktion zeigt vorher die Anzahl ("37 Vorkommen auf 12 Seiten annehmen?") und ist rückgängig machbar.
- Abschlussbedingung: keine offenen Funde mehr, alle niedrigen Konfidenzen einzeln entschieden, alle "unsicher" vom Zweitprüfer entschieden (bei Vier-Augen).

### Suchen und schwärzen

- Freitext, Groß/klein egal, ganze Wörter, Umlaut-Varianten (Müller, Mueller, MÜLLER), Treffer über Zeilenumbruch und Trennstrich; Trefferliste mit Kontext, einzeln abwählbar (Acrobat-Muster).
- Vordefinierte Muster zusätzlich zur Erkennung: E-Mail, Telefon, IBAN, Datum, Text in Klammern (Objective), Regex für Fortgeschrittene.
- Gefundene Treffer werden ein neuer Cluster mit Label, damit sie im Protokoll erscheinen.
- Abhängigkeit: Positions-Textindex der Seite (gleicher Index wie Schwärzung, Spike 5.1), bei Scans OCR-Wortboxen.

### Flächenschwärzung

- Rechteck ziehen mit Maus; **Tastaturalternative** (WCAG 2.1.1): Fläche über Dialog "ganze Seite", "Bild auswählen" (Bildobjekte der Seite als fokussierbare Ziele) oder Koordinaten nudgen mit Pfeiltasten.
- Ganzseitenschwärzung als eigene Aktion (Relativity bietet dafür ein Kürzel), z. B. für Anlagen, die komplett unter § 6 IFG fallen.
- Bei DOCX/ODT-Quelle: Fläche wirkt nur auf die PDF-Ausgabe; die DOCX/ODT-Ausgabe wird dann **nicht** erzeugt oder mit klarer Warnung, weil Flächen nicht auf XML abbildbar sind (eingebettete Bilder ausgenommen: dort Bild ersetzen).

---

## Pseudonym-Schemata

### Was die Praxis zeigt (Belege)

| Quelle | Personen | Orte/Anschriften | Firmen | Was bleibt | Beleg |
|---|---|---|---|---|---|
| BGH (VI ZR 157/24, 31.03.2026) | Rollen ("die Klägerin"), Initialen "H. F.", Vorname gekürzt "H." | Auslassung "[…]" (Klinik, URLs "https://[…]") | Beklagte (Verlag) bleibt | Gericht, Az., Datum, Richter-Nachnamen | omnilex.ai Volltext, abgerufen 07.11.2026 |
| LSG Bayern (L 8 SO 155/22, 13.07.2023) | Rolle ("die Klägerin"), Einzelbuchstabe ohne Punkt "Herrn A" | Einzelbuchstabe "in L", "nach S in den Landkreis L", "in der A Straße" | "Firma E" | Daten, Az., Gerichte, Großstadt Augsburg | gesetze-bayern.de, abgerufen 07.11.2026 |
| JANO (Hessen/BW) | Rollen mit Zähler "Kläger", "Beklagte 1", "Zeuge 1", "Person 1", "Richtername 1"; Schwärzungsmodus "XXXXXX" | im Screenshot nicht sichtbar | "Beklagte 2" (Versicherung AG) | k. A. | JANO-Folien 21.04.2026 |
| Schweiz (BGer) | A.____, B.____ in Reihenfolge des Auftretens | Straße als Platzhalter, PLZ und Ort bleiben | | | Suchergebnis zu bger.ch Anonymisierungsregeln (Seite selbst wegen Zertifikatsfehler nicht abrufbar, LOW) |
| Österreich (OGH) | fortlaufender Buchstabe mit Stern "A*", "beklagte Partei B*" | Buchstaben/Ziffern/Abkürzungen, Nachvollziehbarkeit erhalten | | | Suchergebnis jusline.at (MEDIUM) |
| EuGH (seit 01.07.2018) | Initialen (nicht die echten, sondern zugewiesen) | identifizierende Angaben entfernt | | | eucrim.eu "Names Replaced by Initials" (MEDIUM) |
| Kirchliche Gerichte (ZKR) | Kläger "AA.", Nichtkläger "NN." | Straße "X-straße" (Buchstabe, "-straße" bleibt) | | Verfahrensdaten bleiben | uni-muenster.de ZKR (MEDIUM) |
| Frankreich, Cour de cassation (Judilibre) | "M. [X]", "Mme [Y]" | "[Adresse 1]", "[Localité 2]" | | | **Fachwissen, nicht neu belegt (LOW)** |

Lesart: Es gibt **keine bundeseinheitliche deutsche Konvention**; jede Justizverwaltung hat eigene Hausregeln (nicht öffentlich gefunden). Gemeinsam ist: Rollen für Parteien, Buchstaben für Personen/Orte/Firmen, Auslassung "[…]" für Beiwerk, Gericht/Az./Datum/Richter bleiben.

### Empfohlene Schemata (je Behörde wählbar, Standard fett)

| Kategorie | **Standard DE** | Alternative DE | EN | FR |
|---|---|---|---|---|
| Person | **"A.", "B.", "C." fortlaufend nach erstem Auftreten, Anrede bleibt ("Herr A.", "Frau B.")** | Rolle mit Zähler ("Kläger", "Beklagte zu 1", "Zeugin 2"); "[Name 1]"; echte Initialen nur mit Warnung | "A", "B" / "Person 1" | "M. [A]", "Mme [B]" |
| Ort | **"A-Stadt", "B-Dorf" bzw. "Ort 1"** | Einzelbuchstabe "in L" (Bayern-Stil) | "Town A" | "[Localité 1]" |
| Straße/Anschrift | **"A-Straße" (Hausnummer weg), PLZ weg** | "[Anschrift 1]" | "[Address 1]" | "[Adresse 1]" |
| Firma | **"A GmbH" (Rechtsform bleibt)** | "Firma E" | "Company A Ltd" | "Société [A]" |
| Datum | **Geburtsdatum "[Geburtsdatum]" oder nur Jahr**; Verfahrensdaten bleiben | "XX.XX.1980" | "[date of birth]" | "[date de naissance]" |
| IDs (IBAN, Steuer-ID, Kennzeichen) | **"[IBAN]", "[Kennzeichen]"** | "XXXXXX" | | |
| Auslassung Beiwerk | **"[…]"** (wie BGH) | | | |

Regeln: eigener Namensraum je Kategorie (Person A. und Firma A GmbH kollidieren nicht im Sinne, aber besser getrennte Buchstabenfolgen anzeigen); Buchstaben dürfen nicht die echten Initialen sein (Prüfung, ggf. überspringen); Geschlecht über Anrede bleibt erhalten (lesbar, aber Hinweis: Geschlecht ist Quasi-Identifikator); Schema und Zuordnung je Dokument stabil, über mehrere Dokumente eines Vorgangs optional gleich (v2). Komplexität HIGH insgesamt, Kern ist Clusterung aus Spike (98,5 % auf Gold, Initialen 73 %).

---

## Rechtsgrundlagen-Labels (vorbelegte Sätze)

Als Daten (JSON/DB) ausliefern, versioniert, je Behörde/Gruppe aktivierbar, kopierbar und editierbar; jedes Label: Kürzel, Norm, Kurztext für Balken, Langtext für Begründungsliste. Prüfstand der Paragrafen unten; **vor Auslieferung juristisch gegenlesen lassen**, Landesrecht ändert sich.

### Bund

| Gesetz | Ausnahmen (Kernparagrafen) | Konfidenz |
|---|---|---|
| IFG (Bund) | § 3 Schutz besonderer öffentlicher Belange (Nr. 1 a bis g, Nr. 2 bis 8, u. a. Nr. 4 Geheimhaltungspflicht/Berufs- und Amtsgeheimnis, Nr. 7 vertraulich übermittelte Information); § 4 Schutz des behördlichen Entscheidungsprozesses; **§ 5 Schutz personenbezogener Daten** (Abs. 1 Abwägung/Einwilligung, Abs. 1 S. 2 besondere Kategorien, Abs. 2 Dienst-/Amtsverhältnis und Mandat, Abs. 3 Gutachter/Sachverständige, **Abs. 4 Bearbeiterdaten nicht ausgeschlossen**); § 6 Schutz geistigen Eigentums (S. 1) und Betriebs- oder Geschäftsgeheimnisse (S. 2) | HIGH (gesetze-im-internet.de, Recherche 04.11.; Wikipedia bestätigt §§ 3 bis 6) |
| UIG | § 8 öffentliche Belange; § 9 sonstige Belange (Abs. 1 Nr. 1 personenbezogene Daten, Nr. 2 geistiges Eigentum, Nr. 3 Betriebs-/Geschäftsgeheimnisse) | MEDIUM (Fachwissen, nicht neu abgerufen) |
| VIG | § 3 Ausschluss- und Beschränkungsgründe (Nr. 1 öffentliche, Nr. 2 private Belange inkl. personenbezogene Daten und Betriebs-/Geschäftsgeheimnisse) | MEDIUM (Fachwissen) |
| Querschnitt | Art. 9 DSGVO besondere Kategorien; § 30 AO Steuergeheimnis; § 35 SGB I Sozialgeheimnis; § 203 StGB | MEDIUM |

### Länder

| Land | Gesetz | Personenbezogene Daten | Betriebs-/Geschäftsgeheimnisse, geistiges Eigentum | Öffentliche Belange / Entscheidungsprozess | Konfidenz |
|---|---|---|---|---|---|
| Baden-Württemberg | LIFG | § 5 | § 6 | § 4 (besondere öffentliche Belange); weitere Gründe § 9 Abs. 3 | MEDIUM (LfDI-Handreichung 2026, Ministeriumsseite) |
| Bayern | kein IFG; Art. 39 BayDSG Auskunftsrecht, kommunale Informationsfreiheitssatzungen | Art. 39 BayDSG | | | MEDIUM (Wikipedia, Drs. 19/11074 Nds.) |
| Berlin | IFG Bln | § 6 | § 7, § 7a (besondere Verträge) | § 9 (öffentliche Belange, Rechtsdurchsetzung), § 10 (Entscheidungsprozess), § 11 (Gemeinwohl); § 5 Amtsverschwiegenheit; § 12 beschränkte Akteneinsicht | HIGH (Inhaltsverzeichnis umwelt-online) |
| Brandenburg | AIG | § 5 (private Interessen, Abs. 1 Nr. 1 personenbezogene Daten) | § 5 | § 4 | MEDIUM (bravors-Auszug, VG Potsdam) |
| Bremen | BremIFG | § 5 | § 6 | § 3, § 4 (Bundesmodell) | LOW (Fachwissen) |
| Hamburg | HmbTG | § 4 | § 7 (BGG), § 8 (geistiges Eigentum) | § 5 Ausnahmen, § 6 öffentliche Belange, § 9 Einschränkungen | HIGH (Inhaltsverzeichnis umwelt-online) |
| Hessen | HDSIG Teil 4 (nur Land; Kommunen per Satzung) | § 83 | § 82 (Nr. 4 Drittbeteiligung, Wortlaut nicht geprüft) | § 82 (öffentliche und private Belange), § 84 (behördliche Entscheidungsprozesse) | MEDIUM |
| Mecklenburg-Vorpommern | IFG M-V | § 7 | § 8 | § 5 (öffentliche Belange, Rechtsdurchsetzung), § 6 (Entscheidungsprozess) | MEDIUM |
| Niedersachsen | **kein IFG** (Stand Ende April 2026, Drs. 19/11074); kommunale Satzungen | | | | MEDIUM |
| Nordrhein-Westfalen | IFG NRW | § 9 (§ 10 Einwilligung) | § 8 | § 6 (öffentliche Belange, Rechtsdurchsetzung), § 7 (Entscheidungsbildungsprozess) | HIGH (lexmea-Inhaltsverzeichnis) |
| Rheinland-Pfalz | LTranspG | § 16 (andere Belange; Abs. 4 Amtsträgerdaten) | § 16 Abs. 1 Nr. 1 (geistiges Eigentum), Nr. 2 (BGG) | § 14 (öffentliche Belange), § 15 (Entscheidungsprozess), § 17 Abwägung | MEDIUM |
| Saarland | SIFG (verweist auf IFG Bund) | §§ 3 bis 6 IFG entsprechend | | | LOW (Fachwissen) |
| Sachsen | SächsTranspG (2022, geändert 03.12.2025) | § 6 (Abs. 1 unkenntlich machen) | § 5 Abs. 1 (Paragraf der BGG-Ausnahme nicht sicher) | § 5 Ausnahmen, § 4 Abs. 3 | LOW bis MEDIUM |
| Sachsen-Anhalt | IZG LSA | § 5 | § 6 | § 3, § 4 (Bundesmodell) | LOW (Fachwissen) |
| Schleswig-Holstein | IZG-SH | § 10 (Schutz entgegenstehender privater Interessen) | § 10 | § 9 (entgegenstehende öffentliche Interessen) | MEDIUM |
| Thüringen | ThürTG | § 13 (private Interessen, Abs. 3/4 Bundesmodell) | § 13 Abs. 2 | § 12 (öffentliche Belange), § 14 Abwägung | MEDIUM |

### Veröffentlichung von Gerichtsentscheidungen

Kein eigener Paragraf; Label-Satz "Anonymisierung zur Veröffentlichung" mit Unterlabels nach FAU-Kategorien: Name natürliche Person, Name juristische Person (wenn Rückschluss auf Personen), Anschrift/Ort, Geburtsdatum, Kennzeichen/FIN, Kontaktdaten, Geschäfts-/Aktenzeichen Dritter, Grundstücksbezeichnung (JANO nennt sie ausdrücklich), mittelbar identifizierend (Beruf, Titel, Gesundheit, besondere Merkmale). Begründungstext: Persönlichkeitsrecht (Art. 2 Abs. 1 i. V. m. Art. 1 Abs. 1 GG), Veröffentlichungspflicht der Gerichte (BVerwGE 104, 105, zitiert auf JANO-Folie 4). Bleibt stehen: Gericht, Az. der Entscheidung, Datum, Richter (laut LTO-Bericht zu BVerwG 6 C 35.13 dürfen Namen von Richtern, Schöffen, Staatsanwälten, Verteidigern nicht geschwärzt werden; Hinweis: JANO-Mockup ersetzt dennoch "Richtername 1", Hausregeln weichen ab, daher Kategorie "Gerichtspersonen" mit Voreinstellung "anzeigen, nicht ersetzen").

---

## Schwärzungsprotokoll und Begründungsliste

Zwei Artefakte aus denselben Daten, beide **ohne Klartext** der geschwärzten Inhalte.

**Protokoll (Akte, PDF + JSON)** (Owner, ergänzt um Fundstücke aus Redactable/Objective/Legiscope):
- Kopf: Dateiname Original und Ergebnis (Dateiname auf Personenbezug geprüft), SHA-256 beider, Datum/Zeit, Modus (Schwärzen/Pseudonymisieren, Rastermodus ja/nein), Label-Satz und Version
- Personen: Bearbeiter, Zweitprüfer, jeweils mit Zeitstempel; Status-Historie Entwurf -> geprüft -> freigegeben
- Zählungen: je Kategorie, je Seite, je Label; Anzahl abgelehnter Vorschläge; Anzahl manueller Funde (Suche, Markierung, Fläche); Anzahl bewusst offen gelassener Amtsträger mit Label (z. B. "§ 5 Abs. 4 IFG")
- Je Schwärzung (Tabelle): laufende Nr., Seite, Position (Rechteck), Kategorie, Label, Herkunft (Erkenner/Suche/manuell), Konfidenzstufe, Entscheider, Hash des Inhalts (gesalzen, damit kurze Werte wie PLZ nicht per Wörterbuch rückrechenbar sind)
- Nachprüfung: welche Prüfer, Ergebnis, Anzahl Revisionen (%%EOF), entfernte Objekte (Anhänge, Kommentare, Formularfelder, Metadaten, Strukturbaum-Texte)
- Technik: App-Version, Modellversionen mit sha256, OCR-Sprachen, Hinweis bei schwacher OCR-Seite
- Hinweis auf nicht Erkanntes ("Pseudoidentifikatoren wurden nur als Hinweis geprüft")

**Begründungsliste (für den Bescheid an Antragsteller)**: Tabelle Seite | Umfang (z. B. "1 Name", "Absatz", "ganze Seite") | Rechtsgrundlage | Kurzbegründung (Langtext des Labels, editierbar); zusammenfassbar nach Label ("Seiten 3 bis 5: § 6 S. 2 IFG"). Keine Hashes, keine Prüfernamen (intern). Vorbild: UK National Archives verlangt, alle Ausnahmen mit Gründen zu nennen; US-Praxis "redaction log" mit Rechtsgrundlage und Kurzbegründung. Als PDF (barrierefrei, aus Vorlage) und DOCX/ODT zum Weiterbearbeiten. Komplexität MEDIUM, Abhängigkeit: Labels je Fund.

---

## Barrierefreiheit

### Prüf-UI (BITV 2.0 / EN 301 549 = WCAG 2.1 AA, besser 2.2 AA)

| Anforderung | WCAG | Umsetzung |
|---|---|---|
| Kategorie nicht nur über Farbe | 1.4.1 | Kürzel/Symbol in Markierung und Liste (JANO nutzt nur Farbe) |
| Kontrast Markierungen auf Seite, hell/dunkel | 1.4.3, 1.4.11 | Rahmen 3:1 gegen Seitenhintergrund; Owner-Regel Playwright hell/dunkel |
| Alles per Tastatur, inkl. Flächenschwärzung | 2.1.1 | Alternative zur Mausfläche (siehe oben) |
| Einbuchstaben-Kürzel abschaltbar / nur bei Fokus | 2.1.4 | Einstellung je Nutzer |
| Fokus sichtbar und nicht verdeckt | 2.4.7, 2.4.11 (2.2) | Liste scrollt Fokus in Sicht, Dokumentansicht hebt fokussierten Fund hervor |
| Statusmeldungen ohne Fokuswechsel ("37 Vorkommen angenommen", "Analyse 40 %") | 4.1.3 | `aria-live="polite"` |
| Dokumentansicht für Screenreader | 1.1.1, 1.3.1 | Seitenbild allein ist nicht zugänglich: **Vorschlagsliste mit Kontextausschnitt ist die zugängliche Hauptansicht**; zusätzlich Textansicht der Seite mit markierten Spannen (`<mark>` mit Beschriftung) |
| Zielgröße Schaltflächen | 2.5.8 (2.2) | mind. 24x24 px, Nextcloud-Komponenten |
| Zeitbegrenzung | 2.2.1 | Lebensdauer des Prüfzustands (Owner) muss verlängerbar sein, Warnung vor Ablauf |
| Sprache DE/EN/FR | 3.1.1, 3.1.2 | `lang` je Oberfläche; Dokumentinhalt mit eigener Sprache |

Komplexität MEDIUM; die zugängliche Textansicht ist der Mehraufwand gegenüber einer reinen Bildansicht.

### Ausgabe-PDF

- **DOCX/ODT-Quelle**: Ersatztext ("[geschwärzt]" bzw. Pseudonym) direkt im XML, sichtbarer Balken als Zeichenformat (schwarzer Hintergrund) oder Blockzeichen; LibreOffice exportiert dann ein getaggtes PDF (PDF/UA-Export ist in LibreOffice vorhanden, Version im Container prüfen). Screenreader liest "geschwärzt" statt "Vollblock Vollblock". Komplexität MEDIUM. **Empfehlung v1.**
- **PDF-Quelle mit Strukturbaum**: Nach `apply_redactions` zeigen Strukturelemente ggf. auf entfernte Inhalte; Platzhalter-Tag (Figure oder Span mit Alt "Geschwärzt, <Label>") an der Stelle einfügen, Tags teilen (CommonLook-Vorgehen). Komplexität HIGH, Werkzeuglage in PyMuPDF/pikepdf ungeklärt. **Empfehlung: v1 Strukturbaum sicher entfernen oder bereinigen und Ausgabe als "nicht barrierefrei" im Protokoll kennzeichnen; v2 Platzhalter-Tags.** Bevor entschieden wird: Messung, ob Strukturbaum nach PyMuPDF-Schwärzung Klartext in /Alt oder /ActualText behält (Leckfrage, Phase-Forschung).
- **Rastermodus und Scans**: nicht barrierefrei außer über frische OCR-Textebene (Owner); im Protokoll und Dateinamen kenntlich machen.
- Prüfung des Ausgabe-PDF mit veraPDF (PDF/UA-1, freie Software) in CI möglich; PAC ist nur Windows-GUI. veraPDF-Eignung **nicht geprüft (LOW)**.

---

## Feature Dependencies

```
Text- und Positionsindex (PDF rawdict / OCR-Wortboxen / DOCX-ODT-XML-Läufe)
    ├──requires──> Erkennung (Erkennerstapel, Konfidenz)
    │                  └──requires──> Clusterung/Namensweitergabe
    │                                     ├──required by──> "für alle gleichen Funde"
    │                                     ├──required by──> Pseudonymisierung (konsistent)
    │                                     │                     └──enhanced by──> Rollen-Pseudonyme (Rubrum-Regeln)
    │                                     └──required by──> Amtsträger-Kategorie (Weitergabe im Cluster)
    ├──required by──> Suchen und schwärzen
    ├──required by──> Dokumentansicht mit Markierungen (Koordinaten)
    │                     └──required by──> Seitenübersicht mit Fundmarkern
    └──required by──> Echte Schwärzung (Rechtecke je Zeile)
                          └──required by──> Leck-Nachprüfung (Positionsprüfung kurzer Werte)

Prüfzustand in App-DB (rechtegeprüft, befristet)
    ├──required by──> Prüf-UI (alle Aktionen, Undo)
    ├──required by──> Vier-Augen-Freigabe ──requires──> Status + Rollen/Gruppen
    └──required by──> Protokoll + Begründungsliste

Label-Sätze (Daten, Admin-UI)
    ├──required by──> Label je Fund in Prüf-UI
    ├──required by──> Label im Balken (optional)
    ├──required by──> Begründungsliste
    └──required by──> "bewusst offen gelassen" (Amtsträger § 5 Abs. 4 IFG)

Echte Schwärzung + Neuschreiben ──required by──> Leck-Nachprüfung ──required by──> Datei schreiben neben Original
Vier-Augen-Freigabe ──required by──> Datei schreiben neben Original (wenn aktiv)

OCR (Tesseract) ──required by──> Scans: Erkennung, Suche, Flächenhilfe, frische Textebene nach Schwärzung
LibreOffice headless ──required by──> PDF-Ausgabe aus DOCX/ODT, dritter Prüfer, barrierefreies PDF aus DOCX/ODT

Flächenschwärzung ──conflicts──> DOCX/ODT-Ausgabe (nicht abbildbar; nur PDF-Ausgabe)
Rastermodus ──conflicts──> Barrierefreies Ausgabe-PDF
Label im Balken ──conflicts (teilweise)──> gerundete/feste Balkenbreite (Text braucht Platz; Auto-Size nötig)
Echte Initialen als Pseudonym ──conflicts──> Anonymisierungsziel (USENIX 2023)
```

### Dependency Notes

- **Positionsindex zuerst**: Prüfansicht, Suche, Schwärzung und Nachprüfung hängen am selben Index. Ein Index für alle verhindert, dass die UI etwas markiert, was die Schwärzung an anderer Stelle entfernt. Gegenprobe (Owner-Regel): Nachprüfung nutzt **andere** Extraktoren als der Index.
- **Clusterung vor Pseudonymisierung und vor Sammelaktionen**: beide brauchen stabile Entitäten-IDs; Verknüpfen/Trennen in der UI ändert Cluster, das muss Pseudonyme neu vergeben ohne bereits entschiedene Funde zu verlieren.
- **Labels vor Begründungsliste und vor Amtsträger-Freigabe**: Ohne Label kein "offen gelassen nach § 5 Abs. 4".
- **Vier-Augen erst nach Status-Modell**: Status Entwurf/geprüft/freigegeben mit Prüfer und Zeit ist Basis; Rollen über Nextcloud-Gruppen.
- **Flächenschwärzung vs. DOCX/ODT**: Anforderung muss festlegen, dass bei Flächen auf DOCX/ODT nur PDF ausgegeben wird (oder eingebettetes Bild ersetzt).
- **Barrierefreies PDF hängt am Quellformat**: DOCX/ODT-Weg billig, PDF-Weg teuer; Anforderungen getrennt formulieren.

---

## MVP Definition

### Launch With (v1)

Owner-Entscheidungen sind gesetzt; hier nur Ergänzungen und Präzisierungen.

- [ ] Vorschlagsliste **je Entität mit Zähler**, aufklappbar zu Vorkommen (JANO-Muster), Zustände offen/angenommen/abgelehnt/unsicher
- [ ] Sammelaktionen je Cluster und je Kategorie (nur hohe Konfidenz), mit Anzahl-Bestätigung und Undo
- [ ] Manuelle Textmarkierung -> neuer Cluster; Suchen und schwärzen mit Umlaut-Varianten und Zeilenumbruch
- [ ] Flächenschwärzung mit Tastaturalternative, Ganzseitenschwärzung
- [ ] Seitenübersicht mit Fundzahl und OCR-Warnung
- [ ] Original/Ergebnis-Umschalter, Textvorschau im Ersetzungsmodus
- [ ] Tastaturfluss mit Legende, WCAG-2.1.4-konform
- [ ] Pseudonym-Schema DE/EN/FR **ohne echte Initialen** als Standard, Kategorien-Namensräume, editierbar je Cluster
- [ ] Label-Sätze IFG Bund, UIG, VIG, alle Länder-Gesetze (Tabelle oben), "Veröffentlichung Entscheidungen"; Admin kann kopieren/ändern; Label "offen gelassen § 5 Abs. 4 IFG" für Amtsträger
- [ ] Protokoll mit gesalzenen Hashes und Nachprüfungsergebnis; **Begründungsliste** als Export (vorgezogen, da billig)
- [ ] Prüf-UI WCAG 2.1 AA inkl. zugänglicher Textansicht
- [ ] Ausgabe-PDF aus DOCX/ODT getaggt; aus PDF: Strukturbaum sicher behandelt, Barrierefreiheit im Protokoll ausgewiesen
- [ ] Strukturbaum-Texte (/Alt, /ActualText) in Sanitize-Liste und Leck-Nachprüfung

### Add After Validation (v1.x)

- [ ] Rollen-Pseudonyme aus dem Rubrum ("Kläger", "Beklagte zu 1") wenn Gerichte als Nutzer bestätigt sind
- [ ] Prüfexemplar (audit copy) mit halbtransparenten Markierungen für die Akte, wenn Vier-Augen-Nutzer es anfragen
- [ ] Seitengleiche Nebeneinander-Ansicht Original/Ergebnis als gerenderte PDFs
- [ ] Stapel-Analyse eines Ordners im Hintergrund (Prüfung weiter je Datei), wenn RAM-Wächter stabil
- [ ] Gleiches Pseudonym über mehrere Dokumente eines Vorgangs
- [ ] Label-Satz-Import/Export zwischen Instanzen (JSON), wenn Behörden eigene Sätze pflegen

### Future Consideration (v2+)

- [ ] Platzhalter-Tags für barrierefreie Ausgabe aus getaggten PDF-Quellen (Werkzeuglage klären)
- [ ] Glyphen-Normalisierung ohne Rastern (Recherche 3.3)
- [ ] Erkennung von Unterschriften/Gesichtern/Stempeln in Scans als Vorschlag für Flächen
- [ ] Fristen und Drittbeteiligung § 8 IFG (Conduction hat Woo-Fristen), eher eigene App
- [ ] Interop-Format für Funde mit Conduction/Presidio

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Entitäten-Liste mit Zähler + Sammelaktionen | HIGH | MEDIUM | P1 |
| Suchen und schwärzen | HIGH | MEDIUM | P1 |
| Flächenschwärzung (inkl. Tastatur, ganze Seite) | HIGH | MEDIUM | P1 |
| Dokumentansicht mit Markierungen | HIGH | HIGH | P1 |
| Seitenübersicht mit Fundmarkern | MEDIUM | MEDIUM | P1 |
| Tastaturfluss | HIGH | LOW | P1 |
| Pseudonym-Schema ohne echte Initialen | HIGH | MEDIUM | P1 |
| Label-Sätze Bund + Länder | HIGH | MEDIUM (Recherche/juristische Prüfung ist der Aufwand) | P1 |
| Begründungsliste-Export | HIGH | LOW | P1 |
| Prüf-UI WCAG 2.1 AA mit Textansicht | HIGH (Pflicht für Zielgruppe) | MEDIUM | P1 |
| Getaggtes PDF aus DOCX/ODT | MEDIUM | MEDIUM | P1 |
| Strukturbaum in Sanitize + Nachprüfung | HIGH (Leck) | LOW | P1 |
| Rollen-Pseudonyme aus Rubrum | MEDIUM | HIGH | P2 |
| Prüfexemplar | MEDIUM | MEDIUM | P2 |
| Nebeneinander-Ansicht gerendert | MEDIUM | MEDIUM | P2 |
| Stapel-Analyse | MEDIUM | MEDIUM | P2 |
| Platzhalter-Tags aus PDF-Quelle | MEDIUM | HIGH | P3 |
| Unterschrift-/Gesichtserkennung | MEDIUM | HIGH | P3 |

---

## Competitor Feature Analysis

| Feature | Acrobat Pro | Objective Redact | Redactable | CaseGuard | Conduction Filinq/Anonymiq | JANO | Our Approach |
|---------|-------------|------------------|------------|-----------|---------------------------|------|--------------|
| Lokal/ohne Cloud | Desktop | Desktop/Server | Cloud (SaaS) | lokal | Nextcloud lokal | Bundesnetz, zentral | Nextcloud lokal, ExApp |
| PII-Erkennung | Muster (US-zentriert) | Muster, Regex | KI + Muster | KI | Presidio, NL zuerst | KI (IBM) | Presidio + DE-Erkenner + spaCy + GLiNER2 |
| Prüfung je Fund | markieren, dann anwenden | Arbeitskopie | Entwurfsmodus | k. A. | Accept/Reject/Edit je Zeile | Liste je Entität | Liste je Entität + Vorkommen, 4 Zustände |
| Alle gleichen Funde | Suchen und alles schwärzen | Suche | Find and replace mit Grund | Stichwortsuche | k. A. | Cluster mit Zähler | Cluster + Suche, Grund bei Sammelaktion |
| Fläche | ja | Rechteck, Kritzeln, Stempel | manuell | ja | k. A. | k. A. | ja + Tastatur + ganze Seite |
| Ersetzen/Pseudonym | nein (nur Überlagerungstext) | nein | nein | nein | `[PERSON]` | Rollen mit Zähler | Schema DE/EN/FR, keine echten Initialen |
| Gründe/Codes | US FOIA/Privacy Act, eigene | AU/NZ/UK-Gruppen, eigene | FOIA, HIPAA, eigene | k. A. | nicht dokumentiert | k. A. | IFG Bund, UIG, VIG, 15 Länder, Urteile |
| Freigabe zweite Person | nein | Team-Review vor Finalisieren | Review-Prozesse, RBAC | k. A. | Review-Queue bei niedriger Konfidenz | Prüfung durch Justizbeschäftigte | Vier-Augen, abschaltbar |
| Nachweis/Protokoll | nein | Bericht, Audit-Kopie | Zertifikat | k. A. | Audit-Log in OpenRegister | k. A. | Protokoll + Begründungsliste + Leck-Nachprüfung |
| Unabhängige Leck-Nachprüfung | nein | nein | nein (nur "certificate") | nein | nein | k. A. | ja, blockierend |
| Layouttreues PDF | ja | ja (PDF/TIFF) | ja | ja | nur DOCX, PDF fällt auf Text zurück | Word-basiert (vermutet, LOW) | ja, plus DOCX/ODT |
| Tastenkürzel Prüfung | allgemeine Acrobat-Kürzel | nicht dokumentiert | nicht dokumentiert | nur Video-Kürzel dokumentiert | nicht dokumentiert | k. A. | dokumentierter Fluss |
| Barrierefreie Ausgabe | Text entfernt, kein Platzhalter-Tag | k. A. | k. A. | k. A. | wirbt mit "WCAG compliant" (k. A. zu Schwärzung) | k. A. | getaggtes PDF aus DOCX/ODT v1 |
| Smallpdf (Randnotiz) | | | | | | | Online, manuell markieren, Suche nur kostenpflichtig, keine KI-Erkennung belegt: für Behörden wegen Cloud ungeeignet |
| OpenRedact (Randnotiz) | | | | | | | Prototype Fund 2020, Repo archiviert 20.03.2026, nach opencode.de umgezogen, nicht gepflegt |

---

## Sources

Abgerufen am 07.11.2026, sofern nicht anders angegeben. Herstellerangaben sind nicht unabhängig geprüft.

- JANO: Präsentation Hess. Ministerium der Justiz, 51. AK Informationsfreiheit, 21.04.2026, https://www.lda.brandenburg.de/sixcms/media.php/9/Pr%C3%A4sentation_Projekt_JANO.pdf (Folien 4, 5, 8, 9 lokal gerendert und ausgewertet) (HIGH); anwaltspraxis-magazin.de 15.07.2026 "Anonymisierung von Gerichtsentscheidungen" (MEDIUM); beck-aktuell 12.12.2025
- FAU AnGer: https://www.linguistik.phil.fau.de/files/2026/01/AnGer_AnigeD_2025-2.pdf (Tagset, Risikoniveau, Recall-Ziel > 99 %, lokal ausgewertet) (HIGH)
- Deuber, Keuchen, Christin: Assessing Anonymity Techniques Employed in German Court Decisions, USENIX Security 2023, https://www.usenix.org/conference/usenixsecurity23/presentation/deuber (Abstract) (HIGH für Kernaussage Initialen)
- BGH VI ZR 157/24 vom 31.03.2026, Volltext über https://app.omnilex.ai/de/sources/court-decision/de-rii--kore706382026/bgh-2026-03-31-vi-zr-15724 (MEDIUM, Drittportal)
- LSG Bayern L 8 SO 155/22 vom 13.07.2023, https://www.gesetze-bayern.de/Content/Rtf/Y-300-Z-BECKRS-B-2023-N-48477?all=False (HIGH)
- Anonymisierungskonventionen Schweiz/Österreich/kirchlich: Suchergebnisse zu bger.ch, jusline.at, uni-muenster.de/Ejournals ZKR (MEDIUM bis LOW); EuGH: https://eucrim.eu/news/names-replaced-initials (MEDIUM)
- LTO zu BVerwG 6 C 35.13 (Namen von Richtern usw. nicht schwärzen): https://www.lto.de/recht/hintergruende/h/bverwg-urteil-6-C-35-13-gerichtsentscheidungen-verfahrensbeteiligte-anonymisiert-uebersendung-pressefreiheit/print.html (MEDIUM)
- Conduction: https://filinq.conduction.nl/docs/tutorials/user/anonymise-document/ ; https://conduction.nl/solutions/openanonymiser ; https://docudesk.conduction.nl/docs/intro ; https://zff.dev/Conduction/openanonymiser-light-exapp (MEDIUM, Hersteller)
- Objective Redact: https://www.objective.com/products/objective-redact ; https://www.objective.com/resources/blog-improving-your-redaction-experience-with-our-latest-update-to-objective-redact (MEDIUM, Hersteller)
- Redactable: https://www.redactable.com/redaction-reasons ; https://www.redactable.com/features (MEDIUM, Hersteller)
- CaseGuard: https://caseguard.com/tag/pdf-redaction ; https://caseguard.com/help/project-workspace/keyboard-shortcutes/ (LOW, Marketing)
- Adobe: https://helpx.adobe.com/acrobat/desktop/protect-documents/redact-pdfs/text-redaction-properties.html ; Rick's Acrobat X Redaction Guide https://blog.adobe.com/en/publish/2010/12/27/ricks-acrobat-x-redaction-guide ; Using Redaction in Adobe Acrobat X White Paper (alnd.uscourts.gov) (HIGH für Overlay-Optionen, MEDIUM für Code-Sätze, da 2010)
- Relativity: https://help.relativity.com/RelativityOne/Content/Relativity/Viewer/Markups.htm ; https://help.relativity.com/Server2024/Content/Relativity/Keyboard_shortcuts/Keyboard_shortcuts.htm (HIGH)
- Smallpdf: Vergleich https://updf.com/protect-pdf/smallpdf-redact/ (LOW, Wettbewerberquelle)
- OpenRedact: https://prototypefund.de/en/project/schwaerzer ; https://github.com/openredact/anonymizer (archiviert 20.03.2026) (HIGH für Status)
- Redaction-Codes/Logs allgemein: UK National Archives redaction toolkit https://www.nationalarchives.gov.uk/terms-and-conditions/takedown-and-reclosure-policies/reclosure-policy/redaction-toolkit/ ; Casepoint Redaction Codes https://guide.casepoint.com/resource-center/docs/redaction-codes-1 (MEDIUM)
- Barrierefreie Schwärzung: Allyant/CommonLook https://support.allyant.com/support/solutions/articles/156000019974-how-to-tag-redacted-text-in-commonlook-pdf-desktop ; WebAIM https://webaim.org/discussion/mail_message?id=22607 ; DHS-Memo 2010 (MEDIUM)
- BITV/PDF/UA: BMUV-Leitfaden https://www.bmuv.de/fileadmin/Daten_BMU/Download_PDF/Barrierefreiheit/11-2023_bmuv_leitfaden_externe_anlieferung_barrierefreie_pdf_bf.pdf ; Bundestag Handreichung 09/2024 ; vergabeblog 21.08.2025 (MEDIUM)
- IFG-Länder: Berlin IFG Inhaltsverzeichnis https://umwelt-online.de/recht/allgemei/laender/bln/ifg_in.htm (HIGH); HmbTG https://umwelt-online.de/recht/allgemei/laender/hh/transpg_in.htm (HIGH); IFG NRW https://lexmea.de/de/gesetz/ifg-nrw/toc (HIGH); LIFG BW LfDI-Übersicht 2026 https://www.baden-wuerttemberg.datenschutz.de/wp-content/uploads/2026/05/Landesinformationsfreiheitsgesetz-BW-fuer-informationspflichtige-Stellen-Uebersicht_0427.pdf (MEDIUM); LTranspG RP https://open.rlp.de/fileadmin/user_upload/TranspG_RP.pdf (MEDIUM, über Suchauszug); SächsTranspG https://revosax.sachsen.de/vorschrift/19699 (LOW bis MEDIUM); ThürTG TLfDI-Vortrag (MEDIUM); IZG-SH https://www.anwalt24.de/gesetze/izg_sh/9 und ULD-Folien (MEDIUM); AIG Brandenburg https://bravors.brandenburg.de/gesetze/aig (MEDIUM); IFG M-V Durchführungshinweise https://umwelt-online.de/recht/allgemei/laender/mv/ifgdh2.htm (MEDIUM); HDSIG Kreisrecht Marburg-Biedenkopf https://www.marburg-biedenkopf.de/kreisrecht/10_11.pdf (MEDIUM); Niedersachsen Drs. 19/11074 https://www.landtag-niedersachsen.de/drucksachen/drucksachen_19_12500/11001-11500/19-11074.pdf (MEDIUM); Übersicht https://de.wikipedia.org/wiki/Informationsfreiheitsgesetz (MEDIUM)
- Nicht neu abgerufen, Fachwissen (LOW bis MEDIUM, vor Auslieferung prüfen): Paragrafen UIG, VIG, BremIFG, IZG LSA, SIFG; französische Judilibre-Pseudonyme; veraPDF-Eignung; LibreOffice-PDF/UA-Export im Container
- Interne Grundlagen: `C:/Users/Student/nextcloud-pii-redaction/.planning/PROJECT.md`; `C:/Users/Student/neue-apps-recherche-2026-11-04/bigtech-pii-redaction-2026-11-04.md`; `C:/Users/Student/pii-spike-2026-11-06/SPIKE-REPORT.md`

---
*Feature research for: lokale PII-Schwärzung und Pseudonymisierung in Nextcloud*
*Researched: 07.11.2026*
