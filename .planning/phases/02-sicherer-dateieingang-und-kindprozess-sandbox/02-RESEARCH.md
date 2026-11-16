# Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox - Research

**Researched:** 2026-11-16
**Domain:** Prozessisolation ohne Privilegien unter Docker/HaRP (rlimits, seccomp, Landlock, Prozessgruppen), sichere Vorprüfung von PDF/OOXML/ODF, LibreOffice-Härtung, Offline-Betrieb von Presidio/tldextract/GLiNER2
**Confidence:** MEDIUM (Quellen und Code geprüft; alle Container-Aussagen sind ohne lokalen Docker-Lauf erhoben und müssen in CI gemessen werden, so wie D-02-06 es verlangt)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Ablehnungstexte (Owner 16.11.2026)**
- **D-02-01:** Wortlaut-Linie: je Grund ein Satz in Alltagssprache PLUS Abhilfe-Satz, DE/EN/FR (Beispiel: "Die Datei ist passwortgeschützt. Passwort entfernen und erneut starten."). Zielgruppe Behörden, keine technischen Kürzel.
- **D-02-02:** Ort: der Ablehnungsgrund steht an der Dateikarte in der Review-Oberfläche (gleiche Fläche wie die Statuskarten aus Phase 1). KEINE Nextcloud-Benachrichtigung je Ablehnung.
- **D-02-03:** Alle neuen nutzersichtbaren Texte dem Owner vor dem Bau zeigen (bestehende UI-Abnahme-Regel), dreisprachig im Gleichstand.

**Signierte PDFs (Owner 16.11.2026)**
- **D-02-04:** Blockierende Bestätigung: Die Analyse einer signierten PDF startet erst, wenn der Nutzer den Hinweis bestätigt hat ("Die Signatur geht bei der Schwärzung verloren. Fortfahren?"). Bestätigung und Hinweis stehen im Protokoll (JOB-05). Kein stiller Durchlauf.

**Restrisiko Prozessisolation (Owner 16.11.2026)**
- **D-02-05:** Linie: Accepted Risk mit weicher Isolation. Kindprozesse bekommen immer: geleerte Umgebung (kein AppAPI-Geheimnis), eigene Prozessgruppe mit Gruppen-Kill, rlimits (CPU-Zeit, Speicher, Dateigröße), Zeitdeckel; seccomp/Namespaces soweit unter HaRP/Docker möglich. Was nicht geht, wird als AR dokumentiert und dem Owner EINZELN vorgelegt (bestehende AR-Praxis). Kein Funktionsverzicht allein wegen fehlendem bubblewrap.
- **D-02-06:** Research misst, was unter HaRP/Docker tatsächlich verfügbar ist (Roadmap-Research-Flag), inkl. LibreOffice-25.2-Härtungsschlüssel mit Netzwerkmitschnitt.

**Grenzen (Owner 16.11.2026)**
- **D-02-07:** Alle Grenzen (300 Seiten, Objekt-/Pixel-Deckel, ZIP-Größe, Kompressionsrate, Einträge, Pfadlängen) sind in Phase 2 FESTE, begründete Konstanten mit Tests. Keine Admin-Einstellbarkeit; die kommt höchstens später mit der Admin-Oberfläche bei Nachfrage.
- **D-02-08:** Der 300-Seiten-Deckel (und alle anderen Grenzen) gilt für JEDEN Analyse-Weg gleich, auch für die spätere Auto-Verarbeitung: ein Deckel, ein Text, ein Test.

**Übernommen aus Phase 1 / Projektregeln (nicht neu verhandelt)**
- Kein Dokumentinhalt, kein Befund, keine Telemetrie verlässt den Server; die Modell-Downloads sind die einzigen ausgehenden Verbindungen.
- Logging-Härtung aus Phase 1 (kein Exception-Text, LOG_CONTEXT_KEYS-Gate) gilt für alle neuen Codepfade.
- Security-Audit am Phasenende ist Pflicht (SECURITY.md, offene Threats blockieren); ARs einzeln zum Owner.
- Commits street1983nk, Pushes nur HEAD:phase-02 nach Owner-Freigabe (Muster Phase 1: Phasen-Branch, Merge nach main erst nach Abnahme-Frage).

### Claude's Discretion
- Aufbau der Vorprüfung (Magic-Bytes-Bibliothek vs. eigene Signaturen, Prüfreihenfolge, Fehlerklassen).
- Korpus-Erzeugung (Bomben, XXE, Doppelnamen, External-Rels) per Skript in CI, keine Binärdateien im Repo.
- Technik der Netzabschaltung je Bibliothek (tldextract-Snapshot, Presidio-Modelle lokal, GLiNER2 offline) nach Research-Befund.
- Schnitt der Kindprozess-API (ein Runner-Modul, das alle Parser kapselt) nach AV-/Findling-Mustern.

### Deferred Ideas (OUT OF SCOPE)
- Admin-Einstellbarkeit der Grenzen (erst mit Admin-Oberfläche, bei Nachfrage).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SAFE-01 | Alle Parser (PDF, ZIP, XML, LibreOffice, OCR) laufen in Kindprozessen ohne AppAPI-Geheimnis in der Umgebung, mit Zeit- und Speichergrenzen und Kill der ganzen Prozessgruppe | Jail-Startprogramm (Pattern 1), Befund "Geheimnis über /proc und Dateien lesbar" (Pitfall 1), Zombie-Befund PID 1 (Pitfall 2), rlimit-Tabelle |
| SAFE-02 | Vorprüfung vor dem Parsen: Magic-Bytes, Grenzen für Seiten, Objekte, Pixel, ZIP-Größe, Kompressionsrate, Einträge, Pfade, doppelte Namen; XML ohne DOCTYPE und Entitäten | Pattern 3 (Vorprüfung in drei Stufen), Findling-`archive.py` als Vorlage, Grenzwert-Tabelle, Pitfall 4 (Groß/Klein-Doppelnamen) |
| SAFE-03 | Makros und externe Beziehungen werden vor LibreOffice entfernt; Test-DOCX mit externem Bild löst keinen Netzaufruf aus | Pattern 4 (Bereiniger), LibreOffice-25.2-Schlüssel aus dem Schema belegt, Netzwerkmitschnitt-Verfahren |
| SAFE-04 | Bomben-, XXE-, Doppelnamen- und External-Rels-Korpus läuft in CI und wird abgewiesen, ohne den Container zu gefährden | Korpus-Liste mit Erzeugungsweg (pytest-Fixtures + `ci/make_corpus.py`), Container-Teststufe |
| JOB-05 | Verschlüsselte, E2E-verschlüsselte, defekte oder zu große Dateien (über 300 Seiten) mit konkretem Grund abgelehnt; signierte PDFs vorher gemeldet, Signatur fällt weg, steht im Protokoll | Erkennungstabelle (wo welche Prüfung läuft), neue Reason-Wörter, Bestätigungs-Status, JobEvent-Aktionen |
| RES-02 | Versteckte Netzaufrufe der Bibliotheken abgestellt (Modell-Nachladen, Public Suffix List, Remote-Config) | tldextract 5.4.0 Code-Befund, GLiNER2 2.1.0 Ladepfade, Audit-Hook-Test plus `--network none`-Lauf |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Stack fest: Presidio 2.2.366, spaCy 3.8.18, GLiNER2 2.1.0 (ohne `[local]`), torch 2.15.0+cpu, transformers 4.57.6, PyMuPDF 2.1, pikepdf, pypdf, lxml 6.1.3, LibreOffice `libreoffice-writer-nogui` aus trixie/trixie-security, Tesseract 5.5.0 exakt gepinnt. Nicht neu wählen.
- "What NOT to Use" gilt: kein `defusedxml.lxml`, kein bubblewrap im Container, kein `GLiNER2.from_pretrained("<repo-id>")`, kein `GLiNER2API`/`API`, kein Presidio `AnalyzerEngine()` ohne eigene `NlpEngine`, kein Presidio-`EmailRecognizer` mit Online-PSL, keine LibreOffice-Dauerinstanz, kein gemeinsames LO-Profil, Netzprüfung nie nur "lokal ausprobiert".
- LibreOffice: je Auftrag eigener Prozess, eigenes Profil (`-env:UserInstallation`), harte Zeitgrenze, ganze Prozessgruppe beenden, Temp löschen, nie gleichzeitig mit dem Erkenner-Worker.
- Kein `RLIMIT_AS` für den torch-Worker; für LibreOffice erst nach Messung.
- Container: uid 10001, keine Capabilities, kein Root-Moment.
- Qualitäts-Gates: ruff-Vollsatz, pyright basic, vulture lokal grün; Coverage-Grenze 90 (pyproject).
- Texte DE/EN/FR im Gleichstand, Deutsch zuerst, echte Umlaute, keine Gedankenstriche, keine Emojis; Umlaute nur in Prosa, nie in Code.
- Testkorpora nicht ins Repo (Lizenz); Bomben werden erzeugt.
- Prozess: vor Push/Merge/Kommentar Owner fragen; Agenten nie `python -`/`python -c`; GitHub-API sparsam; Docker lokal aus.

## Summary

