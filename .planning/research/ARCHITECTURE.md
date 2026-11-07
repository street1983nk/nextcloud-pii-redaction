# Architecture Research

**Domain:** Nextcloud-App (PHP `pii_redaction` + ExApp `pii_redaction_backend`), die personenbezogene Daten in PDF, DOCX und ODT lokal erkennt, einem Menschen zur Prüfung vorlegt und danach echt schwärzt oder pseudonymisiert, mit unabhängiger Leck-Nachprüfung und Vier-Augen-Freigabe
**Researched:** 2026-11-07
**Confidence:** HIGH für die Nextcloud-Integrationsgrenzen (im Quellbaum `nextcloud/server` stable33 bis stable35, `nextcloud/app_api` stable33 und `nextcloud-libraries/nextcloud-files` main nachgesehen, siehe Sources) und für alles, was die Schwester-App Audio & Video Search schon gebaut und in CI belegt hat. HIGH für Pipeline-Stufen und Prüfer-Zusammensetzung (aus SPIKE-REPORT.md 06.11. gemessen). MEDIUM für die Abbildung DOCX/ODT-Fundstellen auf die Vorschau, für das Streamen großer Ausgaben über `exAppRequest` und für LibreOffice-Härtung. LOW für Scans (Spike hat OCR-Eingänge nicht gemessen). Alle LOW/MEDIUM-Punkte sind unten als VERIFIZIEREN markiert.

---

## Die sieben Befunde, die die Struktur festlegen

**1. Die PHP-App ist die Sicherheits- und Workflow-Grenze, der Container ist Rechenknecht ohne eigenen Zugang für Browser.** AppAPI leitet jede Route einer ExApp, die in `info.xml` mit `access_level` USER steht, über `/apps/app_api/proxy/{appId}/{other}` an jeden angemeldeten Nutzer durch (`ExAppProxyController::passesExAppProxyRouteAccessLevelCheck`, stable33: `USER => $this->userId !== null`). Der Container kann dort nicht prüfen, ob der Nutzer die Originaldatei lesen darf. Folge: Der Container deklariert **keine** USER-Routen (nur `^/status$` ADMIN wie heute im Skeleton), alle Prüfseiten-Anfragen laufen Browser → PHP-Controller (Sitzung, CSRF, Recheck der Originaldatei) → signiertes `PublicFunctions::exAppRequest` → Container. Signierte Anfragen überspringen die Routenprüfung (Skeleton-Kommentar, AVS-Muster). [HIGH]

**2. Der Container liest Dateien nur über das Content-Gateway der PHP-App und schreibt nie selbst in Nutzerdaten.** Lesen: `GET /ocs/v2.php/apps/pii_redaction/files/{fileId}?userId=` mit `ExAppRequired` + `rejectForeignCaller` + `ReaderContext::actAs` + `FileAccess::readableFile` (1:1 aus AVS `GatewayController.php`). Schreiben: Die PHP-App **holt** die geprüfte Ausgabe per `exAppRequest(..., options: ['stream' => true])` ab und legt sie mit `Folder::newFile()` als handelnder Nutzer ab. `stream` wird bis Guzzle durchgereicht (`AppAPIService::requestToExAppInternal` → `Client::get`, `Response::getBody()` gibt bei `stream` die Ressource zurück, stable33 nachgesehen). Kein WebDAV aus dem Container, kein Nutzer-Imitieren per AppAPI-Header: Rechte, serverseitige Verschlüsselung, Gruppenordner-ACL, Sperren und Dateinamens-Kollision behandelt der Nextcloud-Node-Stack. [HIGH für die API, MEDIUM für Streaming großer Dateien durch HaRP, VERIFIZIEREN in Phase 1]

**3. Klartext-PII lebt an genau einem Ort: im Container-Volume, mit Lebensdauer.** Die PHP-Datenbank hält nur Workflow-Fakten ohne Inhalt (Job, Datei-ID, Nutzer, Status, Revision, Hash des Entscheidungsstands, Zeiten, Zähler). Funde, Fundtexte, Suchbegriffe ("alles schwärzen"), Seitenbilder, Kommentare der Prüfer und Zwischendateien liegen in `state.db` (SQLite, `secure_delete=ON`) und `work/<job>/` des Containers und werden bei Veröffentlichung, Abbruch, Ablauf oder Löschung des Originals gelöscht. Begründung: Die Nextcloud-DB wird repliziert, gedumpt, von DB-Admins gelesen und hat keine TTL-Mechanik; ein zweiter Ort für Klartext verdoppelt die Lösch- und Leckfläche. Die Integrität des Vier-Augen-Prinzips wird trotzdem in PHP verankert (Revision + sha256 des kanonischen Entscheidungsstands, siehe Pattern 3). [Entwurfsentscheidung, HIGH in der Begründung]

**4. Für DOCX/ODT gibt es zwei Darstellungen, und nur eine ist die Wahrheit.** Die Schwärzung arbeitet auf dem XML (lxml, Spike 5.3), also auf einem Textstrom mit Quellanker (Teil, Absatz, Lauf, Zeichenversatz), der auch Kopf/Fuß, Fußnoten, Kommentare, verborgenen Text und Metadaten umfasst. Die Prüfseite zeigt ein per LibreOffice gerendertes Vorschau-PDF. Fundstellen werden **auf dem XML-Textstrom erkannt** und für die Anzeige auf das Vorschau-PDF abgebildet (Textsuche je Seite in Lesereihenfolge). Funde ohne sichtbare Stelle (Kommentar, Metadaten, verborgener Text) erscheinen in der Liste als "nicht im Seitenbild sichtbar" und werden durch die Bereinigung ohnehin entfernt. Das Ausgabe-PDF entsteht aus dem **geschwärzten** DOCX/ODT, nie durch zweites Schwärzen des Vorschau-PDF. [MEDIUM, VERIFIZIEREN Phase 2: Trefferquote der Abbildung bei Tabellen, Silbentrennung, Feldern]

**5. Die Prüfseite zeigt serverseitig gerenderte Seitenbilder mit Kästchen, nicht pdf.js.** Ein Koordinatensystem für alles: dieselbe PDF-Datei (Original-PDF, LibreOffice-Vorschau bei DOCX/ODT, OCR-Bild bei Scans), aus der die Positionen stammen, wird mit PyMuPDF als PNG gerendert; der Browser legt Kästchen in PDF-Punkten skaliert darüber. pdf.js würde Schriften anders setzen (Kästchen verrutschen), kann DOCX/ODT nicht, bräuchte die Rohdatei im Browser und ein zweites Text-Layer-Modell. Für Textauswahl und Flächenschwärzung liefert der Container je Seite Wortkästchen als JSON; der Nutzer darf das Original ohnehin lesen. Nach dem Anwenden zeigt dieselbe Ansicht die **Ausgabe**-Seiten, so dass "was du siehst" exakt der Inhalt der Datei ist. [Entwurfsentscheidung, HIGH]

**6. Modelle, LibreOffice, Tesseract und PDF-Bibliotheken laufen in Kindprozessen, nie im FastAPI-Prozess.** Erkennerstapel 3,96 GB, Kaltstart 16,5 s (Spike 4): ein langlebiger Detektor-Host, warm gehalten solange Arbeit ansteht, nach Leerlauf beendet. LibreOffice je Konvertierung als eigener Prozess mit eigenem Profilverzeichnis, Zeitgrenze und Prozessgruppen-Kill. MuPDF ist C-Code auf fremden Eingaben: Extraktion, Rendering und Schwärzung im Dokument-Worker, damit ein Absturz nur den Auftrag trifft. Muster aus AVS "Engine-Host" mit erhöhtem `oom_score_adj`. [HIGH für das Muster, Spike-Werte gemessen]

