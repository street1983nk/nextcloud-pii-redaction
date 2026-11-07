# PII Redaction

## What This Is

Nextcloud-App aus zwei Teilen (PHP-App `pii_redaction` für Dateiaktion, Prüfseite, Rechte, Freigabe und Protokoll; ExApp `pii_redaction_backend` für Texterkennung, OCR, PII-Erkennung, Schwärzung, Pseudonymisierung und Leck-Nachprüfung), die personenbezogene Daten in PDF-, DOCX- und ODT-Dateien vollständig lokal findet, einem Menschen zur Prüfung vorschlägt und danach echt schwärzt oder konsistent pseudonymisiert. Zielgruppe: Behörden (IFG-Herausgaben, Veröffentlichung von Gerichtsentscheidungen), Kommunen, Schulen, kleine Organisationen und Selfhoster, die Dokumente herausgeben müssen, ohne Inhalte an einen Cloud-Dienst zu geben. Sprachen DE, EN, FR.

## Core Value

Eine Datei aus Nextcloud wird mit einem Klick lokal auf personenbezogene Daten geprüft; nach menschlicher Prüfung entsteht neben dem Original eine geschwärzte oder pseudonymisierte Kopie, in der nachweislich nichts Geschwärztes mehr steckt (Text, Metadaten, Altversionen, OCR-Ebene). Kein Inhalt verlässt den Server.

## Requirements

### Validated

- ✓ ExApp-Grundgerüst (AppAPI/HaRP, deklarative Admin-Einstellungen, l10n DE/EN/FR, Store-Metadaten, Release-/Zertifikats-Pipeline, CI): existing (gemeinsames Skeleton, 7755f0b..1f95af7)

### Active

- [ ] Zwei Apps: PHP `pii_redaction` + ExApp `pii_redaction_backend` (Umbau des Skeletons wie bei Audio & Video Search)
- [ ] Einstieg als Dateiaktion "Schwärzen / Pseudonymisieren" in Dateien; Analyse als Hintergrundauftrag; Benachrichtigung bei Fertig; eigene Prüfseite der PHP-App mit Dokumentansicht und Vorschlagsliste
- [ ] Formate v1: PDF mit Text, gescannte PDF (lokale OCR Tesseract deu/eng/fra), DOCX, ODT
- [ ] Erkennung lokal, gründlicher Modus als Standard: Presidio (gepinnt) + eigene deutsche Erkenner mit Prüfziffer + spaCy `de_core_news_lg` + GLiNER2-PII + Rollenwortfilter + Namensweitergabe (Spike: Personen-Recall 0,996, Leckrate 1,1 %); Schnellmodus (Presidio + spaCy) nur als bewusste Wahl
- [ ] Regeln für EN und FR (Aktenzeichen, Anschriften, IDs) auf DE-Niveau gebracht und gemessen
- [ ] Drei Konfidenzstufen (hoch, mittel, niedrig); niedrige Stufe nie automatisch angenommen
- [ ] Prüf-UI: Annehmen/Ablehnen je Fund und "für alle gleichen Funde", Suchen und alles schwärzen, manuelle Flächenschwärzung, Hinweis "Datum in Personenzeile"
- [ ] Zwei gleichwertige Modi: Schwärzen (Balken) und Pseudonymisieren (konsistente Pseudonyme je Person über Varianten "Herr Müller", "Müller", "M.", Schema DE/EN/FR)
- [ ] Amtsträger-Kategorie: erkannt und angezeigt, aber bis zur menschlichen Prüfung geschwärzt (Regel nimmt im Spike 2/566 Privatpersonen fälschlich aus)
- [ ] Rechtsgrundlagen-Labels je Schwärzung, vorbelegt (IFG Bund, Veröffentlichung von Entscheidungen), je Behörde anpassbar, optional sichtbar im Balken
- [ ] Status Entwurf, geprüft, freigegeben mit Prüfer und Zeitstempel; Vier-Augen-Freigabe in v1, per Admin abschaltbar
- [ ] Echte Schwärzung PDF: PyMuPDF `apply_redactions` (Text, Vektor, Bildpixel) + `scrub` + vollständiges Neuschreiben + pikepdf-Nachlauf; Sanitize-Liste wie Acrobat; Scans: alte Textebene verwerfen, neue OCR nach dem Schwärzen
- [ ] Echte Schwärzung DOCX/ODT per lxml (Änderungen, Kommentare, verborgener Text, Kopf/Fuß, Metadaten, Vorschaubilder, Links, Fußnoten)
- [ ] Ausgabe immer zusätzlich als neu geschriebenes PDF (LibreOffice headless im Container); Modus "Höchste Sicherheit" (Rastern + frische OCR) wählbar; Balkenbreite optional gerundet
- [ ] Automatische Leck-Nachprüfung jeder Ausgabe: zwei unabhängige Extraktoren mit unscharfem Abgleich, Rohobjekt-Suche, Revisionsprüfung, OCR, LibreOffice als dritter Prüfer; Prüfung über Positionen für kurze Zeichenketten; bei Fund keine Ausgabe
- [ ] Kopie neben dem Original (`_geschwärzt`, `_redacted`, `_caviardé`), Original nie verändert; Warnung bei Personenbezug im Dateinamen
- [ ] Schwärzungsprotokoll (PDF + JSON) ohne Klartext-PII: Hashes, Prüfer, Modus, Anzahl je Kategorie und Seite, Rechtsgrundlagen, Nachprüfung, Modellversionen
- [ ] Prüfzustand mit PII im Klartext nur serverseitig, zugriffsbeschränkt auf Berechtigte der Originaldatei, Lebensdauer begrenzt
- [ ] RAM-Wächter (Stapel braucht 3,96 GB), ein Auftrag zur Zeit, ehrlicher Fortschritt und Fehlgründe
- [ ] Eigener Testsatz mit Leckrate als Hauptkennzahl je Kategorie und Dokumenttyp; Ende-zu-Ende-Lecktest in CI; Release-Gate
- [ ] amd64 + arm64, nur CPU
- [ ] Alle Texte inkl. README dreisprachig DE/EN/FR im Gleichstand