Phase 1 hat das Gerüst schon gelegt: `workers/child.py` startet Kinder mit leerer Umgebung (`SAFE_ENV`), eigener Sitzung (`start_new_session=True`) und `killpg` beim Zeitlimit; `workers/sniff.py` erkennt PDF/DOCX/ODT an den Bytes; `workers/soffice.py` nutzt ein Profil je Auftrag. Phase 2 baut darauf auf. Drei Befunde ändern aber das Bild gegenüber CLAUDE.md und dem Phase-1-Stand:

1. **Die leere Umgebung allein schützt das Geheimnis nicht.** Der Server ist im Container PID 1 (`entrypoint.sh` und `start.sh` enden beide mit `exec`), läuft wie jedes Kind als uid 10001, und `/proc/<pid>/environ` eines gleichen Nutzers ist lesbar. Ein übernommener Parser liest also `APP_SECRET` aus `/proc/1/environ` oder aus der Umgebung von `frpc`, dazu `HP_SHARED_KEY` aus `/frpc.toml` und den Schlüssel `/certs/frp/client.key`. Abhilfe ohne Privilegien: `prctl(PR_SET_DUMPABLE, 0)` im Server, Landlock-Dateiregeln (die zugleich `ptrace`-Zugriffe auf Prozesse außerhalb der Sandbox sperren) und `frpc` mit Modus 0711. Der Test aus Erfolgskriterium 1 muss genau diese Lesewege prüfen, nicht nur `os.environ` im Kind.
2. **Docker-seccomp sperrt Namespaces, erlaubt aber eigene Filter.** Im Standardprofil von moby stehen `unshare`, `setns` und `clone` mit Namespace-Flags nur mit `CAP_SYS_ADMIN` offen, `clone3` liefert ENOSYS; bubblewrap scheidet damit aus (bestätigt CLAUDE.md). `seccomp`, `prctl` und alle drei Landlock-Systemaufrufe stehen dagegen in der allgemeinen Erlaubnisliste. HaRP legt Container ohne `SecurityOpt`, ohne `Init`, ohne `PidsLimit` an (Quelle `haproxy_agent.py`). Damit geht ohne Capabilities: `PR_SET_NO_NEW_PRIVS`, ein seccomp-Filter, der `socket(AF_INET/AF_INET6/...)` verweigert (Netzsperre nur für Kinder, auch für LibreOffice), und Landlock für Dateien. Das ist mehr als die "weiche Isolation" aus D-02-05 und kostet keine Funktion.
3. **LibreOffice-Zombies sind real.** Weil Python PID 1 ist und kein `tini` läuft, landen verwaiste Enkel (etwa `soffice.bin` nach dem Tod von `oosplash`) beim Server und bleiben Zombies, bis jemand `waitpid` ruft. Nach jedem `killpg` muss der Server die Gruppe mit `os.waitpid(-pgid, WNOHANG)` einsammeln.

Für die Vorprüfung gibt es in Findling (`extract/archive.py`, gemessen und auditiert) eine fertige Vorlage für ZIP-Grenzen in drei Stufen (Zentralverzeichnis zählen, Deklarationen prüfen, lesen mit Zähler). PDF-Struktur prüft man in einem Kind mit pikepdf (qpdf), bevor PyMuPDF rendert. LibreOffice 25.2 hat belegte Schlüssel (`DisableMacrosExecution`, `MacroSecurityLevel`, `BlockUntrustedRefererLinks`, `DisableActiveContent`, `DisablePythonRuntime`, Writer `Update/Link=2`, `Update/Field=false`), aber die Hauptlinie ist wie bei Gotenberg: externe Bezüge vor LibreOffice aus dem Dokument entfernen, die Schlüssel sind die zweite Schicht und die seccomp-Netzsperre die dritte.

**Primary recommendation:** Ein Modul `sandbox/` mit einem Jail-Startprogramm (`python -I -m pii_redaction_backend.sandbox.jail <profil> -- <befehl>`), das in einem frischen, einfädigen Prozess rlimits setzt, `NO_NEW_PRIVS` setzt, Landlock und seccomp lädt und dann `execv` macht; davor eine Vorprüfung als eigenes Kind, die mit geschlossener Grundliste antwortet; beim Start eine Fähigkeitsprobe, deren Ergebnis in `/status` steht und fehlende Schichten als AR sichtbar macht.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| E2E-Erkennung (Ordner mit Verschlüsselungsflag) | PHP-App (`JobService::start`, `FileAccess`) | - | Nur der Server kennt den Dateibaum; der Container sieht nie einen Pfad |
| Erwartetes Format aus dem Nextcloud-MIME (Endung) | PHP-App | Container vergleicht | MIME in Nextcloud folgt der Endung; Container braucht das Erwartete für "falsch benannt" |
| Magic-Bytes, ZIP-, XML-, PDF-Vorprüfung | Container, Kindprozess (Jail) | - | Parsen fremder Bytes nie im Server- und nie im PHP-Prozess |
| Verschlüsselt/signiert/defekt/zu groß erkennen | Container, Kind "precheck" | PHP zeigt Grund | Erkennung braucht einen PDF-/ZIP-Parser |
| Bestätigung signierter PDF, Protokoll | PHP-App (Status, JobEvent, Review-Karte) | Container meldet Befund | Nutzerentscheidung und Protokoll gehören zur PHP-Seite (JOB-05) |
| Bereinigung (Makros, externe Bezüge) vor LibreOffice | Container, Kind "sanitize" | - | lxml auf fremdem XML, also im Jail |
| Prozessisolation (rlimits, seccomp, Landlock, Gruppen-Kill, Reaper) | Container, Server + Jail | Dockerfile (frpc 0711) | Kernel-Mechanismen, vom Container selbst gesetzt |
| Ablehnungstexte DE/EN/FR | PHP-App (l10n, Review-Karte) | - | Texte werden in PHP/JS übersetzt (Phase-1-Muster `startToast.ts`, Review-Karte) |
| Offline-Konfiguration Presidio/tldextract/GLiNER2 | Container (Worker-Start) | Dockerfile ENV | Bibliotheksverhalten, im Prozess gesetzt |

## Standard Stack

### Core (schon festgelegt, hier nur Rolle in Phase 2)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pikepdf | 10.17.0 laut CLAUDE.md; PyPI aktuell **10.18.2** [VERIFIED: PyPI JSON 16.11.2026] | Strukturvorprüfung PDF: Verschlüsselung (`PasswordError`), Seiten, Objektzahl, Bildmaße, `/SigFlags`, `/F`-Ströme | qpdf-Kern, robust gegen kaputte xref (Rekonstruktion), schon im Stack; pypdf (reines Python) hatte 2025/2026 mehrere DoS-Fehler und ist nur Prüfer |
| lxml | 6.1.3 [VERIFIED: PyPI] | XML-Prüfung und Bereinigung in DOCX/ODT | Stack-Vorgabe; Parser fest konfiguriert |
| PyMuPDF | 2.1 (im Image) | Rendern erst NACH der Vorprüfung | Phase 1 |
| LibreOffice | `libreoffice-writer-nogui` 4:25.2.3-2+deb13u**9** [VERIFIED: packages.debian.org, trixie] | DOCX/ODT zu PDF | CLAUDE.md nennt u8, inzwischen u9: Debian-Sicherheitsupdates laufen wie erwartet |
| Python-Standardbibliothek | 3.13 | `resource`, `os.killpg`, `os.waitpid`, `zipfile`, `ctypes`, `sys.addaudithook` | keine Zusatzpakete für die Sandbox |
| libseccomp (System) | `libseccomp2` ist im Basis-Image, weil `apt` davon abhängt [VERIFIED: packages.debian.org/trixie/apt, Depends libseccomp2 >= 2.4.2, nicht auf riscv64] | seccomp-Filter über `ctypes.CDLL("libseccomp.so.2")` | Bibliothek löst Systemaufruf-Nummern je Architektur (amd64/arm64) selbst auf; kein handgeschriebenes BPF |

### Supporting (nur für den RES-02-Beweis, siehe Open Question 1)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| presidio-analyzer, spacy, gliner2, torch+cpu, transformers | wie CLAUDE.md | Offline-Beweis `--network none` | wenn der Planer die Erkennungs-Abhängigkeiten schon in Phase 2 ins Image nimmt |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| eigene Magic-Signaturen (`sniff.py`) | `python-magic` 0.4.27 | letzter Release 2022 [VERIFIED: PyPI], braucht libmagic (weiterer C-Parser auf fremden Bytes), unterscheidet DOCX/verschlüsseltes OOXML/ODT nicht verlässlich. Nein |
| ctypes auf libseccomp | `pyseccomp` 0.1.2 | letzter Release 02.01.2021 [VERIFIED: PyPI]; ist selbst nur ein ctypes-Wrapper. Nein, eigenes kleines Modul nach gleichem Muster |
| eigenes ctypes-Landlock | PyPI `landlock` 1.0.0.dev5 | nur Dev-Release (03.05.2025), ein Betreuer [VERIFIED: PyPI]. Nein |
| bubblewrap 0.12.0 | - | braucht `unshare(CLONE_NEWUSER)`, im Docker-Standardprofil nur mit `CAP_SYS_ADMIN` [VERIFIED: moby/profiles default.json] |
| tcpdump im Container | Loopback-Kanarienserver + tcpdump auf dem CI-Host an `docker0` | Container hat keine Capabilities für Mitschnitt; Host-Runner hat sudo |

