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

### Owner-Entscheide nach der Research (16.11.2026, F1 bis F6 aus 02-RESEARCH.md)
- **D-02-09 (F1):** Der Erkennungsstapel (Presidio, spaCy, GLiNER2, torch-cpu, transformers) kommt schon in Phase 2 exakt gepinnt ins Image; Modelle nur im CI-Cache. Der --network-none-Beweis (RES-02) läuft am echten Produktions-Image. Phase 3 baut auf fertiger Basis.
- **D-02-10 (F2):** PDF nur mit Besitzerpasswort (öffnet ohne Passwort) wird ANGENOMMEN, mit Protokolleintrag, dass der Besitzerschutz der Quelle nicht in die Ausgabe übernommen wird. Nutzerpasswort-geschützte PDFs bleiben abgelehnt (JOB-05).
- **D-02-11 (F3):** Zeigt die Laufzeit-Probe, dass seccomp im konkreten Container nicht verfügbar ist, laufen DOCX/ODT TROTZDEM über LibreOffice: weiche Isolation bleibt (rlimits, Prozessgruppe, geleerte Umgebung, Bereiniger vor LibreOffice), der Status zeigt dem Admin den geminderten Schutz; als AR dokumentiert (Linie D-02-05).
- **D-02-12 (F4):** Entfernte Makros werden an der Dateikarte gemeldet ("Makros wurden für die Analyse entfernt", DE/EN/FR, Wortlaut vor dem Bau zeigen) UND protokolliert.
- **D-02-13 (F5):** Grenzwert-Tabelle bestätigt: 300 Seiten, 500 000 PDF-Objekte, Seitenmaß max 14 400 pt, Bilder max 100 Megapixel, ZIP-Grenzen nach Findling-Muster (entpackte Gesamtgröße, Kompressionsrate, Eintragszahl, Pfade, Doppelnamen inkl. Groß/Klein- und Normalisierungs-Dubletten); jede Konstante mit Begründung und Test. RLIMIT_AS für LibreOffice erst nach Messung im Container.
- **D-02-14 (F6):** Dockerfile: frpc-Binary auf Modus 0711 (statt 0755), start.sh byteweise unverändert; die Schutzwirkung (Annahme A1) wird in CI gemessen, sonst zurück.
- Research-Kernbefunde für die Pläne: Server ist PID 1 (exec-Kette), Geheimnis-Lesewege /proc/1/environ, frpc-Umgebung, /frpc.toml, /certs/frp/client.key; Abhilfen prctl(PR_SET_DUMPABLE, 0), Landlock-Dateiregeln im Jail, seccomp-Filter gegen socket(AF_INET...); bubblewrap fällt aus (Docker-Standardprofil sperrt unshare/setns/clone-Namespaces); Jail als eigenes Startprogramm (python -I -m ...sandbox.jail) statt preexec_fn (Threads); killpg + waitpid(-pgid, WNOHANG), NIE waitpid(-1) (asyncio), KEIN RLIMIT_NPROC (uid-10001-weite Zählung trifft Findling/AV); LibreOffice-Schlüssel (DisableMacrosExecution, MacroSecurityLevel=3, BlockUntrustedRefererLinks, DisableActiveContent, DisablePythonRuntime, DisableOLEAutomation, LoadExoticFileFormats=0, Writer Update/Link=2, Update/Field=false); Hauptlinie Bereiniger vor LibreOffice (Gotenberg-Muster: externe Rels, attachedTemplate, INCLUDEPICTURE/LINK/DDE, altChunk, vbaProject, ODF-xlink/Basic/Ereignisse); Netzbeweis Kanarienserver auf Loopback in --network none plus tcpdump an docker0; passwortgeschütztes DOCX = CFB mit EncryptedPackage, verschlüsseltes ODT = manifest:encryption-data; E2E-Prüfung in PHP am Ordner-Flag (nicht an der Datei); tldextract TLD_EXTRACTOR mit suffix_list_urls=() + TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS=""; gliner2.api_client lässt sich nicht am Import hindern, nur an der Nutzung (Test) plus Audit-Hook als Netz-Tripwire.

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