**7. Der Leck-Prüfer ist ein eigenes Paket mit eigener Bibliothekskette und wird vor der Schwärzung gebaut.** Er importiert nichts aus `redact/`, `detect/`, `docmodel/` und kein PyMuPDF (`fitz`/`pymupdf`), prüft mit pypdf, pdfminer.six, pikepdf, Revisionszählung, python-docx/odfpy/ZIP-roh, LibreOffice-Textexport und OCR über einen **anderen** Renderer (pypdfium2 statt MuPDF), läuft in eigenem Prozess und schließt bei jedem eigenen Fehler (Zeitüberschreitung, Absturz, unbekanntes Format) die Ausgabe. Owner-Regel "Gegenprobe nie mit dem Muster der Umsetzung". Ein Importgrenzen-Test erzwingt das in CI, ein Positivkontroll-Test (Spike-Varianten Overlay, inkrementell, nur Annotation, naive Body-Ersetzung) beweist, dass er Lecks findet. [HIGH für Zusammensetzung aus Spike 5.2; pypdfium2 als unabhängiger Renderer MEDIUM, Version im STACK-Teil festlegen]

---

## Standard Architecture

### System Overview

```
 Browser (Dateien-App, Prüfseite, Benachrichtigungen)
    │  Sitzung + CSRF, nie direkt zum Container
┌───▼──────────────────────────────────────────────────────────────────────────┐
│ Nextcloud-Prozess: PHP-App `pii_redaction`                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌────────────────┐ ┌──────────────────┐ ┌───────────────┐ ┌───────────────┐  │
│ │ Dateiaktion    │ │ ReviewController │ │ ApprovalSvc   │ │ Admin-Seite   │  │
│ │ (JS, @nextcloud│ │ Seite, Seiten-PNG│ │ Vier-Augen,   │ │ Vier-Augen an/│  │
│ │ /files 4)      │ │ Funde, Entscheide│ │ Notifier      │ │ aus, Gruppe,  │  │
│ │ JobController  │ │ (Proxy+Recheck)  │ │ (INotifier)   │ │ TTL, Labels   │  │
│ └──────┬─────────┘ └────────┬─────────┘ └──────┬────────┘ └───────────────┘  │
│        │      ┌─────────────▼──────────────────▼──────┐                      │
│        └─────►│ JobService + Zustandsautomat          │◄── Listener: Node-   │
│               │ (oc_pii_jobs, oc_pii_job_events,      │    Deleted/Written,  │
│               │  oc_pii_protocols; KEIN Klartext)     │    UserDeleted       │
│               └──┬──────────────┬──────────────┬──────┘                      │
│      ┌───────────▼───┐ ┌────────▼────────┐ ┌───▼──────────────┐              │
│      │ QueueController│ │ GatewayController│ │ PublishJob      │              │
│      │ claim/ack/     │ │ nur lesen, als   │ │ (QueuedJob):    │              │
│      │ requeue, Lease │ │ Nutzer, actAs    │ │ Ausgabe holen,  │              │
│      └───────▲───────┘ └────────▲────────┘ │ newFile() als   │              │
│              │                  │          │ Auftraggeber    │              │
│      ┌───────┴──────────────────┴──────────┴─────────┐       │              │
│      │ ExAppService: einziger Draht zum Container    │◄──────┘              │
│      │ (exAppRequest, Timeouts, Feldfilter, Lockstep)│                      │
│      └───────────────────────┬───────────────────────┘                      │
├──────────────────────────────┼───────────────────────────────────────────────┤
│ AppAPI / HaRP (signiert in beide Richtungen)                                  │
├──────────────────────────────┼───────────────────────────────────────────────┤
│ ExApp-Container `pii_redaction_backend` (Python 3.13, FastAPI)                │
│ ┌─────────────────┐  ┌───────▼────────────────────────────┐                  │
│ │ Task-Client     │  │ API (nur signiert): status, pages,  │                  │
│ │ claim/ack,      │  │ findings, decisions, search, submit,│                  │
│ │ Gateway-Download│  │ output, protocol, purge             │                  │
│ └───────┬─────────┘  └───────┬────────────────────────────┘                  │
│ ┌───────▼────────────────────▼──────┐  ┌─────────────────────────────┐       │
│ │ Job-Runner (ein Auftrag zur Zeit, │◄─┤ RAM-Wächter (cgroup), Zu-   │       │
│ │ Stufen mit Cursor, Wiederanlauf)  │  │ lassung je Kindprozess-Art  │       │
│ └──┬─────────┬──────────┬───────┬───┘  └─────────────────────────────┘       │
│ ┌──▼─────┐ ┌─▼────────┐ ┌▼──────┐ ┌▼──────────┐  reine Logik (ohne I/O):    │
│ │Doc-    │ │Detektor- │ │soffice│ │Leck-Prüfer│  merge/, tiers/, cluster/,  │
│ │Worker  │ │Host      │ │Runner │ │(eigenes   │  officials/, pseudonym/,    │
│ │PyMuPDF,│ │Presidio, │ │je Auf-│ │Paket, pypdf│ decisions/ (kanonischer    │
│ │pikepdf,│ │spaCy lg, │ │ruf ein│ │pdfminer,   │  Hash), protocol/           │
│ │lxml,   │ │GLiNER2   │ │Prozess│ │pikepdf,    │                             │
│ │Tesser- │ │~4 GB,    │ │eigenes│ │pypdfium2+  │                             │
│ │act     │ │warm      │ │Profil │ │OCR, LO-Text│                             │
│ └──┬─────┘ └──────────┘ └───────┘ └────────────┘                             │
├────┼──────────────────────────────────────────────────────────────────────────┤
│ Persistentes Volume (APP_PERSISTENT_STORAGE)                                  │
│  state.db (WAL, secure_delete)   work/<job>/ (src, preview.pdf, pages/*.png,  │
│  Funde, Entscheide, Cluster,     out.*, check/)  models/<name>/<sha256>/      │
│  Revisionen, Prüfberichte        TTL-gelöscht    sha256-gepinnt               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Komponente | Seite | Verantwortung (besitzt) | Vorlage |
|---|---|---|---|
| **Dateiaktion (JS)** | PHP/Browser | `registerFileAction` aus `@nextcloud/files` 4.x (Server stable33 bis 35 pinnen `^4.1.1`; `IFileAction` mit `enabled(context)`, `exec(context)`, optional `execBatch`), geladen über `OCA\Files\Event\LoadAdditionalScriptsEvent` (in stable33/34/35 vorhanden). `enabled`: Mimetype PDF/DOCX/ODT, Leserecht, keine Download-Sperre. Ruft `POST /apps/pii_redaction/jobs`, zeigt Toast "Analyse läuft, du wirst benachrichtigt". Nur Komfort, keine Sicherheitsprüfung | neu; Muster `@nextcloud/files` |
| **JobController / JobService** | PHP | Job anlegen nach Rechteprüfung (Pattern 4), Zustandsautomat, Revision/Hash, Ablaufzeit, Ereignisprotokoll `oc_pii_job_events` (wer, was, wann, kein Inhalt) | neu |
| **QueueController** | PHP | Arbeitsvorrat mit Lease: Container holt `analyze`, `apply`, `purge`; ack mit Ergebnis-Zählern; requeue; Zustell-Zähler (3, dann `failed(repeatedly_stuck)`) | AVS/Findling `QueueController`, `QueueMapper` |
| **GatewayController** | PHP | Einziger Lesekanal für Originalbytes, als genannter Nutzer, `fopen('r')` | AVS `GatewayController.php` 1:1 (neue App-ID) |
| **ReviewController** | PHP | Prüfseite (TemplateResponse + Vue-Bundle), Proxy für Seitenbilder, Wortkästchen, Funde, Entscheide, Suche; vor **jeder** Anfrage: Job-Mitgliedschaft + `FileAccess::readableFile` als aktueller Nutzer + Etag-Abgleich | neu, Recheck-Muster AVS `Provider`/`PageController` |
| **ApprovalService + Notifier** | PHP | Vier-Augen: Vorlegen, Freigeben, Zurückweisen; Kandidaten = Mitglieder der Freigabegruppe, die das Original lesen können, ohne Auftraggeber; `OCP\Notification\IManager` + eigener `INotifier` (in stable33 vorhanden, inkl. `IAction`) | neu |
| **PublishJob** | PHP | `QueuedJob`: Ausgabe nur im Zustand `verified` holen (Stream, Größen- und sha256-Abgleich), Etag des Originals erneut prüfen, `getNonExistingName()` + `newFile()` als Auftraggeber in `actAs`, Protokoll ablegen, Container `purge` | neu; `Folder::newFile`, `getNonExistingName`, `isCreatable` in stable33/35 nachgesehen |
| **Lifecycle-Listener** | PHP | `NodeDeletedEvent`/`NodeWrittenEvent` auf Dateien mit offenem Job → Job `stale`/`cancelled` + `purge`; `UserDeletedEvent` → alle Jobs des Nutzers purgen; `CleanupJob` (TimedJob) für TTL | AVS/Findling Listener-Muster |
| **ExAppService** | PHP | Einziger `exAppRequest`-Aufrufer, Timeouts je Aufruf, Feldfilter (Container ist außerhalb der Vertrauensgrenze), Lockstep, 7 Zustände der Gegen-App | AVS `ExAppService.php` |
| **Admin-Seite** | PHP | Vier-Augen an/aus, Freigabegruppe, Aufbewahrung Prüfzustand (TTL), Rechtsgrundlagen-Katalog (vorbelegt IFG Bund, Entscheidungsveröffentlichung), Standardmodus, Dateinamens-Suffixe, Seitenlimit, Status der Gegen-App | AVS `Settings/Admin.php` |
| **Task-Client** | Python | claim/ack gegen QueueController, Download über Gateway nach `work/<job>/src.part` mit sha256 im Strom, Format per Magic-Bytes statt Endung | AVS `companion.py`, Findling `nc/queue.py` |
| **Job-Runner** | Python | Ein Auftrag zur Zeit, Stufen mit Cursor (Pattern 2), `apply` vor `analyze` (Mensch wartet), Fortschritt ehrlich (Seiten fertig/gesamt, Stufe) | neu, Findling `lane.py`-Gedanke |
| **RAM-Wächter** | Python | Zulassung je Kindprozess-Art: Detektor 4,0 GB + 1 GB Reserve, soffice ca. 0,5 GB [Schätzung], Doc-Worker ca. 0,3 GB [Schätzung]; OOM eines Kindes senkt Deckel, Job `failed(out_of_memory)` statt Endlosschleife | Findling `memory_guard.py`, `guard.py`, `hardware.py` |
| **Doc-Worker** | Python | Kindprozess: Extraktion (PyMuPDF `rawdict`, Glyphen korrekt laut Spike 5.2), Seiten-Rendering PNG, Scan-Erkennung je Seite, Tesseract-Aufruf, Schwärzung PDF (apply_redactions, scrub, garbage=4, pikepdf-Nachlauf), DOCX/ODT per lxml | Spike `redaction_spike.py` |
| **Detektor-Host** | Python | Kindprozess mit Presidio 2.2.366 + eigenen Erkennern + spaCy `de_core_news_lg` + GLiNER2-PII; Eingabe Textsegmente mit Versatz, Ausgabe Spannen mit Label, Score, Quelle; schreibt nie in `state.db` | Spike `run_stack.py`, AVS Engine-Host-Protokoll |
| **soffice-Runner** | Python | Je Aufruf ein `soffice --headless --convert-to pdf` mit `-env:UserInstallation=file:///…/lo-<job>-<n>`, Zeitgrenze, Kill der Prozessgruppe, Makros aus, keine Link-Aktualisierung | neu |
| **Reine Logik** | Python | Zusammenführung, Konfidenzstufen, Rollenwortfilter, Namensweitergabe, Amtsträger, Clusterung, Pseudonym-Schema, Entscheidungs-Kanonisierung + Hash, Protokoll-Aufbau; ohne I/O, offline gegen Spike-JSONL testbar | Spike `evaluate.py`, `pseudo.py` |
| **Leck-Prüfer** | Python | Eigenes Paket, eigener Prozess, fail-closed, siehe Pattern 6 | Spike `recheck.py` |
| **Store (`repo.py`)** | Python | Einziger SQL-Ort, ein Schreiber (Hauptprozess), Kinder liefern über Pipe | Findling/AVS `store/repo.py` |
| **Modell-Register** | Python | sha256-Pins, `.part`, fsync, Rename, Admin-Ablage offline | AVS/Findling `weights.py` |