**Installation:** keine neuen Laufzeitpakete für die Sandbox. pikepdf und lxml kommen in `[project].dependencies` (exakt gepinnt, Lock aktualisieren). Für den Offline-Beweis siehe Open Question 1.

## Package Legitimacy Audit

slopcheck konnte nicht laufen (Installation in dieser Sitzung vom Berechtigungssystem abgelehnt). Alle Pakete stammen aus der Stack-Festlegung in CLAUDE.md (dort einzeln über die PyPI-JSON-API geprüft, 07.11.2026); heute erneut über PyPI abgefragt: pikepdf 10.18.2, lxml 6.1.3, pypdf 7.1.0. Keine neuen Paketnamen in dieser Phase.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pikepdf | PyPI | > 7 Jahre | hoch | github.com/pikepdf/pikepdf | nicht gelaufen | Approved (Stack), [ASSUMED] bis Prüfung |
| lxml | PyPI | > 15 Jahre | sehr hoch | github.com/lxml/lxml | nicht gelaufen | Approved (Stack), [ASSUMED] bis Prüfung |
| pyseccomp | PyPI | 2020/2021 | gering | github.com/cptpcrd/pyseccomp | nicht gelaufen | NICHT verwenden (veraltet) |
| landlock | PyPI | Dev-Release 2025 | gering | github.com/Edward-Knight/landlock | nicht gelaufen | NICHT verwenden |
| python-magic | PyPI | letzter Release 2022 | hoch | github.com/ahupp/python-magic | nicht gelaufen | NICHT verwenden |

**Packages removed due to slopcheck [SLOP] verdict:** keine (nicht gelaufen)
**Packages flagged as suspicious [SUS]:** keine; Planer setzt für pikepdf/lxml-Pin-Änderungen den üblichen Lock-Diff-Check, kein eigener human-verify nötig, weil beide schon Owner-freigegebener Stack sind.

## Architecture Patterns

### System Architecture Diagram

```
Nutzer klickt "Prüfen" (Files)
        |
        v
PHP JobService::start ──> E2E-Ordner? ──ja──> refused(e2e_encrypted) ──> Toast/Karte
        |  MIME erlaubt? (Endung)          
        |  expected = pdf|docx|odt
        v
Queue (Claim mit expected, confirmSignature)
        |
        v
Container Runner._analyze (Server-Prozess, PR_SET_DUMPABLE=0, Reaper)
        |
        |-- fetch (Gateway, Größendeckel) --> work/<job>/src
        |
        v
[Kind "precheck" im Jail: rlimits + NO_NEW_PRIVS + Landlock + seccomp(kein INET)]
   Stufe A Magic-Bytes ──> CFB? (EncryptedPackage = encrypted, sonst unsupported)
        |                  passt nicht zu expected? ──> wrong_type
   Stufe B Container-Struktur
        |  ZIP: EOCD/Zentralverzeichnis zählen, Namen (Traversal, Doppel, Groß/Klein),
        |       Deklarationen (Summe, Rate), Verschlüsselungs-Flag, ODF-manifest encryption-data
        |  PDF: pikepdf open (PasswordError -> encrypted), Seiten <= 300, Objekte, Seitenmaß,
        |       Bildpixel, /F-Ströme, /SigFlags + /Sig-Felder -> signed
   Stufe C XML-Teile parsen (resolve_entities=False, no_network, huge_tree=False, DOCTYPE -> Abbruch)
        |
        v  verdict.json (geschlossene Liste) 
   rejected ──> ack(failed, reason) ──> Karte mit Satz + Abhilfe
   signed && !confirmed ──> ack(confirm) ──> PHP Status "confirm" ──> Dialog ──> Bestätigung
        |                                                      (JobEvent: signature_notice, signature_confirmed) ──> neu in Queue
   ok
        |
        v  (nur DOCX/ODT)
[Kind "sanitize" im Jail] Makros, externe Rels, Felder mit URL, altChunk, attachedTemplate,
                          ODF xlink:href nach außen, Skripte, Ereignisse entfernen ──> clean.docx/odt
        |
        v
[soffice im Jail, gehärtetes Profil, Netz per seccomp zu] ──> PDF ──> Seitenzahl <= 300 erneut prüfen
        |
        v
[Kind "render" im Jail] ──> page-1.png ──> ack(review)
        |
   nach jedem Kind: killpg(pgid) bei Zeitüberschreitung, dann waitpid(-pgid, WNOHANG) bis leer
```

### Recommended Project Structure
```
backend/src/pii_redaction_backend/
├── sandbox/
│   ├── __init__.py
│   ├── jail.py          # Startprogramm: rlimits, NO_NEW_PRIVS, Landlock, seccomp, dann execv
│   ├── profiles.py      # feste Profile je Kindart (render, precheck, sanitize, soffice, ocr, detect)
│   ├── seccomp.py       # ctypes auf libseccomp.so.2, Denylist-Filter
│   ├── landlock.py      # ctypes, ABI-Probe, Pfadregeln
│   ├── probe.py         # Fähigkeitsprobe beim Start, Ergebnis für /status
│   └── reaper.py        # PR_SET_CHILD_SUBREAPER, Gruppe einsammeln
├── intake/
│   ├── limits.py        # ALLE festen Grenzen als Konstanten mit Begründung (D-02-07)
│   ├── magic.py         # Nachfolger von workers/sniff.py (CFB, ODF-Verschlüsselung, docm)
│   ├── zipcheck.py      # Findling-archive.py Stufe 1+2, ohne Leseteil
│   ├── xmlcheck.py      # ein einziger Parser-Fabrikpunkt
│   ├── pdfcheck.py      # pikepdf-Prüfung
│   └── sanitize.py      # Bereiniger DOCX/ODT
├── workers/
│   ├── child.py         # run_child bekommt profile=..., startet immer über jail
│   ├── precheck.py      # Kind-Einstieg: Vorprüfung, schreibt verdict.json
│   ├── sanitize.py      # Kind-Einstieg: Bereinigung
│   ├── render.py, soffice.py, placeholder.py
│   └── lo_profile/registrymodifications.xcu  # Paketdaten, wird je Auftrag kopiert
└── offline.py           # Offline-Schalter Presidio/tldextract/GLiNER2 (RES-02)
```

### Pattern 1: Jail-Startprogramm statt `preexec_fn`
**What:** Das Kind wird nicht direkt gestartet, sondern als `python -I -m pii_redaction_backend.sandbox.jail <profil> -- <argv...>`. Das Jail läuft als frischer Prozess mit nur einem Faden, setzt alles und ersetzt sich mit `os.execv` durch das Ziel (soffice, tesseract, python-Kind). Die Sitzung entsteht weiter über `start_new_session=True` (im C-Teil von CPython, sicher).
**Why:** `preexec_fn` ist im mehrfädigen Server (asyncio + `to_thread`) nach `fork` unsicher: ctypes-Aufrufe in libseccomp allozieren Speicher, und ein im Moment des `fork` gehaltenes malloc-Lock eines anderen Fadens führt zum Hänger. CPython warnt selbst davor [CITED: docs.python.org/3/library/subprocess.html, "preexec_fn ... not safe to use in the presence of threads"]. Kosten: ein Interpreterstart mehr je Kind (ca. 50 bis 100 ms), bei einem Auftrag zur Zeit unerheblich.
**Reihenfolge im Jail:**
1. `resource.setrlimit` je Profil (Tabelle unten), immer `RLIMIT_CORE=(0,0)`.
2. `prctl(PR_SET_NO_NEW_PRIVS, 1)` über ctypes (`libc.prctl(38, 1, 0, 0, 0)`).
3. Landlock: ABI abfragen, Regelsatz mit allen bekannten FS-Rechten der ABI, erlaubte Pfade hinzufügen, `landlock_restrict_self`. Ab ABI 4 auch TCP bind/connect sperren, ab ABI 6 `SCOPE_ABSTRACT_UNIX_SOCKET | SCOPE_SIGNAL`.
4. seccomp über libseccomp: Standard ALLOW, Regeln ERRNO(EACCES) für `socket` mit Domäne AF_INET(2), AF_INET6(10), AF_PACKET(17), AF_NETLINK(16), dazu `ptrace`, `process_vm_readv`, `process_vm_writev`, `io_uring_setup`, `bpf`, `perf_event_open`, `userfaultfd`, `keyctl`, `add_key`, `request_key`. AF_UNIX bleibt (LibreOffice braucht seine OSL-Pipe). Fremde Architekturen (x32/i386 auf amd64) bekommen die libseccomp-Standardaktion für "bad arch" (KILL).
5. `os.execv(ziel, argv)` mit der leeren Umgebung aus `child_env()`.
Fällt ein Schritt aus, entscheidet das Profil: Landlock/seccomp "nicht verfügbar" (ENOSYS/EOPNOTSUPP/EINVAL bei der ABI-Probe) wird protokolliert und der Lauf geht weiter (D-02-05, AR); ein Fehler NACH erfolgreicher Probe (etwa `restrict_self` scheitert) bricht ab (fail closed).

