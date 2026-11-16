# Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox - Context

**Gathered:** 2026-11-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Keine bösartige oder kaputte Datei kann die ExApp übernehmen oder ins Netz rufen: alle Parser (PDF, ZIP, XML, LibreOffice, OCR) laufen isoliert in Kindprozessen mit Zeit- und Speichergrenzen, gefährliche Eingaben werden VOR dem Parsen mit konkretem Grund abgewiesen, versteckte Netzaufrufe der Bibliotheken (Presidio, tldextract, GLiNER2) sind abgestellt und per `--network none` bewiesen. Anforderungen: SAFE-01 bis SAFE-04, JOB-05, RES-02.

Nicht in dieser Phase: die Erkennung selbst (NER/Regex-Qualität), Review-UI-Ausbau, Auto-Verarbeitung, Admin-Oberfläche.

</domain>

<decisions>
## Implementation Decisions

### Ablehnungstexte (Owner 16.11.2026)
- **D-02-01:** Wortlaut-Linie: je Grund ein Satz in Alltagssprache PLUS Abhilfe-Satz, DE/EN/FR (Beispiel: "Die Datei ist passwortgeschützt. Passwort entfernen und erneut starten."). Zielgruppe Behörden, keine technischen Kürzel.
- **D-02-02:** Ort: der Ablehnungsgrund steht an der Dateikarte in der Review-Oberfläche (gleiche Fläche wie die Statuskarten aus Phase 1). KEINE Nextcloud-Benachrichtigung je Ablehnung.
- **D-02-03:** Alle neuen nutzersichtbaren Texte dem Owner vor dem Bau zeigen (bestehende UI-Abnahme-Regel), dreisprachig im Gleichstand.

### Signierte PDFs (Owner 16.11.2026)
- **D-02-04:** Blockierende Bestätigung: Die Analyse einer signierten PDF startet erst, wenn der Nutzer den Hinweis bestätigt hat ("Die Signatur geht bei der Schwärzung verloren. Fortfahren?"). Bestätigung und Hinweis stehen im Protokoll (JOB-05). Kein stiller Durchlauf.

### Restrisiko Prozessisolation (Owner 16.11.2026)
- **D-02-05:** Linie: Accepted Risk mit weicher Isolation. Kindprozesse bekommen immer: geleerte Umgebung (kein AppAPI-Geheimnis), eigene Prozessgruppe mit Gruppen-Kill, rlimits (CPU-Zeit, Speicher, Dateigröße), Zeitdeckel; seccomp/Namespaces soweit unter HaRP/Docker möglich. Was nicht geht, wird als AR dokumentiert und dem Owner EINZELN vorgelegt (bestehende AR-Praxis). Kein Funktionsverzicht allein wegen fehlendem bubblewrap.
- **D-02-06:** Research misst, was unter HaRP/Docker tatsächlich verfügbar ist (Roadmap-Research-Flag), inkl. LibreOffice-25.2-Härtungsschlüssel mit Netzwerkmitschnitt.

### Grenzen (Owner 16.11.2026)
- **D-02-07:** Alle Grenzen (300 Seiten, Objekt-/Pixel-Deckel, ZIP-Größe, Kompressionsrate, Einträge, Pfadlängen) sind in Phase 2 FESTE, begründete Konstanten mit Tests. Keine Admin-Einstellbarkeit; die kommt höchstens später mit der Admin-Oberfläche bei Nachfrage.
- **D-02-08:** Der 300-Seiten-Deckel (und alle anderen Grenzen) gilt für JEDEN Analyse-Weg gleich, auch für die spätere Auto-Verarbeitung: ein Deckel, ein Text, ein Test.

### Übernommen aus Phase 1 / Projektregeln (nicht neu verhandelt)
- Kein Dokumentinhalt, kein Befund, keine Telemetrie verlässt den Server; die Modell-Downloads sind die einzigen ausgehenden Verbindungen.
- Logging-Härtung aus Phase 1 (kein Exception-Text, LOG_CONTEXT_KEYS-Gate) gilt für alle neuen Codepfade.
- Security-Audit am Phasenende ist Pflicht (SECURITY.md, offene Threats blockieren); ARs einzeln zum Owner.
- Commits street1983nk, Pushes nur HEAD:phase-02 nach Owner-Freigabe (Muster Phase 1: Phasen-Branch, Merge nach main erst nach Abnahme-Frage).

### Claude's Discretion
- Aufbau der Vorprüfung (Magic-Bytes-Bibliothek vs. eigene Signaturen, Prüfreihenfolge, Fehlerklassen).
- Korpus-Erzeugung (Bomben, XXE, Doppelnamen, External-Rels) per Skript in CI, keine Binärdateien im Repo.
- Technik der Netzabschaltung je Bibliothek (tldextract-Snapshot, Presidio-Modelle lokal, GLiNER2 offline) nach Research-Befund.
- Schnitt der Kindprozess-API (ein Runner-Modul, das alle Parser kapselt) nach AV-/Findling-Mustern.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase und Anforderungen
- `.planning/ROADMAP.md` Phase 2 (Ziel, 4 Erfolgskriterien, Research-Flag: Netz-Namespace/Prozessisolation unter HaRP/Docker, LibreOffice-25.2-Härtungsschlüssel mit Netzwerkmitschnitt)
- `.planning/REQUIREMENTS.md` SAFE-01 bis SAFE-04, JOB-05, RES-02

### Frühere Entscheide
- `.planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-CONTEXT.md` (Gerüst-Entscheide, UI-Flächen)
- `.planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-SECURITY.md` (103 Threats, Logging-Gates, AR-Praxis)

### Wiederverwendbare Muster
- AV-Repo `C:/Users/Student/nextcloud-audio-video-search` backend/src/audio_video_search_backend/ (Kindprozess je Job-Block, memory_guard, Worker-Muster)
- Findling `C:/Users/Student/nextcloud-search/backend/src/findling/memory_guard.py` (cgroup-Headroom, rlimit-Praxis)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/` (Phase-1-Gerüst): FastAPI-ExApp, Queue/Claim, Statuskarten-Weg in der Review-UI; Ablehnungsgründe docken an den bestehenden Status-/Kartenweg an.
- Workflow-Gates (test_workflows.py, test_workflow_pins.py) und security.yml (pip-audit in backend/) bestehen; neue CI-Jobs (Korpus, --network none) folgen dem Muster.

### Established Patterns
- Fail-closed als Grundlinie (Phase-1-Audit); Ablehnung ist der sichere Pfad.
- Alle nutzersichtbaren Texte DE/EN/FR, Deutsch zuerst, echte Umlaute; Entwürfe vor dem Bau zum Owner.

### Integration Points
- Review-UI-Dateikarte (Statusfläche aus Phase 1) für Gründe und die Signatur-Bestätigung.
- Protokoll (JOB-05) für Signatur-Hinweis und Bestätigung.

</code_context>

<specifics>
## Specific Ideas

- Signatur-Bestätigungstext sinngemäß "Die Signatur geht bei der Schwärzung verloren. Fortfahren?" (Wortlaut vor dem Bau zeigen).
- Ablehnungs-Beispielton: "Die Datei ist passwortgeschützt. Passwort entfernen und erneut starten."

</specifics>

<deferred>
## Deferred Ideas

- Admin-Einstellbarkeit der Grenzen (erst mit Admin-Oberfläche, bei Nachfrage).

</deferred>

---

*Phase: 02-sicherer-dateieingang-und-kindprozess-sandbox*
*Context gathered: 2026-11-16*