---

## Recommended Project Structure

Umbau des Skeletons auf das AVS-Layout `backend/` + `php/`. Das vorhandene `appinfo/`, `src/pii_redaction/`, `Dockerfile` ziehen nach `backend/` und bekommen die ID `pii_redaction_backend` (Zertifikat #1419 beantragt); die ID `pii_redaction` (Zertifikat #1411) geht an die PHP-App.

```
nextcloud-pii-redaction/
├── backend/                               # ExApp pii_redaction_backend
│   ├── appinfo/info.xml                   # nur ^/status$ ADMIN, keine USER-Routen
│   ├── Dockerfile                         # LibreOffice headless, Tesseract deu/eng/fra, keine Modelle im Image
│   └── src/pii_redaction_backend/
│       ├── main.py, nc.py, config.py, settings.py, logs.py   # bestehend (nc.py einziger nc_py_api-Import)
│       ├── companion.py                   # Handshake/Lockstep wie AVS
│       ├── tasks/client.py, fetch.py      # claim/ack/requeue, Gateway-Download mit sha256
│       ├── runner/runner.py, stages.py    # ein Auftrag zur Zeit, Stufen-Cursor, Wiederanlauf
│       ├── resources/hardware.py, memory.py, guard.py        # aus Findling kopiert
│       ├── workers/
│       │   ├── host.py, protocol.py       # Kindprozess-Einstieg, JSON-Zeilen über Pipe
│       │   ├── doc_worker.py              # PyMuPDF/pikepdf/lxml/Tesseract
│       │   ├── detector_host.py           # Modelle warm halten
│       │   └── soffice.py                 # LibreOffice-Runner
│       ├── docmodel/                      # Seiten, Wörter mit bbox, Textstrom mit Quellanker
│       │   ├── pdf.py, ooxml.py, odf.py, scan.py, mapping.py   # mapping: XML-Funde → Vorschau-Kästchen
│       ├── detect/                        # läuft NUR im Detektor-Host
│       │   ├── recognizers/de.py, en.py, fr.py, checksums.py
│       │   └── ensemble.py
│       ├── logic/                         # rein, ohne I/O
│       │   ├── merge.py, tiers.py, rolefilter.py, propagate.py
│       │   ├── officials.py, cluster.py, pseudonym.py
│       │   ├── decisions.py               # kanonische Form + sha256
│       │   └── protocol.py                # Protokoll-JSON ohne PII
│       ├── redact/                        # läuft NUR im Doc-Worker
│       │   ├── pdf.py, ooxml.py, odf.py, sanitize.py, raster.py
│       ├── leakcheck/                     # UNABHÄNGIG: kein Import aus redact/, detect/, docmodel/, kein pymupdf
│       │   ├── __main__.py                # eigener Prozess
│       │   ├── secrets.py                 # Eingabevertrag: Werte + Positionen
│       │   ├── pdf_text.py, pdf_raw.py, pdf_revisions.py, ocr.py, office.py, lo_text.py
│       │   └── fuzzy.py                   # NFKD, Joker, 1 bis 2 Abweichungen (Spike 5.2)
│       ├── store/repo.py, schema.py       # einziges SQL, secure_delete, TTL-Sweep
│       ├── models/registry.py, download.py
│       └── api/status.py, pages.py, findings.py, decisions.py, output.py, protocol.py
│   └── tests/test_boundary.py             # nc.py-Regel UND leakcheck-Importgrenze
├── php/                                   # PHP-App pii_redaction
│   ├── appinfo/info.xml, routes.php
│   ├── lib/AppInfo/Application.php        # Listener, Notifier, LoadAdditionalScripts
│   ├── lib/Controller/{Job,Review,Approval,Queue,Gateway,Settings,Handshake}Controller.php
│   ├── lib/Service/{JobService,ApprovalService,ExAppService,FileAccess,ReaderContext,PublishService}.php
│   ├── lib/Db/{Job,JobEvent,Protocol}{,Mapper}.php
│   ├── lib/Notification/Notifier.php
│   ├── lib/BackgroundJob/{PublishJob,CleanupJob}.php
│   ├── lib/Listener/{FileLifecycle,UserDeleted,LoadFilesScripts}Listener.php
│   ├── lib/Migration/, lib/Settings/{Admin,Section}.php
│   ├── src/                               # Vue 3 + @nextcloud/vue 9 (Server stable33 bis 35 nutzen vue ^3.5, @nextcloud/vue ^9.14)
│   │   ├── fileaction.ts, review/ReviewApp.vue, review/PageCanvas.vue, review/FindingList.vue
│   ├── templates/review.php, admin.php
│   └── l10n/ (de, en, fr)
├── eval/                                  # Testsatz-Skripte, Leckraten-Gate, sha256-Manifeste, KEINE Korpora
└── .github/workflows/                     # zwei Archive, zwei Signaturen, HaRP NC 33 bis 35, Playwright, E2E-Lecktest
```

### Structure Rationale

- **`leakcheck/` als Geschwister, nicht als Unterpaket von `redact/`:** Die Importgrenze ist mechanisch prüfbar (AST-Test wie AVS `test_boundary.py`). Gemeinsamer Code ist verboten, auch Normalisierung: `leakcheck/fuzzy.py` ist eine eigene Implementierung. Sonst verdeckt ein gemeinsamer Fehler beide Seiten.
- **`detect/` nur im Detektor-Host, `redact/` nur im Doc-Worker:** Der FastAPI-Prozess importiert weder torch noch MuPDF; ein Absturz oder OOM nimmt Status, Prüfseite und Queue nicht mit. Test: Importliste des Hauptprozesses nach Start.
- **`logic/` ohne I/O:** Konfidenzstufen, Weitergabe, Clusterung, Amtsträger und Entscheidungs-Hash laufen im Schnell-Gate gegen gespeicherte Spike-Vorhersagen (`preds/`-Format), ohne Modell.
- **`php/` trägt Rechte, Workflow und Protokoll:** Wer was sehen und freigeben darf, entscheidet ausschließlich PHP mit dem echten Rechtemodell.
- **Vue 3 statt Plain-JS (Abweichung von AVS):** Die Prüfseite hat Liste, Seitenbild, Kästchen, Tastaturbedienung, Massenaktionen und Zustände; AVS kam mit `play.js` aus, hier wäre das nicht wartbar. `@nextcloud/vue` 9 entspricht dem Server-Stand 33 bis 35.

---

## Architectural Patterns

### Pattern 1: Pull-Arbeitsvorrat mit Lease, drei Aufgabenarten

**What:** PHP schreibt Aufgaben in `oc_pii_jobs` (Spalten `task`, `lease_until`, `attempts`); der Container holt per signiertem OCS-claim, wenn der Wächter Kapazität meldet, und quittiert mit Ergebnis-Zählern (nie Inhalt). Arten: `analyze` (Minuten), `apply` (Sekunden bis Minuten, inkl. Prüfer), `purge` (sofort).
**When to use:** Immer. Ein abgestürzter Container staut Arbeit an, statt sie zu verlieren.
**Anpassung:** Lease je Art (analyze: Seitenanzahl × 15 s + Kaltstart, Verlängerung je fertiger Seite; apply: 10 min). Reihenfolge im Container: purge > apply > analyze; innerhalb analyze FIFO mit Höchstzahl offener Jobs je Nutzer (Vorschlag 3), damit ein Stapel eines Nutzers nicht alle anderen blockiert. Benachrichtigung "Analyse fertig" schickt PHP im ack-Handler, weil PHP dort den Übergang ohnehin schreibt.
**Trade-offs:** Zwei Apps im Lockstep; dafür Rückdruck, Absturzfestigkeit und ein Ort für den Zustand.

### Pattern 2: Stufen mit persistiertem Cursor je Job

**What:** Jede Stufe schreibt ihr Ergebnis in `state.db`/`work/<job>/` und setzt den Cursor; ein Neustart setzt an der letzten fertigen Seite fort.

```
ingest → normalize → extract → [ocr je Scan-Seite] → detect je Seite → merge (dokumentweit)
       → review (Mensch) → apply → render_output → leakcheck → verified → (PHP holt ab) → purge
```

**When to use:** `detect` je Seite (8 bis 11 s/Seite), weil 100 Seiten 15 bis 18 min dauern. `merge` erst, wenn alle Seiten fertig sind: Namensweitergabe und Clusterung brauchen das ganze Dokument (Spike 2.1: Weitergabe hebt Personen-Recall 0,96 auf 0,996).
**Trade-offs:** Rohspannen je Seite werden gespeichert (Klartext, TTL wie alles). Die Prüfseite öffnet erst nach `merge`; vorher zeigt sie ehrlichen Fortschritt.

### Pattern 3: Inhalt im Container, Integrität in PHP (Revision + Hash)

**What:** Jeder gespeicherte Entscheid (Annehmen/Ablehnen je Fund, "für alle gleichen", Flächen, Suchregeln, Rechtsgrundlage je Schwärzung, Pseudonym-Änderungen) erhöht im Container die Revision. Container-API verlangt bei Schreibzugriffen die Basis-Revision (409 bei Konflikt, optimistische Sperre bei zwei Prüfern). "Als geprüft markieren" liefert `{revision, sha256(kanonischer Entscheidungsstand)}`; PHP speichert beides im Job. Der Freigeber gibt **diese** Revision frei. `apply` sendet `{jobId, revision, hash}`; der Container verweigert, wenn sein Stand nicht exakt passt.
**When to use:** Immer, auch bei abgeschaltetem Vier-Augen-Prinzip (dann gibt der Prüfer selbst frei).
**Trade-offs:** Container und PHP müssen dieselbe Kanonisierung nicht kennen: PHP vergleicht nur Hashes. Ein Container, der seinen Zustand verliert (Volume weg), kann nicht unbemerkt eine andere Schwärzung anwenden.

```python
def canonical_hash(job) -> str:
    rows = sorted(
        [("f", f.fid, f.decision, f.label_id) for f in job.findings]
        + [("a", a.page, *a.bbox_rounded, a.label_id) for a in job.areas]
        + [("p", c.cid, c.pseudonym) for c in job.clusters],
    )
    return sha256(json.dumps([job.mode, job.output_options, rows], ensure_ascii=False).encode()).hexdigest()
```

### Pattern 4: Rechteprüfung an jeder Kante, nie gespeichert

**What:** "Darf X das?" wird bei Start, jeder Prüfseiten-Anfrage, Freigabe, Abholen und Schreiben neu gestellt, immer in `ReaderContext::actAs($uid, …)` (Gruppenordner-ACL-Falle `in_share`, AVS/Findling #14).

| Aktion | Bedingung (alle) |
|---|---|
| Job starten | `readableFile` als Auftraggeber; keine Download-Sperre (`OCA\Files_Sharing\ViewOnly`-Logik: Speicher `SharedStorage` und `getAttributes()->getAttribute('permissions','download') === false` → ablehnen, stable33/35 nachgesehen); Zielordner `isCreatable()` oder Admin-Ausweichordner; Format per Mimetype + später Magic-Bytes |
| Prüfseite lesen/ändern | Mitglied des Jobs (Auftraggeber, Mit-Prüfer, Freigeber-Kandidat) UND `readableFile` jetzt UND Etag des Originals = Job-Etag (sonst `stale`) |
| Freigeben | Freigabegruppe, ≠ Auftraggeber, ≠ jeder Nutzer mit Entscheid in dieser Revision, `readableFile` jetzt |
| Kopie schreiben | als Auftraggeber: `readableFile` jetzt, Elternordner `isCreatable()`, Etag unverändert |

**Download-Sperre:** Eine geschwärzte Kopie, die dem Empfänger gehört, umgeht eine Freigabe "ohne Download". Deshalb Ablehnung mit klarer Meldung; keine Admin-Ausnahme in v1. [Entwurfsentscheidung]
**Trade-offs:** Mehr Node-Lookups; dafür kann ein entzogenes Recht während einer zweiwöchigen Prüfung nicht weiterwirken.

### Pattern 5: Kindprozesse mit Zulassung und warmem Detektor

**What:** Der Runner fragt den Wächter vor jedem Kindstart. Detektor-Host bleibt warm, solange `analyze`-Arbeit ansteht, und wird nach Leerlauf (Vorschlag 5 min) oder bei Speicherdruck beendet; Speicher geht nur beim Prozessende sicher zurück. Nie zwei Detektoren. soffice nie parallel zum Detektor, wenn Kopf-Raum < Bedarf beider. Doc-Worker darf neben dem Detektor laufen (Seitenbilder für die Prüfseite eines anderen Jobs), wenn Kopf-Raum reicht.
**Isolation LibreOffice:** eigenes Profil je Aufruf (sonst blockiert ein hängendes soffice alle folgenden), `start_new_session=True` + Kill der Gruppe nach Zeitgrenze (Vorschlag 120 s je Dokument), `MacroSecurityLevel` hoch über `registrymodifications.xcu`, Aktualisierung externer Verknüpfungen aus (DOCX mit verlinkten Bildern würde sonst nach außen greifen). [MEDIUM, VERIFIZIEREN Phase 2: welche Schalter LO 7.x/24.x headless wirklich beachtet; Netzwerkmitschnitt beim Konvertieren eines DOCX mit externem Bild]
**Isolation Tesseract:** Aufruf je Seite, `OMP_THREAD_LIMIT=1`, Zeitgrenze.

### Pattern 6: Unabhängiger, fail-closed Leck-Prüfer mit Positions-Prüfung

**What:** Eingabe ist (a) die Ausgabedatei(en), (b) die Geheimnisliste aus dem **freigegebenen Entscheidungsstand** (nicht aus dem Schwärzungsergebnis): je Fund Wert, Normalform, Seite und bbox (PDF/Scan) bzw. Teil/Absatz (DOCX/ODT). Ausgabe: Bericht mit Zählern je Prüfer, Urteil `clean`/`leak`/`error`.

| Prüfer | PDF | DOCX/ODT |
|---|---|---|
| Text, unscharf | pypdf + pdfminer.six, NFKD, Joker, 1 bis 2 Abweichungen | python-docx / odfpy, alle Teile |
| Roh | pikepdf: alle Strings und dekomprimierten Streams, Info, XMP, Annots, AcroForm, EmbeddedFiles, Outlines | ZIP-roh über alle Einträge, auch `customXml/`, Thumbnails |
| Revision | `%%EOF`-Zählung, Rekonstruktion erster Revision | entfällt |
| OCR | Rendering mit **pypdfium2** (nicht MuPDF) + Tesseract | über Ausgabe-PDF |
| Dritter | LibreOffice-Textexport | LibreOffice-Textexport |
| Positionen (für Werte unter 4 Zeichen, Initialen) | keine Glyphe eines Extraktors mit Mittelpunkt in einer geschwärzten bbox; Bildbereich der bbox einfarbig im pypdfium2-Rendering | Absatz enthält Balken/Pseudonym an der Stelle |

Jede Ausgabe wird geprüft: bei DOCX/ODT das geschwärzte Office-Dokument **und** das daraus erzeugte PDF. Urteil `leak` oder `error` → keine Ausgabe, Job `failed(leak_detected|check_error)`, Bericht ohne Klartext (Fund-ID, Prüfer, Seite). Pseudonymisieren: Geheimnisse sind die Originalwerte; die Pseudonyme dürfen vorkommen.
**When to use:** Jede Ausgabe, ohne Abschaltschalter.
**Trade-offs:** Laufzeit (OCR jeder Seite); dafür ist "nachweislich nichts Geschwärztes mehr drin" eine geprüfte Aussage. Falsch-Positive (Name kommt legitim als Pseudonym-Teil vor, z. B. abgelehnter Fund mit gleichem Wert) müssen über die Entscheide auflösbar sein: ein abgelehnter Fund mit identischem Wert macht den Wert zum "sichtbar erlaubt"-Eintrag, und Text-Prüfer zählen dann nur Vorkommen über der erlaubten Anzahl, Positions-Prüfer bleiben scharf. [MEDIUM, Regel in Phase 4 mit Testfällen festlegen]

### Pattern 7: Protokoll ohne Klartext, und ohne umkehrbare Hashes

**What:** Protokoll-JSON (und daraus PDF) mit: Job-ID, sha256 Original und Ausgabe(n), Modus, Prüfer und Freigeber (uid + Anzeigename zum Zeitpunkt), Zeitstempel, Anzahl je Kategorie und Seite, Rechtsgrundlagen je Schwärzung (Label-ID + Text), Prüfer-Urteile je Prüfer, Modell- und Regelversionen (sha256 der Modelle, Version des Erkennerpakets), App-Versionen.
**Achtung:** Keine sha256 einzelner Werte. Ein ungesalzener Hash von "Valerie Schüler" ist per Wörterbuch umkehrbar und wäre damit PII. Wenn Wiedererkennung nötig ist (später), dann HMAC mit einem Schlüssel, der nur in der Instanz liegt, und nur auf Owner-Entscheid.
**Ablage:** JSON in `oc_pii_protocols` (überdauert Purge und Dateilöschung, Audit), zusätzlich Protokoll-PDF neben der Kopie nur, wenn der Admin das einschaltet (Owner-Entscheid; Vorschlag: an, Name `<stamm>_protokoll.pdf`). Der Container baut das Protokoll, PHP prüft Felder gegen eine geschlossene Liste, bevor es speichert.

---

## Data Flow

### Fluss 1: Auftrag starten (Richtung: Browser → PHP → Queue)

```
Nutzer klickt "Schwärzen / Pseudonymisieren" (Dateiaktion, enabled() nur Komfort)
    ↓ POST /apps/pii_redaction/jobs {fileId, mode}           (Sitzung, CSRF)
JobController: actAs(uid): readableFile, keine Download-Sperre, Ziel isCreatable
    ↓ insert oc_pii_jobs(status=queued, task=analyze, etag, initiator, expires_at)
    ↓ Antwort {jobId}; Toast; Nutzer kann weiterarbeiten
```

### Fluss 2: Analyse (Richtung: Container zieht, PHP liefert Bytes, Container meldet Zähler)

```
Task-Client: claim(analyze) ──OCS signiert──► QueueController (Lease)
    ↓ GET Gateway /files/{fileId}?userId=initiator → work/<job>/src.part, sha256 im Strom
normalize: Magic-Bytes; PDF verschlüsselt/defekt → failed(reason); DOCX/ODT → soffice → preview.pdf
extract (Doc-Worker): Seiten, Wörter mit bbox, Textstrom mit Quellanker; Scan-Seiten erkannt
ocr (Doc-Worker + Tesseract je Scan-Seite, Sprache aus Instanz-Sprachen)
detect (Detektor-Host, je Seite, Cursor) → Rohspannen
merge (logic/): Zusammenführung, Rollenwortfilter, Weitergabe, Stufen hoch/mittel/niedrig,
    Amtsträger-Markierung (vorgeschlagen, bleibt geschwärzt), Cluster + Pseudonym-Vorschlag,
    Hinweis "Datum in Personenzeile", Dateiname-Prüfung (Basisname einmalig von PHP)
    ↓ state.db: finding, cluster; Seitenbilder bei Bedarf (lazy)
ack(analyze, {pages, findingsByTier, byCategory}) ──► PHP: status=review, Notification an Auftraggeber
```

### Fluss 3: Prüfen (Richtung: Browser ↔ PHP ↔ Container, Inhalt nur im Container)

```
GET /apps/pii_redaction/review/{jobId}  → Recheck → Template + Vue
Vue: GET …/review/{jobId}/findings      → Recheck → exAppRequest GET /jobs/{id}/findings?uid
     GET …/review/{jobId}/page/{n}.png  → Recheck → exAppRequest GET /jobs/{id}/pages/{n}.png (stream)
     GET …/review/{jobId}/page/{n}/words→ Wortkästchen für Auswahl
     POST …/decisions {baseRev, ops[]}  → Recheck → Container: ops anwenden, rev+1, actor=uid
     POST …/search {term}               → Container sucht im Textstrom, schlägt Funde vor
     POST …/submit                      → Container: {rev, hash} → PHP: status=submitted(rev,hash)
```

Alle Antworten des Containers filtert `ExAppService` feldweise; Seitenbilder werden mit `Content-Type: image/png`, `Cache-Control: private, no-store` ausgeliefert (Browser-Cache wäre ein dritter Klartextort).

### Fluss 4: Vier-Augen-Freigabe

```
submitted(rev, hash)
    ↓ ApprovalService: Kandidaten = Freigabegruppe ∩ readableFile(Original) − Auftraggeber
    ↓ INotification je Kandidat, Aktion "Prüfen" → review/{jobId}?mode=approve
Freigeber öffnet (Recheck), sieht Entscheide read-only + Ausgabe-Vorschau optional
    ├─ "Zurückweisen" (+Kommentar, liegt im Container) → status=review, Notification an Auftraggeber
    └─ "Freigeben"   → PHP prüft: Freigeber ∉ Akteure(rev); hash unverändert (GET /jobs/{id}/revision)
                     → status=approved(approver, at), task=apply
Vier-Augen aus: Auftraggeber "Freigeben" führt direkt zu approved (Protokoll vermerkt "ohne Zweitprüfung")
```

### Fluss 5: Anwenden, Prüfen, Ablegen (Richtung: Container erzeugt, PHP holt und schreibt)

```
claim(apply {rev, hash, labels, options}) → Container prüft hash == eigener Stand
redact (Doc-Worker): PDF apply_redactions + scrub + garbage=4 + pikepdf | DOCX/ODT lxml
render_output: DOCX/ODT → soffice → out.pdf; Option "Höchste Sicherheit": rastern + frische OCR
leakcheck (eigener Prozess) über alle Ausgaben → clean | leak | error
    ├─ leak/error → ack(failed, reason, report ohne Klartext) → Notification "nicht abgelegt"
    └─ clean → state=verified, ack(verified, {sha256, size je Ausgabe}) 
PHP PublishJob: GET /jobs/{id}/output/{kind} (stream, nur verified) → sha256/size prüfen
    → actAs(initiator): Etag Original unverändert? Ziel isCreatable? getNonExistingName("<stamm>_geschwärzt.pdf")
    → newFile() je Ausgabe; Protokoll speichern; status=published(outputFileIds)
    → Notification an Auftraggeber (+ Freigeber) mit Link zur Kopie
    → task=purge → Container löscht Job aus state.db und work/
```

Suffix nach Sprache des Auftraggebers (`_geschwärzt`, `_redacted`, `_caviardé`); Ausgabeformat: Originalformat geschwärzt + immer PDF.

### Fluss 6: Lebenszyklus und Löschen

- **Original gelöscht/verschoben in Papierkorb während Prüfung:** Listener → `cancelled(original_deleted)` + purge.
- **Original geändert (Etag):** Listener markiert `stale`; Prüfseite zeigt "Datei wurde geändert, neu analysieren"; Anwenden gesperrt (PublishJob prüft zusätzlich).
- **Umbenennen/Verschieben im selben Speicher:** `file_id` bleibt, nichts zu tun; Ziel der Kopie ist der Elternordner zum Zeitpunkt des Ablegens.
- **TTL:** `CleanupJob` setzt abgelaufene Jobs auf `expired` + purge; Container hat eigenen TTL-Sweep als zweite Linie (falls PHP-App deaktiviert ist).
- **Nutzer gelöscht:** alle Jobs purgen, Protokolle bleiben (Audit, ohne Klartext).
- **ExApp deinstalliert/Volume weg:** Jobs in `review`/`submitted` werden beim nächsten Status-Abgleich `failed(backend_state_lost)`.

### State Management

**PHP (Nextcloud-DB, kein Klartext):**
```
oc_pii_jobs(id, file_id, initiator_uid, file_etag, orig_sha256, mode, options_json, status, reason,
            task, lease_until, attempts, revision, revision_hash, submitted_by, submitted_at,
            approved_by, approved_at, output_file_ids_json, created_at, updated_at, expires_at)
oc_pii_job_events(id, job_id, uid, action, revision, at)            -- wer hat wann was getan
oc_pii_protocols(job_id PK, json, created_at)                       -- geschlossene Feldliste
```
`status` aus geschlossener Liste: `queued, analyzing, review, submitted, approved, applying, verified, published, failed, stale, cancelled, expired`; `reason` ebenfalls geschlossen (`encrypted_pdf, unsupported_format, too_many_pages, out_of_memory, repeatedly_stuck, leak_detected, check_error, original_changed, original_deleted, target_not_writable, backend_state_lost`). Freitext ist der kürzeste Weg, einen Namen in die DB zu bringen.

**Container (`state.db`, Klartext, TTL):**
```
job(job_id PK, sha256, format, pages, stage, cursor, mode, revision, created_at, expires_at)
page(job_id, n, kind{text|scan|mixed}, w_pt, h_pt)
span_raw(job_id, page, start, end, label, score, source)                -- Rohspannen je Seite
finding(job_id, fid, anchor_json, bboxes_json, text, norm, category, tier, sources, cluster_id,
        official, visible, date_hint)
decision(job_id, fid, state, label_id, actor_uid, rev, at)
area(job_id, aid, page, bbox, label_id, actor_uid, rev)
rule(job_id, rid, term, actor_uid, rev)                                -- "suchen und alles schwärzen"
cluster(job_id, cid, pseudonym, gender, actor_uid, rev)
revision(job_id, rev, hash, submitted)
comment(job_id, cid, uid, text, at)
output(job_id, kind, sha256, size, verdict, report_json)
meta(key PK, value)
```

---

## Scaling Considerations

| Maßstab | Anpassung |
|---|---|
| Einzelne Dokumente (1 bis 20 Seiten, wenige Jobs/Tag) | Ein Container, ein Job zur Zeit; 10 Seiten ca. 80 bis 110 s + Kaltstart 16,5 s (Spike 4); Detektor nach Leerlauf beenden |
| Stapel (100+ Seiten, mehrere Nutzer) | 100 Seiten 15 bis 18 min; FIFO mit Obergrenze je Nutzer, ehrliche Restzeit, Seitenlimit je Job (Admin, Vorschlag 300); Detektor bleibt warm |
| Große Behörde | CPU-Grenze. Zweiter Detektor nur, wenn Wächter 2 × 4 GB + Reserve zulässt; keine Verteilung auf mehrere Container in v1 (ein Schreiber, ein state.db) |

### Scaling Priorities

1. **Erster Engpass: RAM.** 3,96 GB je Detektor; auf 8-GB-Servern mit Nextcloud und DB ist genau einer möglich. Der Wächter entscheidet, nicht eine feste Zahl.
2. **Zweiter Engpass: Plattenplatz in `work/`.** Seitenbilder (lazy, nur angesehene Seiten), Raster-Ausgaben 3,4 bis 6,3-fach größer (Spike 5.1). Purge direkt nach Veröffentlichung, TTL für liegengebliebene Prüfungen.

---

## Anti-Patterns

### Anti-Pattern 1: Prüfseite als ExApp-UI (Top-Menü/Proxy-Route)
**What people do:** Die Prüfseite im Container ausliefern, über `/apps/app_api/proxy/pii_redaction_backend/…` mit `access_level` USER.
**Why it's wrong:** Jeder angemeldete Nutzer erreicht die Route; der Container kann nicht prüfen, ob er das Original lesen darf, und bekommt bei Job-IDs-Raten fremde Funde im Klartext.
**Do this instead:** Prüfseite in der PHP-App, Container nur signiert.

### Anti-Pattern 2: Klartext-Funde in der Nextcloud-DB
**What people do:** Funde und Entscheide in `oc_`-Tabellen, weil PHP die UI baut.
**Why it's wrong:** DB-Dumps, Replikation, DB-Admins, keine TTL; Löschpflicht lässt sich nicht belegen.
**Do this instead:** Klartext nur im Container mit TTL und `secure_delete`; PHP hält Hash und Revision.

### Anti-Pattern 3: Leck-Prüfer, der Code der Schwärzung wiederverwendet
**What people do:** Dieselbe Text-Extraktion (PyMuPDF) oder dieselbe Normalisierung zum Prüfen nutzen.
**Why it's wrong:** Ein Fehler in der gemeinsamen Schicht ist auf beiden Seiten unsichtbar; Spike 5.2 zeigt, dass Extraktoren Glyphen unterschiedlich lesen. Ein Prüfer, der die gleiche Brille trägt, sieht dasselbe nicht.
**Do this instead:** Eigenes Paket, eigene Bibliotheken, Importgrenzen-Test, Positivkontrollen in CI.

### Anti-Pattern 4: Overlay statt Schwärzung, oder inkrementelles Speichern
**What people do:** Balken zeichnen oder `apply_redactions` mit `incremental=True` speichern.
**Why it's wrong:** Spike 5.1: 84/88 Geheimnisse bleiben lesbar.
**Do this instead:** apply + scrub + Neuschreiben (`garbage=4`) + pikepdf-Nachlauf; der Prüfer verlangt genau ein `%%EOF`.

### Anti-Pattern 5: Container schreibt per WebDAV in den Nutzerordner
**What people do:** nc_py_api `files.upload` mit Nutzer-Imitieren.
**Why it's wrong:** Erste Schreibkante des Containers in Nutzerdaten, ExApp-Scope "alle Nutzer", keine PHP-Rechteprüfung zum Schreibzeitpunkt, Etag-Abgleich und Namenskollision fehlen.
**Do this instead:** PHP holt die geprüfte Ausgabe und schreibt mit `newFile()` in `actAs`.

### Anti-Pattern 6: Amtsträger automatisch ausnehmen
**What people do:** Funde mit Amtsträger-Markierung standardmäßig "nicht schwärzen".
**Why it's wrong:** Spike 6: 2/566 Privatpersonen fälschlich als Amtsträger → Leck mit Rechtsfolge.
**Do this instead:** Kategorie anzeigen, Entscheid `pending` bis Mensch; ungeprüft gilt geschwärzt.

### Anti-Pattern 7: Modelle oder LibreOffice im FastAPI-Prozess
**What people do:** spaCy/GLiNER2 global im Webprozess laden, soffice per `subprocess.run` ohne eigene Session.
**Why it's wrong:** OOM nimmt Status und Prüfseite mit; ein hängendes soffice blockiert das gemeinsame Profil; Speicher kommt nach dem Entladen nicht zurück.
**Do this instead:** Pattern 5.

### Anti-Pattern 8: DOCX schwärzen über das Vorschau-PDF
**What people do:** DOCX → PDF, dann PDF schwärzen, DOCX-Ausgabe weglassen oder separat naiv ersetzen.
**Why it's wrong:** Kommentare, Änderungen, verborgener Text und Metadaten sind im PDF unsichtbar und bleiben im Office-Dokument (Spike 5.3 naiv: 19/88 Lecks).
**Do this instead:** Schwärzung auf dem XML, PDF aus dem geschwärzten Dokument rendern, beide prüfen.

---

## Integration Points

### External Services

| Dienst | Muster | Hinweise |
|---|---|---|
| Dateien-App | `@nextcloud/files` 4.x `registerFileAction` über `LoadAdditionalScriptsEvent` | `enabled()` ist Komfort; Server prüft. Batch (`execBatch`) erst nach v1-Einzelweg |
| Notifications | `OCP\Notification\IManager`, eigener `INotifier`, `IAction` | Nur Status-Texte und Dateiname (Nutzer kennt ihn); kein Fundtext in Benachrichtigungen |
| AppAPI/HaRP | `PublicFunctions::exAppRequest` (PHP → Container), `ExAppRequired`-OCS (Container → PHP) | Standard-Timeout 3 s (`AppAPIService::prepareRequestToExApp`), je Aufruf setzen; `stream` für Seitenbilder/Ausgaben |
| groupfolders | `ReaderContext::actAs` | `in_share`-Falle bei +read −share |
| files_sharing | `ViewOnly`-Logik (Attribut `permissions/download`) | Download-Sperre blockiert Start |
| Server-Verschlüsselung | transparent über Node-API | Gateway liefert Klartext an Container; Ausgabe wird beim Schreiben verschlüsselt |
| Hugging Face / spaCy-Releases | nur Modell-Download mit sha256 | einziger ausgehender Verkehr; Admin-Ablage offline |

### Internal Boundaries

| Grenze | Kommunikation | Hinweise |
|---|---|---|
| Browser ↔ PHP | Sitzung, CSRF, JSON + PNG | nie Browser ↔ Container |
| PHP ↔ Container | nur `ExAppService` (raus), `QueueController`/`GatewayController` (rein) | Container bekommt file_id, uid, Basisname einmalig; nie Pfade |
| Hauptprozess ↔ Kindprozesse | JSON-Zeilen über Pipe, Dateien als Pfad in `work/<job>/` | Kinder schreiben nie in `state.db` |
| Schwärzung ↔ Prüfer | nur Dateien + Geheimnisliste aus dem Entscheidungsstand | Importgrenzen-Test |
| logic ↔ detect | Spannenlisten im Spike-Format | Gate auf gespeicherten Vorhersagen |

---

## Build Order (Abhängigkeiten für den Roadmapper)

```
1 Gerüst+Integrationsbeweis
   ├─► 2 Dokumentmodell, Extraktion, Rendering, Kindprozesse
   │      ├─► 4 Echte Schwärzung + Ausgabe-PDF ◄── 3 Leck-Prüfer (parallel zu 2, vor 4 fertig)
   │      └─► 6 Prüfseite ◄── 5 Erkennung (Logik ab Phase 1 offline möglich)
   │                 └─► 7 Workflow: Vier-Augen, Ablage, Protokoll, Lebenszyklus (braucht 4 + 6)
   │                        ├─► 8 Scans/OCR (braucht 2, 4, 5)
   │                        └─► 9 Pseudonymisierung als zweiter Modus (braucht 4, 5, 6)
   └─► 10 EN/FR-Regeln + Eval-Gate (braucht 5) ──► 11 Admin-Zustände, i18n, Release-Gate, arm64, Volltest
```

1. **Zwei-App-Gerüst und Integrationsbeweis.** Repo auf `backend/` + `php/`, IDs tauschen (Owner-Tor: Zertifikat #1419), Lockstep, Handshake, 7 Zustände, CI mit HaRP auf NC 33/34/35. Beweis Ende zu Ende mit Platzhaltern: Dateiaktion erscheint für PDF, Klick legt Job an, Container claimt, lädt über Gateway, rendert Seite 1 als PNG, ack → Benachrichtigung → Prüfseite zeigt das Bild über den PHP-Proxy mit Recheck; PublishJob schreibt eine Dummy-Kopie mit `newFile()`. Klärt Befund 1, 2, 5 und das Streaming. *Risiko zuerst*, alle Plattform-Unbekannten liegen hier.
2. **Dokumentmodell und Kindprozesse.** Doc-Worker, soffice-Runner (Profil, Zeitgrenze, Makros, Links), RAM-Wächter-Grundform, Extraktion PDF (`rawdict`), DOCX/ODT-Textstrom mit Quellanker, Vorschau-PDF, Abbildung XML-Fund → Kästchen (mit synthetischen Funden messen), Seitenbilder lazy, Fuzz mit defekten/verschlüsselten Dateien.
3. **Leck-Prüfer (parallel zu 2, eigener Bearbeiter wenn möglich).** Nur abhängig vom Geheimnislisten-Vertrag. Positivkontrollen aus Spike 5 (Overlay, Annotation, inkrementell, naiv DOCX/ODT) als CI-Fixtures; Prüfer muss alle finden, auf den "proper"-Varianten 0 melden; Positionsprüfung für Initialen. Muss fertig sein, bevor 4 als erledigt gilt.
4. **Echte Schwärzung und Ausgabe.** PDF/DOCX/ODT nach Spike, Sanitize-Liste, Ausgabe-PDF via LibreOffice, "Höchste Sicherheit", Balkenbreite gerundet, Rechtsgrundlagen-Text im Balken; Eingabe noch Gold-Spannen. E2E-Lecktest in CI gegen 3.
5. **Erkennung.** Detektor-Host, Modell-Register mit sha256, eigene DE-Erkenner, Ensemble, `logic/` (Stufen, Rollenwortfilter, Weitergabe, Amtsträger, Cluster, Datumshinweis), Eval-Harness mit Leckrate je Kategorie. `logic/` und Erkenner-Regeln können ab Phase 1 offline gegen die Spike-Daten gebaut werden; die Einbindung braucht 2.
6. **Prüfseite.** Vue-App, Seitenbild + Kästchen, Liste nach Stufe/Kategorie, Annehmen/Ablehnen einzeln und "alle gleichen", Suchen + alles schwärzen, Flächenschwärzung, Datumshinweis, Revisionen mit 409, Tastatur, drei Breiten hell/dunkel. Kann mit Fake-Funden parallel zu 5 beginnen.
7. **Workflow.** Status, Vier-Augen mit Notifications, Freigabe-Integrität (Hash), PublishJob, Protokoll PDF + JSON, Rechtsgrundlagen-Katalog, TTL/Purge, Lifecycle-Listener, Rechte-Paritätstest (geteilt, entzogen, Gruppenordner-ACL, Download-Sperre) im HTTP-Pfad.
8. **Scans.** Scan-Erkennung je Seite, Tesseract deu/eng/fra, OCR-Kästchen, Pixel-Schwärzung, alte Textebene verwerfen, neue OCR nach dem Schwärzen. Eigene Phase, weil im Spike ungemessen.
9. **Pseudonymisierung.** Konsistente Pseudonyme über Varianten, Schema DE/EN/FR, Ersetzung im PDF (Ersatztext im Redact-Bereich) und XML, Cluster-Korrektur in der Prüfseite, Prüfer mit Originalwerten als Geheimnissen.
10. **EN/FR-Regeln auf DE-Niveau** mit Messung und Leckraten-Gate je Sprache.
11. **Admin-Zustände, Dreisprachigkeit, Release-Gate, arm64, Volltest** (Owner-Abnahme per Playwright).

**Begründung:** 1 enthält alle Plattform-Unbekannten und das Zertifikats-Tor. 3 vor bzw. neben 4, damit die Schwärzung gegen einen fertigen, unabhängigen Prüfer entsteht und nicht umgekehrt. 5 ist der größte Block, aber in der Logik unabhängig und deshalb früh parallelisierbar. 7 erst, wenn Anwenden (4) und Prüfen (6) existieren. 8 und 9 erweitern einen funktionierenden Kernweg, statt ihn zu blockieren. 7 vor 8/9 liefert früh den Kernwert "PDF/DOCX/ODT mit Text, Schwärzen, geprüft, abgelegt".

### Forschungsbedarf je Phase

- **Phase 1:** Streaming großer Ausgaben über `exAppRequest` durch HaRP (Größen bis 50 MB), Dateiaktion in NC 33/34/35 sichtbar (gleiche `@nextcloud/files`-Hauptversion bestätigt), Store-Ablauf ID-Tausch.
- **Phase 2:** Abbildung DOCX/ODT-Fund → Vorschau-Kästchen (Tabellen, Silbentrennung, Felder); LibreOffice-Härtung (Makros, externe Links, Netzwerkmitschnitt), Container-Größe mit LibreOffice amd64/arm64.
- **Phase 3:** pypdfium2 als unabhängiger Renderer (Lizenz, Wheels arm64); Regel für erlaubte Vorkommen abgelehnter Werte.
- **Phase 8:** Komplett offen: OCR-Qualität deutscher Behördenscans, Laufzeit, Pixel-Schwärzung über Bild-XObjects, Glyphenpositions-Leck (PoPETs 2023).
- **Phase 9:** Ersatztext im PDF bei längeren Pseudonymen (Schriftgröße, Zeilenumbruch), Initialen-Cluster 73 %.
- **Standardmuster:** Phase 1 Gerüst (AVS), Phase 7 Rechte (AVS/Findling), Phase 11 (AVS-Gates).

---

## Sources

- `nextcloud/app_api` stable33: `lib/PublicFunctions.php` (`exAppRequest`, `getExApp`), `lib/Service/AppAPIService.php` (Timeout-Standard 3 s, `requestToExAppInternal` reicht Optionen an den Client), `lib/Controller/ExAppProxyController.php` (`passesExAppProxyRouteAccessLevelCheck`: USER = jeder angemeldete Nutzer), `appinfo/routes.php` (`/proxy/{appId}/{other}`), gelesen 07.11.2026 [HIGH]
- `nextcloud/server` stable33/34/35: `apps/files/lib/Event/LoadAdditionalScriptsEvent.php`; `lib/public/Notification/{IManager,INotifier,IAction}.php`; `lib/public/Files/Folder.php` (`newFile`, `getNonExistingName`, `getFirstNodeById`); `lib/public/Files/{Node,FileInfo}.php` (`isCreatable`, `getEtag`); `apps/files_sharing/lib/ViewOnly.php` (Download-Attribut); `lib/private/Http/Client/{Client,Response}.php` (`stream`); `package.json` (`@nextcloud/files ^4.1.1`, `@nextcloud/vue ^9.14`, `vue ^3.5.44`) [HIGH]
- `nextcloud-libraries/nextcloud-files` main, `lib/ui/actions/fileAction.ts` (`IFileAction`, `registerFileAction`, Kontext-Signaturen), Release v4.1.1 vom 21.10.2026 [HIGH]
- Audio & Video Search: `.planning/research/ARCHITECTURE.md`, `.planning/ROADMAP.md`, `php/lib/Controller/GatewayController.php`, `php/lib/Service/{ExAppService,FileAccess,ReaderContext}.php` [HIGH, gelesen]
- Spike `C:/Users/Student/pii-spike-2026-11-06/SPIKE-REPORT.md` Abschnitte 2, 4, 5, 6, 8 (Stapel, RAM, Kaltstart, Schwärzungsverfahren, Positivkontrollen, Glyphen-Befund, Amtsträger 2/566) [HIGH, gemessen]
- Projekt: `C:/Users/Student/nextcloud-pii-redaction/.planning/PROJECT.md`, `appinfo/info.xml` (nur `^/status$` ADMIN) [HIGH]
- LibreOffice-Härtungsschalter, pypdfium2-Eignung, DOCX-Abbildung: nicht verifiziert [LOW/MEDIUM, oben markiert]

---
*Architecture research for: Nextcloud PII Redaction (PHP-App + ExApp), lokale Erkennung, echte Schwärzung, Leck-Nachprüfung*
*Researched: 2026-11-07*