```python
# Source: Muster nach kernel.org userspace-api/landlock.rst und man 2 seccomp; Werte siehe Text
import ctypes, os, resource
libc = ctypes.CDLL(None, use_errno=True)
PR_SET_NO_NEW_PRIVS = 38
if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), "no_new_privs")

seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
SCMP_ACT_ALLOW = 0x7FFF0000
def SCMP_ACT_ERRNO(e): return 0x00050000 | (e & 0xFFFF)
ctx = seccomp.seccomp_init(SCMP_ACT_ALLOW)
nr = seccomp.seccomp_syscall_resolve_name(b"socket")
# struct scmp_arg_cmp {unsigned int arg; enum op; uint64 datum_a; uint64 datum_b;}, op SCMP_CMP_EQ = 4
# je Domäne: seccomp_rule_add_exact_array(ctx, ERRNO(EACCES), nr, 1, &cmp)
# danach seccomp_load(ctx); seccomp_release(ctx)
```

### Pattern 2: Gruppe töten UND einsammeln (Zombies)
**What:** Server setzt beim Start `prctl(PR_SET_CHILD_SUBREAPER, 1)` (unschädlich, wenn er ohnehin PID 1 ist; wichtig für Tests außerhalb des Containers). Nach jedem Kind, egal ob Erfolg, Fehler oder Zeitlimit: zuerst wartet asyncio auf den Gruppenführer (wie heute), dann `killpg(pgid, SIGKILL)` (auch bei Erfolg, gegen zurückgelassene Enkel) und eine Schleife `os.waitpid(-pgid, os.WNOHANG)` bis `ChildProcessError`.
**Why:** Verwaiste Enkel gehen an PID 1 = Server. `waitpid(-1)` ist tabu, weil es asyncio den Status eines eigenen Kindes stehlen kann; `waitpid(-pgid)` trifft nur die Gruppe, deren Führer schon eingesammelt ist.
**Test:** nach einem absichtlich hängenden Kind, das einen Enkel mit `sleep` startet: `/proc/*/stat` enthält keinen Prozess mit dieser pgid und keinen Zustand `Z`.

### Pattern 3: Vorprüfung in drei Stufen, ein Kind, eine geschlossene Antwort
**What:** `workers/precheck.py <src> <expected> <out.json>` im Jail (Profil `precheck`: CPU 60 s, AS 1 GiB, FSIZE 1 MiB, nur `src` lesbar, nur `out.json` schreibbar). Antwort ist ein Wort aus einer geschlossenen Liste plus Zahlen (Seiten, Signatur ja/nein), nie ein Name oder eine Meldung.
- **Stufe A, Bytes:** `%PDF-` irgendwo in den ersten 1024 Byte (PDF-Spezifikation erlaubt Vorspann; Acrobat sucht in 1024 Byte) [ASSUMED], aber Vorspann > 0 als eigener Grund `damaged` bewerten wäre zu streng: Empfehlung Header an Offset 0 verlangen und Vorspann ablehnen (Polyglot-Schutz). `PK\x03\x04` an Offset 0 für ZIP. `D0 CF 11 E0 A1 B1 1A E1` (CFB): Verzeichnis nach Strom `EncryptedPackage`/`EncryptionInfo` absuchen; gefunden = `encrypted` (passwortgeschütztes DOCX ist KEIN ZIP, sondern CFB) [CITED: MS-OFFCRYPTO 2.3.4.4 / ECMA-376 Agile Encryption], sonst `unsupported_format` (altes .doc). Vergleich mit `expected` aus dem Claim: anderes Format = `wrong_type`.
- **Stufe B, Struktur:** ZIP: Findling-`archive.py` Stufe 1 und 2 übernehmen (End-Record selbst finden, Zentralverzeichnis blockweise zählen bis Grenze+1, erst dann `ZipFile`), ergänzt um die DOCX-spezifischen Regeln (Pitfall 4). PDF: `pikepdf.open(src)` im Kind; `PasswordError` = `encrypted`; sonst Seiten, Objektzahl, Seitenmaße (MediaBox mal UserUnit), Bild-XObjects (Width*Height), Ströme mit `/F` (externe Datei) = `damaged`/unsicher, `/AcroForm /SigFlags & 1` oder Feld `/FT /Sig` mit `/V` = `signed`.
- **Stufe C, XML:** jedes `.xml`/`.rels`-Mitglied mit Deklarationsgröße unter dem Deckel streamend lesen (Zähler wie Findling Stufe 3) und mit der einen Parser-Fabrik parsen; `docinfo.doctype` nicht leer oder `docinfo.internalDTD` gesetzt = `unsafe_content`.

```python
# Source: lxml-Doku (lxml.de/parsing.html, XMLParser-Optionen); CLAUDE.md-Vorgabe
from lxml import etree
def make_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False, no_network=True, huge_tree=False,
        load_dtd=False, dtd_validation=False, remove_blank_text=False,
    )
def parse_part(data: bytes) -> etree._Element:
    root = etree.fromstring(data, make_parser())
    info = root.getroottree().docinfo
    if info.doctype or info.internalDTD is not None:
        raise UnsafeXml
    return root
```

### Pattern 4: Bereiniger vor LibreOffice (SAFE-03), Gotenberg-Linie
**What:** LibreOffice bekommt nie das Original, sondern eine Kopie, aus der alles entfernt ist, was nachladen oder ausführen kann. Gotenberg hat seit 8.34.0 dieselbe Linie: verlinkte Inhalte an der Quelle entfernen statt sich auf LibreOffice-Einstellungen zu verlassen [CITED: gotenberg.dev/docs/outbound-url-filtering, Suchergebnis; Seite selbst nicht abrufbar, MEDIUM].
**DOCX, zu entfernen bzw. zu neutralisieren:**
- jede Beziehung mit `TargetMode="External"` in allen `*.rels` (Bilder, `attachedTemplate` in `word/_rels/settings.xml.rels` = Vorlagen-Injektion, `oleObject`, `subDocument`, `frame`, Hyperlinks). Hyperlinks (`r:id` an `w:hyperlink`) dürfen bleiben, wenn nur das Ziel geleert wird; Bilder werden zur leeren Beziehung, die zugehörigen `a:blip r:link` entfernt.
- `vbaProject.bin`, `vbaData.xml`, `customizations`/`keyMapCustomizations`, ActiveX (`word/activeX/*`), eingebettete OLE-Pakete; Content-Type `macroEnabled` auf den normalen DOCX-Typ zurücksetzen.
- Feldcodes mit Nachladewirkung in `w:instrText`/`w:fldSimple`: `INCLUDEPICTURE`, `INCLUDETEXT`, `LINK`, `DDE`, `DDEAUTO`, `IMPORT` (Feld durch sein zwischengespeichertes Ergebnis ersetzen oder Feld entfernen).
- `w:altChunk` (`aFChunk`-Teile), `webSettings.xml` Frameset.
**ODT:** `xlink:href` mit Schema außer internem Paketpfad an `draw:image`, `draw:object`, `draw:object-ole`, `text:section-source`, `office:dde-source`/`text:dde-connection-decl`, `table:table-source`; `office:scripts`, `office:event-listeners`, Ordner `Basic/` und `Scripts/` samt Manifest-Einträgen.
**Danach:** Bereinigte Kopie erneut durch Stufe B/C (Gegenprobe), damit der Bereiniger nichts Neues erzeugt.
**Wichtig für spätere Phasen:** Diese Kopie ist nur LibreOffice-Eingabe. Was mit externen Links in der späteren geschwärzten Ausgabe passiert (eine URL kann selbst personenbezogen sein), entscheidet Phase 7.

### Pattern 5: LibreOffice-Profil je Auftrag, vorbefüllt
Schlüssel, im Schema von LibreOffice 25.2 belegt [VERIFIED: github.com/LibreOffice/core, Zweig libreoffice-25-2, `officecfg/registry/schema/org/openoffice/Office/Common.xcs` Zeilen 2308 bis 2580 und `Writer.xcs` Zeilen 1089 bis 1125]:

| Pfad | Eigenschaft | Wert | Schema-Beschreibung |
|------|-------------|------|---------------------|
| `/org.openoffice.Office.Common/Security/Scripting` | `DisableMacrosExecution` | `true` | "disable Basic, Beanshell, Javascript and Python scripts. If it is set to true, the MacroSecurityLevel is ignored" |
| `/org.openoffice.Office.Common/Security/Scripting` | `MacroSecurityLevel` | `3` | 0 bis 3, Standard 2 |
| `/org.openoffice.Office.Common/Security/Scripting` | `BlockUntrustedRefererLinks` | `true` | "block any links originating from documents that are not among the trusted locations" |
| `/org.openoffice.Office.Common/Security/Scripting` | `DisableActiveContent` | `true` | "only disables active embedded content (OLE) and DDE" |
| `/org.openoffice.Office.Common/Security/Scripting` | `DisablePythonRuntime` | `true` | Python-Laufzeit aus |
| `/org.openoffice.Office.Common/Security/Scripting` | `DisableOLEAutomation` | `true` | OLE-Automation aus |
| `/org.openoffice.Office.Common/Security/Scripting` | `CheckDocumentEvents` | `true` (Standard), zusätzlich `AllowedDocumentEventURLs` als leere Liste | Ereignis-Makros |
| `/org.openoffice.Office.Common/Security` | `LoadExoticFileFormats` | `0` | "Refuse loading without question" |
| `/org.openoffice.Office.Writer/Content/Update` | `Link` | `2` | 0 Always, 1 On Request (Standard), 2 Never |
| `/org.openoffice.Office.Writer/Content/Update` | `Field` | `false` | "fields ... updated during loading" |
| `/org.openoffice.Office.Jobs/Jobs/org.openoffice.Office.Jobs:Job['UpdateCheck']/Arguments` | `AutoCheckEnabled` | `false` | Update-Prüfung (Pfad aus hardentools; ob die Debian-nogui-Variante den Dienst überhaupt baut, ist offen [ASSUMED]) |