### Out of Scope

- Inhalte an externe Dienste schicken (Cloud-Erkennung, externe Embeddings, LLM-APIs): Owner-Regel Datenschutz zuerst
- Vollautomatische Schwärzung ohne menschliche Prüfung: kein Anbieter mit Behördenbezug macht das, AWS-Pilot 5 % Fehler bei "sicheren" Fällen
- Nur Overlay-Annotationen ausliefern: Epstein-/Manafort-Fehler
- Flair `ner-german-large` im Auslieferpfad: Lizenz ungeklärt, 7,2 GB RAM, 42 s/Seite (Spike)
- Generatives LLM als Haupterkenner: keine stabilen Offsets, CPU-Laufzeit
- Geschwärzte Dokumente als Trainingsdaten weitergeben: Datenschutzregel
- Weitere Formate (XLSX, E-Mail, Bilder einzeln, PPTX): nach v1
- Indirekte Identifikatoren (Beruf, Funktion) und Gesundheitsdaten-Erkennung als Versprechen: später, v1 höchstens Hinweis

## Context

- Spike 06.11.2026 unter `C:/Users/Student/pii-spike-2026-11-06/` (SPIKE-REPORT.md, Code, `results/`, sha256-Manifest). Maßgebliche Quelle für Erkennerstapel, Kennzahlen, Schwärzungsverfahren und Leck-Prüfung.
- Recherche 04.11.2026: `C:/Users/Student/neue-apps-recherche-2026-11-04/bigtech-pii-redaction-2026-11-04.md` (Purview, Presidio, Acrobat, JANO, ALeKS, FAU, Conduction DocuDesk, Fehlschläge Epstein/Manafort/PoPETs 2023, MVP-Liste).
- Gemessen (CPU, 12 Kerne): v1-Stapel 7,9 bis 11,1 s/Seite, 3,96 GB Spitze, Kaltstart 16,5 s; Schwärzung PDF/DOCX/ODT 0 von 88 Geheimnissen nachweisbar; Positivkontrollen lecken (Overlay 84/88, inkrementell 84/88).
- Bekannte Schwächen: Initialen (Cluster 73 %), Geburtsdaten ohne Kontextwort (13/86), Präzision 0,5 bis 0,7, Glyphen-Fehlzuordnung in LibreOffice-PDFs (exakter Abgleich meldet fälschlich "sauber"), EN/FR-Regeln fehlen, Scans und Glyphenpositions-Leck nicht gemessen.
- Wettbewerb: Conduction DocuDesk + OpenAnonymiser (NL-Fokus, EUPL). Differenzierung: deutsche Erkenner und Rechtsgrundlagen, dokumentierte Leck-Nachprüfung, offene Qualitätszahlen, Pseudonymisierung wie JANO.
- Schwester-Apps: Audio & Video Search (Zwei-App-Muster, PHP-Gates, Playwright, Upgrade-/Drift-CI als Vorlage), Findling (Rechte, Gateway, RAM-Wächter), gemeinsames Skeleton.
- Zertifikate: `pii_redaction` erteilt (#1411), `pii_redaction_backend` beantragt (#1419, 06.11.). Repo `street1983nk/nextcloud-pii-redaction`.
- Testrechner 15,7 GB RAM, oft nur 4 bis 7 GB frei, C: knapp: Messungen seriell.

## Constraints

- **Datenschutz**: Kein Dokumentinhalt, kein Fund, keine Telemetrie verlässt den Server; Modelle einmal aus öffentlichen Quellen mit festem sha256 oder per Admin-Ablage: Owner-Regel
- **Bestes Ergebnis für User**: Aufwand und Zeit sind kein Grund, eine messbar bessere Lösung wegzulassen; jede Qualitätsentscheidung mit Leckrate/Recall belegen: Owner 04./06./07.11.
- **Tech stack**: Python-ExApp (FastAPI, nc_py_api) aus dem Skeleton; Presidio, spaCy, GLiNER2, PyMuPDF, pikepdf, pypdf, pdfminer.six, lxml, odfpy, Tesseract, LibreOffice headless: Spike
- **Kompatibilität**: Nextcloud 33 bis 35, AppAPI mit HaRP, amd64 + arm64, nur CPU
- **Ressourcen**: RAM-Wächter; Stapel ca. 4 GB je Arbeitsprozess, nie zwei Aufträge parallel auf kleinen Servern
- **Lizenzen**: AGPL-3.0-or-later (passt zu PyMuPDF AGPL); `fr_core_news_lg` LGPL-LR vor Auslieferung prüfen; Testkorpora nicht ins Repo
- **Sprache**: Alle nutzersichtbaren Texte und README DE/EN/FR im Gleichstand, Deutsch zuerst, echte Umlaute, keine Gedankenstriche, keine Emojis
- **Qualitäts-Gates**: ruff-Vollsatz, pyright basic, vulture lokal grün; Commits nur als street1983nk <k.cherif@outlook.de>, ohne "closes #N"
- **Prozess**: Vor jedem Push, Merge oder Kommentar den Owner fragen; UI-Abnahme gemeinsam per Playwright (3 Breiten, hell/dunkel); vor Store-Release großer Volltest DE/EN/FR; Gegenprobe nie mit dem Muster der Umsetzung

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1 Formate PDF + DOCX/ODT, Scans per lokaler OCR in v1 | Owner 06./07.11.; viele Behördenakten sind Scans | Offen |
| Schwärzen und Pseudonymisieren gleichwertig | Owner 06.11.; IFG braucht Balken, Urteilsveröffentlichung Pseudonyme | Offen |
| Zwei Apps: PHP `pii_redaction` + ExApp `pii_redaction_backend` | Dateiaktion, Prüfseite und Rechte brauchen PHP; Muster aus Audio & Video Search | Offen |
| Gründlicher Modus (mit GLiNER2) als Standard | Owner 07.11. "bestes Ergebnis, Aufwand egal"; Leckrate 1,1 % statt 2,1 % | Offen |
| Flair nicht ausliefern, eigenes feinjustiertes DE-Modell in die Roadmap | Spike: Lizenz, RAM; FAU: Feinjustierung größter Hebel | Offen |
| LibreOffice headless im Container (PDF-Ausgabe, dritter Prüfer) | Owner 07.11. | Offen |
| Amtsträger bis zur Prüfung geschwärzt | Owner 07.11.; Regel nimmt Privatpersonen fälschlich aus | Offen |
| Vier-Augen-Freigabe in v1, per Admin abschaltbar | Owner 07.11. | Offen |
| Rechtsgrundlagen-Labels in v1, je Behörde anpassbar | Owner 07.11. | Offen |
| Einstieg Dateiaktion + eigene Prüfseite | Owner 07.11. | Offen |
| FAU/ALeKS-Goldstandard anfragen (Entwurf, Owner sendet) | Owner 07.11.; echte Zielmaterial-Messung | Offen |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check: still the right priority?
3. Audit Out of Scope: reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-07 after initialization*