Format in `registrymodifications.xcu` (je Eintrag `<item oor:path="..."><prop oor:name="..." oor:op="fuse"><value>...</value></prop></item>`) [ASSUMED: Format aus Praxis, im CI durch Auslesen bestätigen]. Profil: Vorlage aus dem Paket nach `/tmp/lo-<job>/user/registrymodifications.xcu` kopieren, dann `-env:UserInstallation=file:///tmp/lo-<job>`. Beweis, dass LibreOffice die Datei liest: im CI ein ODT mit Makro, das beim Öffnen eine Datei schreiben würde (`OnLoad`), einmal ohne und einmal mit Profil in einer Wegwerfumgebung; oder `soffice --convert-to xcu`-freie Variante: nach dem Lauf prüfen, dass LibreOffice die Datei nicht überschrieben/verworfen hat und die Werte noch stehen.

### Anti-Patterns to Avoid
- **Nur `env={}` als Geheimnisschutz:** deckt `/proc/<pid>/environ`, `/frpc.toml`, `/certs/frp/client.key` nicht ab (Pitfall 1).
- **`RLIMIT_NPROC`:** zählt Prozesse und Fäden der realen uid in der Benutzer-Namensraum-Instanz; ohne userns-remap teilen sich alle Container mit uid 10001 (Findling, AV, PII nutzen alle 10001) dieselbe Zählung auf dem Host [CITED: man 2 setrlimit, RLIMIT_NPROC "for the real user ID"]. Nicht setzen; Gabelbombe als AR mit Gruppen-Kill und Zeitdeckel.
- **`waitpid(-1)` im Server:** stiehlt asyncio Kindstatus.
- **pypdf als Vorprüfer:** reiner Python-Parser auf fremden Bytes im kritischen Pfad; nur in Phase 5 als Prüfer.
- **DOCX-Seitenzahl aus `docProps/app.xml`:** vom Angreifer gesetzt. Seitenzahl nur aus dem LibreOffice-PDF.
- **Signatur in PHP parsen:** PHP würde fremdes PDF im Webserver-Prozess lesen. Erkennung im Container-Kind.
- **Server-seitige Verschlüsselung (SSE) mit E2E verwechseln:** `FileInfo::isEncrypted()` ist bei SSE an Dateien gesetzt, Nextcloud entschlüsselt transparent. Nur ein ORDNER mit dem Flag ist E2E (Pitfall 5).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ZIP-Grenzen | neue Prüflogik | Findling `extract/archive.py` Stufe 1+2 (gemessen, auditiert: Zentralverzeichnis zählen vor `ZipFile`, Overlap, Traversal, Rate) | `ZipFile()` baut je Header ein `ZipInfo`, bevor eigener Code zählen kann (Findling-Befund) |
| seccomp-BPF | rohes BPF-Programm | libseccomp über ctypes | Architektur-Nummern, Arch-Prüfung, x32-Falle |
| PDF-Struktur | eigener PDF-Tokenizer | pikepdf (qpdf) | xref-Rekonstruktion, Schleifen im Seitenbaum |
| XML-Sicherheit | Regex auf `<!DOCTYPE` allein | lxml-Parser mit festen Optionen + `docinfo`-Prüfung | UTF-16-Teile verstecken Byte-Muster |
| Reaper | eigenes init | `PR_SET_CHILD_SUBREAPER` + `waitpid(-pgid)` | kein tini in HaRP-Containern verfügbar |

**Key insight:** Die gefährlichen Teile (Kernel-Filter, PDF-Struktur, ZIP-Zentralverzeichnis) sind fertig gelöst; selbst geschrieben werden nur dünne ctypes-Hüllen und die Regeln, welche Teile entfernt werden.

## Grenzwerte (Vorschlag für D-02-07, Owner bestätigt)

| Konstante | Wert | Begründung | Quelle |
|-----------|------|------------|--------|
| `MAX_SOURCE_BYTES` | 256 MiB (bleibt) | 300 Seiten Scan mit 300 dpi liegen meist unter 150 MB | Phase 1, [ASSUMED] Scangröße |
| `MAX_PAGES` | 300 | Owner, ein Deckel für alle Wege | D-02-08 |
| `MAX_PDF_OBJECTS` | 500 000 | 300 Seiten Text-PDF mit Schriften liegt bei wenigen Zehntausend | [ASSUMED], am Zoo (Phase 4) gegenprüfen, Test auf Grenze+1 |
| `MAX_PAGE_SIDE_PT` | 14 400 (200 Zoll, mit UserUnit) | PDF-Implementierungsgrenze laut ISO 32000 Anhang C | [ASSUMED] |
| `MAX_IMAGE_PIXELS` | 100 000 000 je Bild | A3 mit 600 dpi = 70 MP | Rechnung |
| `MAX_RENDER_PIXELS` | 50 000 000 je Seite, dpi wird abgesenkt | Speicher Pixmap RGB 150 MB | Rechnung |
| `ZIP_MAX_ENTRIES` | 10 000 | Findling, gemessen | Findling config.py |
| `ZIP_MAX_CENTRAL_DIRECTORY_BYTES` | 8 MiB | Findling | Findling |
| `ZIP_MAX_MEMBER_BYTES` | 64 MiB deklariert | Findling Audit M4 (815-kB-ODT mit 800-MB-content.xml) | Findling |
| `ZIP_MAX_TOTAL_BYTES` | 256 MiB deklariert | Findling, halbe Adressraumgrenze | Findling |
| `ZIP_MAX_RATIO` / `ZIP_MALICIOUS_RATIO` / ab Größe | 100 / 1000 / 1 MiB | Findling | Findling |
| `ZIP_MAX_NAME_BYTES` | 255 | übliche Dateisystemgrenze | [ASSUMED] |
| `ZIP_MAX_DEPTH` (verschachtelt) | 0 (keine ZIP in DOCX/ODT erlaubt zu öffnen; eingebettete Pakete werden nicht geöffnet) | Phase 2 braucht keine | Entwurf |
| Zeit precheck / sanitize / soffice / render | 60 / 60 / 120 / 60 s | Phase 1 Werte | Phase 1 |
| `RLIMIT_AS` precheck/sanitize/render | 1 GiB | Findling 512 MB für Extraktion, MuPDF-Render größer | messen (VmPeak in CI) |
| `RLIMIT_AS` soffice | 2 GiB, erst nach Messung | CLAUDE.md "nach Messung" | messen |
| `RLIMIT_FSIZE` | precheck 1 MiB, sanitize = Quelle + 10 %, soffice/render 512 MiB | Ausgaben begrenzt; SIGXFSZ = `too_large` | Entwurf |
| `RLIMIT_NOFILE` | 1024 (soffice), 256 sonst | Schriften | messen |
| `RLIMIT_CPU` | Zeitdeckel + 5 s | zweite Linie hinter der Wanduhr | Entwurf |
| `RLIMIT_CORE` | 0 | kein Kernabbild mit Dokumentinhalt | Pflicht |

## Erkennung "verschlüsselt, E2E, defekt, signiert": wo und wie

| Fall | Ort | Verfahren | Grund-Wort (Entwurf) |
|------|-----|-----------|-----------|
| E2E-Datei | PHP `start()` | Elternordner bis zum Benutzerordner durchgehen; ein `Folder` mit `getFileInfo()->isEncrypted()` = E2E. Die E2EE-App selbst prüft genauso: Ordner mit Flag sind immer E2E, Dateien mit Flag nicht unbedingt (SSE) [CITED: Spiegel von `end_to_end_encryption/lib/E2EEnabledPathCache.php`, MEDIUM] | `e2e_encrypted` |
| Passwort-PDF | Kind precheck | `pikepdf.PasswordError` beim Öffnen ohne Passwort [ASSUMED API] | `encrypted_pdf` (gibt es) |
| PDF nur mit Besitzerpasswort (Rechte-Sperre) | Kind precheck | öffnet ohne Passwort, `is_encrypted` wahr | Open Question 2 |
| Passwort-DOCX | Kind precheck | CFB-Magic + Strom `EncryptedPackage` | `encrypted_document` |
| Passwort-ODT | Kind precheck | ZIP mit `META-INF/manifest.xml`, Element `manifest:encryption-data` | `encrypted_document` |
| Defekt | Kind precheck/render | ZIP ohne gültigen End-Record, PDF, das pikepdf nicht öffnet, render/soffice-Fehler | `damaged` |
| Falsch benannt | Kind precheck | Magic ≠ `expected` aus Claim | `wrong_type` |
| Zu groß | precheck (PDF), nach soffice (DOCX/ODT) | Seiten > 300 | `too_many_pages` (gibt es) |
| Grenzen überschritten | precheck | Objekte, Pixel, ZIP-Werte, SIGXFSZ, RLIMIT_AS | `too_large` |
| Bombe/Traversal/Doppelname/DOCTYPE | precheck | Findling-Signaturen + Pitfall 4 | `unsafe_content` |
| Signiert | precheck | `/AcroForm/SigFlags` Bit 1 oder Feld `/FT /Sig` mit `/V` (`/ByteRange`) ; zusätzlich `/Perms` (DocMDP) | kein Fehler: Status `confirm` |

Reason-Spalte hat 32 Zeichen, Status 16 Zeichen (Phase-1-Schema): `e2e_encrypted`, `encrypted_document`, `wrong_type`, `damaged`, `too_large`, `unsafe_content`, Status `confirm` passen. Beide Listen (PHP `Reason`/`Status` Enum und `model.py`) wachsen im Gleichschritt; `test_php_schema.py`/Lockstep-Tests erweitern. JobEvent-Aktionen neu: `signature_notice`, `signature_confirmed`, `macros_removed`, `external_links_removed` (Wörter, kein Inhalt).

## Runtime State Inventory

Nicht zutreffend (keine Umbenennung/Migration). Einzige Laufzeit-Änderung: neue Wörter in den geschlossenen Listen Reason/Status; bestehende Zeilen in `pii_jobs` bleiben gültig, keine Datenmigration. Neue Migration nur, falls der Planer ein Feld `signature_confirmed_at` statt eines JobEvent wählt.

## Common Pitfalls

### Pitfall 1: Geheimnis über /proc und Dateien statt über die Umgebung
**What goes wrong:** Kind liest `/proc/1/environ` (Server ist PID 1), `/proc/<frpc>/environ`, `/frpc.toml` (`metadatas.token = HP_SHARED_KEY`), `/certs/frp/client.key`, `state.db`, fremde `work/<job>`-Ordner. Ausleitung braucht kein Netz: die gerenderte Seite geht an den Sachbearbeiter, die geschwärzte Kopie später an die Öffentlichkeit (IFG).
**Why:** Gleiche uid für Server und Kind; `start.sh` (unverändert aus HaRP) schreibt `/frpc.toml` als 10001 und startet `frpc` mit voller Umgebung; `/proc/<pid>/environ` braucht nur PTRACE_MODE_READ, das bei gleicher uid und dumpbarem Ziel erfüllt ist.
**How to avoid:** (a) Server: `prctl(PR_SET_DUMPABLE, 0)` als erste Handlung in `main.py`, (b) Dockerfile: `frpc` mit `install -m 0711` (Ausführen eines nicht lesbaren Programms macht den Prozess nicht dumpbar) [ASSUMED: Kernel `would_dump()` in fs/exec.c; in CI messen], (c) Landlock im Jail: Lesen nur `/usr`, `/lib*`, `/etc`, `/app/.venv`, `/app` (Code), `/proc/self` nicht nötig für Python; Schreiben nur Auftragsordner und `/tmp/lo-<job>`. Landlock sperrt zusätzlich `ptrace`-artige Zugriffe auf Prozesse außerhalb der eigenen Domäne; die Kernel-Doku nennt das als den Weg, über den `/proc/<pid>/...`-Zugriffe indirekt begrenzt werden [CITED: docs.kernel.org/userspace-api/landlock.html].
**Warning signs:** Container-Test liest im Jail `/proc/1/environ`, `/frpc.toml`, `/certs/frp/client.key`, `<storage>/state.db` und erwartet je `PermissionError`; schlägt einer durch, gehört er als AR zum Owner.

### Pitfall 2: Zombies durch Python als PID 1
**What goes wrong:** `oosplash` stirbt, `soffice.bin` wird zum Waisen des Servers und bleibt nach `killpg` als Zombie stehen.
**How to avoid:** Pattern 2. HaRP setzt kein `Init` [VERIFIED: nextcloud/HaRP `haproxy_agent.py` Zeilen 1582 bis 1630, `HostConfig` nur NetworkMode, Mounts, RestartPolicy, optional Devices/Memory/NanoCPUs].

### Pitfall 3: seccomp/Landlock fehlt auf manchen Hosts
**What goes wrong:** Podman, gVisor, alte Kernel (< 5.13 ohne Landlock, Landlock nicht in `lsm=`), Docker mit eigenem Profil.
**How to avoid:** Fähigkeitsprobe beim Start (ein Jail-Lauf mit `/bin/true` je Schicht), Ergebnis als feste Wörter in `/status` und im Admin-Bereich ("Dateisystem-Sperre: aktiv/nicht verfügbar"), je fehlende Schicht ein AR. Ob ohne seccomp DOCX/ODT überhaupt noch an LibreOffice gehen, ist Open Question 3.

### Pitfall 4: Doppelnamen, die nicht byte-gleich sind
**What goes wrong:** OPC-Teilnamen sind ohne Beachtung von Groß/Klein gleich [CITED: ECMA-376 Teil 2, Part names "case-insensitive ASCII"; ASSUMED Fundstelle]; `word/document.xml` und `Word/Document.xml` sind für Word dasselbe Teil, für `zipfile` zwei Einträge. Dazu `./word/...`, `word//document.xml`, Backslash, NFC/NFD-Varianten, Prozent-Kodierung. Ein Parser liest den ersten, LibreOffice den anderen: die Vorschau zeigt etwas anderes, als lxml später schwärzt (Leck).
**How to avoid:** Namen normalisieren (Backslash zu `/`, `.`-Segmente, doppelte Slashes, Unicode NFC, `casefold()`) und auf Gleichheit prüfen; jede Kollision = `unsafe_content`. Außerdem: Daten vor dem ersten Local Header (`ZipFile` toleriert Vorspann) ablehnen, Lokal- gegen Zentralname vergleicht CPython selbst (`BadZipFile`), Overlap (CVE-2024-0450) meldet CPython.

### Pitfall 5: SSE-verschlüsselte Dateien als E2E abgelehnt
**What goes wrong:** Auf Instanzen mit Server-Side-Encryption tragen alle Dateien das Flag; eine Dateiprüfung `isEncrypted()` an der Datei lehnt alles ab.
**How to avoid:** Nur Ordner prüfen (Erkennungstabelle). PHPUnit mit Mock-Knoten für beide Fälle; im deploy-harp-Lauf optional einen Ordner per SQL auf `encrypted=1` setzen [ASSUMED Spaltenname `encrypted` in `oc_filecache`].

### Pitfall 6: tldextract lädt die Public Suffix List
**What goes wrong:** Presidios `EmailRecognizer.validate_result` ruft `tldextract.extract()`, also den Modul-Standard `TLD_EXTRACTOR = TLDExtract()`, der beim ersten Aufruf `publicsuffix.org` und GitHub abfragt und in den Cache schreibt [VERIFIED: Spike-venv `tldextract/tldextract.py` 5.4.0 Zeile 645, `suffix_list.py` mit `requests.Session`; `email_recognizer.py` Zeile 52].
**How to avoid:** Vor jedem Presidio-Import `tldextract.tldextract.TLD_EXTRACTOR = TLDExtract(suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True)` setzen (Modulattribut wird beim Aufruf nachgeschlagen) UND `ENV TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS=""` (leere Zeichenkette ergibt in 5.4.0 eine leere URL-Liste, Zeile 628 bis 642). Test prüft `TLD_EXTRACTOR.suffix_list_urls == ()`.

### Pitfall 7: GLiNER2 und transformers
**What goes wrong:** `import gliner2` importiert `api_client` (und damit `requests`) immer mit [VERIFIED: Spike-venv `gliner2/__init__.py` Zeile 10]; ein Importverbot des Moduls ist also unmöglich, verboten werden kann nur die Nutzung von `GLiNER2API`/`API`. `AutoConfig/AutoModel/AutoTokenizer.from_pretrained(..., trust_remote_code=True)` laufen mit einer Repo-ID ins Netz und könnten mit `auto_map` in `config.json` Code laden [VERIFIED: `gliner2/models/base.py` 576 bis 630].
**How to avoid:** Laden nur aus absolutem lokalem Ordner, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`; Test: `config.json` und `encoder_config/config.json` ohne `auto_map`; AST-Test, dass kein Quellmodul `GLiNER2API`, `API` aus gliner2, `hf_hub_download`, `snapshot_download` nennt; Erkenner-Worker läuft im Jail mit seccomp-Netzsperre (dann scheitert jeder vergessene Netzaufruf sofort statt still).

### Pitfall 8: `RLIMIT_AS` und glibc-Arenen / OpenMP
**What goes wrong:** Fäden reservieren je 64 MiB Arena; `RLIMIT_AS` zählt Reservierung. Findling-Messung: HEIC 427 bis 444 MiB ohne, 358 mit einer Arena.
**How to avoid:** `OMP_THREAD_LIMIT=1` (schon in `SAFE_ENV`), im Python-Kind `mallopt(M_ARENA_MAX=-8, 1)` wie Findling `sandbox.py`; Werte per VmPeak in CI messen.

### Pitfall 9: LibreOffice hängt an Netz- oder Dialogwartezeiten
**What goes wrong:** Headless-Konvertierung wartet bei externen Links (Mailingliste 2018) [CITED: listarchives.libreoffice.org/global/users/2018/msg00061.html].
**How to avoid:** Bereiniger zuerst; seccomp liefert EACCES sofort statt Timeout; Wanduhr-Deckel 120 s mit Gruppen-Kill.

## Code Examples

### Reaper nach jedem Kind
```python
# Source: man 2 waitpid (pid < -1: any child whose process group ID equals |pid|)
import os, signal
def reap_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    while True:
        try:
            pid, _ = os.waitpid(-pgid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return  # Rest stirbt noch; nächster Durchlauf sammelt ihn ein
```

### Audit-Hook als Netz-Tripwire im Python-Kind (RES-02, auch ohne Docker testbar)
```python
# Source: docs.python.org/3/library/audit_events.html (socket.connect, socket.getaddrinfo, socket.gethostbyname)
import sys
_NET = {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto", "urllib.Request"}
def _hook(event: str, _args: tuple) -> None:
    if event in _NET:
        raise PermissionError("network access is not allowed in this child")
sys.addaudithook(_hook)
```
Erfasst nur Python-Ebene (requests, urllib3, huggingface_hub), nicht C-Code (libcurl in LibreOffice); dafür ist seccomp und der Container-Lauf mit `--network none` da.

### tldextract offline
```python
# Source: Spike-venv tldextract 5.4.0, tldextract.py Zeilen 329 bis 411 und 645
import tldextract.tldextract as _tx
_tx.TLD_EXTRACTOR = _tx.TLDExtract(suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True)
```

## Netzwerkbeweis in CI (Erfolgskriterien 2 und 4)

1. **Container-Teststufe:** Dockerfile bekommt eine Stufe `test` (FROM runtime, plus Dev-Gruppe und `tests/`); docker.yml baut sie für amd64 und arm64 und ruft `docker run --rm --network none ... pytest -m container`. So laufen Jail, Landlock-Probe, LibreOffice und der Korpus im echten Kernel und im echten Image.
2. **Kanarienserver statt Mitschnitt im Container:** Der Test startet im selben Container einen HTTP-Server auf `127.0.0.1:<port>` (Loopback existiert auch bei `--network none`). Testdokumente verlinken Bild, Vorlage und `INCLUDEPICTURE` auf genau diese Adresse. Erwartung: null Verbindungen. Drei Schichtläufe: (a) volle Kette, (b) nur LibreOffice-Profil, unbereinigtes Dokument, seccomp aus: belegt die Schlüssel aus Pattern 5, (c) nur seccomp, unbereinigt, Standardprofil: belegt die Netzsperre.
3. **Host-Mitschnitt (Owner-Wunsch "Netzwerkmitschnitt"):** ein Lauf im Standard-Bridge-Netz mit `--dns 192.0.2.1`; auf dem Runner `sudo tcpdump -i docker0 -w lo.pcap` während der Konvertierung; Erwartung: kein Paket aus der Container-Adresse außer ARP. DNS-Versuche wären als UDP/53 zu 192.0.2.1 sichtbar.
4. **RES-02:** Modell-Dateien werden auf dem Runner (mit Netz) geladen und per sha256 geprüft, mit `actions/cache` über den Hash gecacht, dann schreibgeschützt in einen `--network none`-Container gehängt, der Presidio mit SpacyNlpEngine (absoluter Pfad), den E-Mail-Erkenner und GLiNER2 aus dem lokalen Ordner auf einem Satz mit E-Mail-Adresse laufen lässt, mit Audit-Hook aktiv.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| bubblewrap/nsjail für Konverter | seccomp + Landlock ohne Privilegien | Landlock seit 5.13, Netz ab ABI 4, Scope ab ABI 6, Pfad-Unix-Sockets ab ABI 9 | funktioniert in Docker ohne Capabilities |
| LibreOffice-Einstellungen gegen Nachladen | Bezüge vor LibreOffice entfernen (Gotenberg 8.34.0) | 2025/2026 | Einstellungen nur zweite Schicht |
| lxml Standard `resolve_entities=True` | ab lxml 5 Standard `'internal'`; wir setzen `False` explizit | lxml 5.0 [ASSUMED] | explizit setzen bleibt Pflicht |

**Deprecated/outdated:**
- CVE-2024-12426 (`vnd.sun.star.expand` in Dokument-URLs liest Umgebung und INI-Werte und schickt sie per URL hinaus), behoben in 24.8.4, also in 25.2 nicht mehr offen [CITED: libreoffice.org/about-us/security/advisories/CVE-2024-12426]. Zeigt die Klasse: Dokument-URLs sind ein Ausleitungsweg, deshalb leere Umgebung + Netzsperre + Bereiniger.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Ausführen eines nicht lesbaren Programms (frpc 0711) macht den Prozess nicht dumpbar | Pitfall 1 | `frpc`-Umgebung bleibt lesbar ohne Landlock; dann AR |
| A2 | Landlock ist auf typischen Hosts aktiv (Ubuntu 22.04+, Debian 12/13) | Pitfall 3 | Dateischutz fehlt; AR |
| A3 | `registrymodifications.xcu`-Format mit `oor:op="fuse"` wird von 25.2 im vorbefüllten Profil gelesen | Pattern 5 | Schlüssel wirkungslos; Schichtlauf (b) zeigt es |
| A4 | pikepdf-API (`PasswordError`, `is_encrypted`, Objektzählung) wie beschrieben | Erkennungstabelle | kleine Codeänderung |
| A5 | Grenzwerte Objekte 500 000, Seitenmaß 14 400 pt, Name 255 | Grenzwerte | Fehlablehnung echter Dokumente; am Zoo prüfen |
| A6 | E2E-Ordner tragen in `oc_filecache` das Flag `encrypted` | Pitfall 5 | E2E-Datei läuft bis zum Parser (scheitert dort als `damaged`) |
| A7 | OPC-Teilnamen ohne Groß/Klein (ECMA-376 Teil 2) | Pitfall 4 | Regel strenger als nötig, kein Sicherheitsrisiko |
| A8 | LibreOffice braucht AF_UNIX (OSL-Pipe), nicht AF_INET, für `--convert-to` | Pattern 1 | Konvertierung scheitert unter seccomp; Schichtlauf zeigt es |
| A9 | Debian baut die nogui-Variante ohne Online-Update | Pattern 5 | Schlüssel `AutoCheckEnabled` trotzdem setzen, seccomp sperrt ohnehin |
| A10 | `%PDF-` an Offset 0 verlangen trifft keine echten Behörden-PDFs | Pattern 3 | Fehlablehnung; am Zoo prüfen |

## Open Questions (Owner)

1. **RES-02-Beweis jetzt mit dem echten Erkennungsstapel?**
   - What we know: Erfolgskriterium 4 nennt Presidio, tldextract und GLiNER2; diese Pakete sind noch nicht in `pyproject.toml`, das Image wüchse um torch+cpu und transformers (mehrere hundert MB).
   - Recommendation: Pakete in Phase 2 mit den CLAUDE.md-Pins aufnehmen (sie kommen ohnehin), Modelle nur im CI-Cache, nicht im Image. Alternative: eigener Probe-Container nur in CI.
2. **PDF nur mit Besitzerpasswort (Rechtesperre, öffnet ohne Passwort):** annehmen (Ausgabe verliert die Sperre, Hinweis im Protokoll) oder als `encrypted_pdf` ablehnen? Empfehlung: annehmen mit Protokolleintrag, weil Behörden solche PDFs oft von Dritten bekommen.
3. **Fehlt seccomp zur Laufzeit:** DOCX/ODT trotzdem an LibreOffice geben (AR, Admin-Hinweis) oder nur DOCX/ODT sperren? D-02-05 spricht für "weiter mit AR"; Netzsperre ist aber die stärkste Schicht gegen Ausleitung.
4. **Makro-DOCX:** stillschweigend entfernen (nur Protokoll) oder dem Nutzer an der Karte sagen "Makros wurden entfernt"? Text vor dem Bau zeigen (D-02-03).
5. **Grenzwert-Tabelle** bestätigen (D-02-07 verlangt feste Werte).
6. **Dockerfile `frpc` 0711:** kleine Abweichung vom Gameworld-Muster (start.sh bleibt byteweise unverändert).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker lokal | Container-Messungen | bewusst aus (Owner-Regel) | - | alle Messungen in docker.yml/deploy-harp (amd64 + arm64 Runner) |
| libseccomp2 im Image | seccomp | ja (über apt) | >= 2.4.2 | ohne: AR |
| Landlock im Kernel der Runner | Tests | ubuntu-24.04-Runner, Kernel 6.8+ [ASSUMED] | ABI >= 4 | Test meldet ABI, prüft je nach Stufe |
| sudo/tcpdump auf Runner | Host-Mitschnitt | GitHub-Runner haben sudo; tcpdump vorinstalliert [ASSUMED] | - | `apt-get install tcpdump` im Schritt |
| Spike-venv | Code-Belege | ja | `C:/Users/Student/pii-spike-2026-11-06/.venv` | - |

**Missing dependencies with no fallback:** keine.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.2.0, pytest-asyncio 1.4.1.post1, pytest-cov 7.1.0 |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && uv run pytest -q -x tests/test_<modul>.py` |
| Full suite command | `cd backend && uv run pytest -q -rs --cov=src/pii_redaction_backend` |
| Container suite | `docker run --rm --network none <image>:test pytest -m container` (nur CI) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAFE-01 | Kind-Umgebung ohne Geheimnis; `/proc/1/environ`, `/frpc.toml`, Schlüssel, state.db im Jail nicht lesbar | container | `pytest -m container tests/test_jail_container.py` | ❌ Wave 0 |
| SAFE-01 | rlimits gesetzt (über `/proc/self/limits` im Kind), Zeitlimit tötet Gruppe, keine Zombies | unit (Linux) + container | `pytest tests/test_jail.py tests/test_reaper.py` | ❌ Wave 0 |
| SAFE-01 | Jail-Profile und Argumentbau | unit (alle OS) | `pytest tests/test_jail_profiles.py` | ❌ Wave 0 |
| SAFE-02 | Magic, ZIP-Grenzen, Doppelnamen, XML-DOCTYPE, PDF-Grenzen auf Grenze und Grenze+1 | unit | `pytest tests/test_intake_*.py` | ❌ Wave 0 |
| SAFE-03 | Bereiniger entfernt alle Klassen aus Pattern 4; Gegenprobe | unit | `pytest tests/test_sanitize.py` | ❌ Wave 0 |
| SAFE-03 | DOCX mit externem Bild + Makro: null Verbindungen am Kanarienserver, drei Schichtläufe | container | `pytest -m container tests/test_lo_network.py` | ❌ Wave 0 |
| SAFE-04 | Korpus komplett abgewiesen, Container lebt, Laufzeit unter Deckel | container | `pytest -m container tests/test_corpus.py` | ❌ Wave 0 |
| JOB-05 | Reason/Status-Wörter in PHP und Python gleich; E2E-Ordner abgelehnt; SSE nicht; Bestätigungsfluss mit JobEvent | unit + phpunit + deploy-harp | `pytest tests/test_model.py tests/test_php_schema.py`; `composer test` | teils (erweitern) |
| RES-02 | Audit-Hook-Lauf ohne Netzereignis; tldextract-URLs leer; kein `GLiNER2API` im Code; `--network none`-Lauf | unit + container | `pytest tests/test_offline.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Quick run des berührten Moduls
- **Per wave merge:** volle lokale Suite + ruff/pyright/vulture
- **Phase gate:** volle Suite grün, docker.yml Container-Suite grün auf amd64 und arm64, deploy-harp grün, dann `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py`: Fixture-Fabrik für den Korpus (in `tmp_path` erzeugt, keine Binärdateien), Marker `container` und `linux`
- [ ] `ci/make_corpus.py` (Standardbibliothek, für die Container-Stufe und deploy-harp), Gegenstück zu `ci/make_fixtures.py`
- [ ] Dockerfile-Stufe `test` und docker.yml-Schritt `--network none`
- [ ] `test_workflows.py`/`test_workflow_pins.py` um die neuen Schritte erweitern (Phase-1-Gates)
- [ ] Korpus-Liste: ZIP mit Rate 1000+ (echter Deflate-Strom aus Nullen, zlib in Blöcken), ZIP mit gelogener Größe, Overlap-Bombe (Fifield-Bauart), 10 001 Einträge, Traversal (`../`, `/abs`, `C:`, Backslash, NUL), Doppelnamen exakt und Groß/Klein, Vorspann vor ZIP, Billion Laughs, XXE `file:///etc/passwd` und `http://127.0.0.1:<kanarie>`, Parameter-Entität, DOCTYPE allein, DOCX mit externem Bild/attachedTemplate/INCLUDEPICTURE/altChunk/vbaProject, ODT mit externem `draw:image`, Basic-Ordner und Ereignis, PDF mit 301 Seiten, Riesen-MediaBox, 100 000 x 100 000-Bild, Flate-Bombe im Inhaltsstrom, Seitenbaum-Schleife, Objektzahl Grenze+1, Passwort-PDF (pikepdf `Encryption`), Besitzerpasswort-PDF, Signatur-Attrappe (`/SigFlags 3`, `/FT /Sig`, `/ByteRange`), CFB mit `EncryptedPackage`, ODT mit `manifest:encryption-data`, falsch benannte Dateien je Richtung, abgeschnittene Dateien.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | nein (unverändert Phase 1) | - |
| V3 Session Management | nein | - |
| V4 Access Control | ja (E2E-Prüfung, Bestätigung nur durch Auftraggeber) | `FileAccess`, `forMember` aus Phase 1 |
| V5 Input Validation | ja, Kern der Phase | Magic-Bytes, Findling-ZIP-Stufen, lxml-Fabrik, pikepdf-Grenzen |
| V6 Cryptography | nein (nur Erkennen von Verschlüsselung) | - |
| V12 Files and Resources | ja | Größen-, Raten-, Pfadgrenzen, Bereiniger, keine Ausführung |
| V14 Configuration | ja | LibreOffice-Profil, Jail-Profile, Offline-ENV |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Zip-/XML-/PDF-Bombe | Denial of Service | Deklarationsprüfung vor dem Lesen, rlimits, Wanduhr, Gruppen-Kill |
| XXE / externe Entität | Information Disclosure | `resolve_entities=False`, `no_network=True`, DOCTYPE ablehnen, seccomp |
| Externe Rels / Vorlagen-Injektion / INCLUDEPICTURE | Information Disclosure (SSRF, Leseweg) | Bereiniger, LO-Schlüssel, seccomp |
| Makro-Ausführung | Elevation of Privilege | Bereiniger, `DisableMacrosExecution` |
| Parser-Differenz durch Doppelnamen | Tampering (Leck in Ausgabe) | Namensnormalisierung + Ablehnung |
| Geheimnis über /proc oder Dateien | Information Disclosure | `PR_SET_DUMPABLE=0`, Landlock, frpc 0711 |
| Ausleitung über gerenderte Ausgabe | Information Disclosure | Landlock-Leseliste nur Auftragsordner |
| Zombie-/Prozessflut | Denial of Service | Gruppen-Kill, `waitpid(-pgid)`, Zeitdeckel; `RLIMIT_NPROC` bewusst nicht (AR) |
| Polyglot-Datei (PDF+ZIP) | Spoofing | Magic an Offset 0, Vorspann ablehnen, `expected`-Vergleich |

## Sources

### Primary (HIGH confidence)
- moby/profiles `seccomp/default.json` (main): `unshare`/`setns`/`mount` nur mit CAP_SYS_ADMIN; `clone` Maske 2114060288 (enthält CLONE_NEWUSER); `clone3` ENOSYS; `seccomp`, `prctl`, Landlock-Aufrufe allgemein erlaubt; `ptrace`/`process_vm_*` ab Kernel 4.8; `io_uring_*` nicht erlaubt; `socket` nach Domäne gefiltert
- nextcloud/HaRP `haproxy_agent.py` (main), Container-Erzeugung Zeilen 1582 bis 1630
- LibreOffice core, Zweig libreoffice-25-2: `officecfg/.../Common.xcs` und `Writer.xcs` (lokal geladen und gelesen)
- packages.debian.org trixie: `apt` (Depends libseccomp2), `libreoffice-core-nogui` 4:25.2.3-2+deb13u9 (Depends libcurl4t64, libnss3)
- docs.kernel.org/userspace-api/landlock.html (ABI 1 bis 12, no_new_privs, procfs-Hinweise)
- Spike-venv: tldextract 5.4.0, presidio email_recognizer, gliner2 2.1.0 `__init__.py`, `models/base.py`, `auto.py`
- Repo-Code: `workers/child.py`, `sniff.py`, `soffice.py`, `runner/runner.py`, `model.py`, `config.py`, `docker/entrypoint.sh`, `docker/start.sh`, `Dockerfile`, PHP `Reason`, `Status`, `JobService`, `FileAccess`
- Findling: `extract/archive.py`, `extract/sandbox.py`, `config.py` (Grenzwerte und Messbegründungen)
- PyPI JSON (16.11.2026): pikepdf 10.18.2, lxml 6.1.3, pypdf 7.1.0, pyseccomp 0.1.2 (2021), python-magic 0.4.27 (2022), landlock 1.0.0.dev5 (2025)

### Secondary (MEDIUM confidence)
- docs.docker.com/engine/security/seccomp (Tabelle; widerspricht beim Punkt "unshare --user" dem aktuellen Profil, maßgeblich ist default.json)
- hardentools `libreoffice.go` (Schlüsselpfade, Update-Check-Pfad)
- LibreOffice-Sicherheitshinweis CVE-2024-12426, CodeAn-Labs-Analyse
- Spiegel `end_to_end_encryption/lib/E2EEnabledPathCache.php` (Ordner-Flag = E2E)
- gotenberg.dev Outbound URL Filtering (nur über Suchergebnis)

### Tertiary (LOW confidence)
- Mailingliste LibreOffice 2018 zu Hängern bei externen Links

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, unverändert gegenüber CLAUDE.md, Versionen geprüft
- Architecture (Jail, Reaper, Vorprüfung): MEDIUM, Mechanismen belegt, Verhalten im HaRP-Container ungemessen
- LibreOffice-Schlüssel: HIGH für Existenz und Bedeutung (Schema), MEDIUM für Wirkung im vorbefüllten Profil
- Pitfalls: HIGH für PID-1/Zombie und /proc-Leseweg (aus Code und Startskripten abgeleitet), MEDIUM für frpc-0711-Effekt

**Research date:** 2026-11-16
**Valid until:** 2026-12-16 (Docker-Profil und HaRP können sich ändern; vor Release erneut prüfen)
