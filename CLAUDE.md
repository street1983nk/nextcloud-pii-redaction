<!-- GSD:project-start source:PROJECT.md -->
## Project

**PII Redaction**

Nextcloud-App aus zwei Teilen (PHP-App `pii_redaction` für Dateiaktion, Prüfseite, Rechte, Freigabe und Protokoll; ExApp `pii_redaction_backend` für Texterkennung, OCR, PII-Erkennung, Schwärzung, Pseudonymisierung und Leck-Nachprüfung), die personenbezogene Daten in PDF-, DOCX- und ODT-Dateien vollständig lokal findet, einem Menschen zur Prüfung vorschlägt und danach echt schwärzt oder konsistent pseudonymisiert. Zielgruppe: Behörden (IFG-Herausgaben, Veröffentlichung von Gerichtsentscheidungen), Kommunen, Schulen, kleine Organisationen und Selfhoster, die Dokumente herausgeben müssen, ohne Inhalte an einen Cloud-Dienst zu geben. Sprachen DE, EN, FR.

**Core Value:** Eine Datei aus Nextcloud wird mit einem Klick lokal auf personenbezogene Daten geprüft; nach menschlicher Prüfung entsteht neben dem Original eine geschwärzte oder pseudonymisierte Kopie, in der nachweislich nichts Geschwärztes mehr steckt (Text, Metadaten, Altversionen, OCR-Ebene). Kein Inhalt verlässt den Server.

### Constraints

- **Datenschutz**: Kein Dokumentinhalt, kein Fund, keine Telemetrie verlässt den Server; Modelle einmal aus öffentlichen Quellen mit festem sha256 oder per Admin-Ablage: Owner-Regel
- **Bestes Ergebnis für User**: Aufwand und Zeit sind kein Grund, eine messbar bessere Lösung wegzulassen; jede Qualitätsentscheidung mit Leckrate/Recall belegen: Owner 04./06./07.11.
- **Tech stack**: Python-ExApp (FastAPI, nc_py_api) aus dem Skeleton; Presidio, spaCy, GLiNER2, PyMuPDF, pikepdf, pypdf, pdfminer.six, lxml, odfpy, Tesseract, LibreOffice headless: Spike
- **Kompatibilität**: Nextcloud 33 bis 35, AppAPI mit HaRP, amd64 + arm64, nur CPU
- **Ressourcen**: RAM-Wächter; Stapel ca. 4 GB je Arbeitsprozess, nie zwei Aufträge parallel auf kleinen Servern
- **Lizenzen**: AGPL-3.0-or-later (passt zu PyMuPDF AGPL); `fr_core_news_lg` LGPL-LR vor Auslieferung prüfen; Testkorpora nicht ins Repo
- **Sprache**: Alle nutzersichtbaren Texte und README DE/EN/FR im Gleichstand, Deutsch zuerst, echte Umlaute, keine Gedankenstriche, keine Emojis
- **Qualitäts-Gates**: ruff-Vollsatz, pyright basic, vulture lokal grün; Commits nur als street1983nk <k.cherif@outlook.de>, ohne "closes #N"
- **Prozess**: Vor jedem Push, Merge oder Kommentar den Owner fragen; UI-Abnahme gemeinsam per Playwright (3 Breiten, hell/dunkel); vor Store-Release großer Volltest DE/EN/FR; Gegenprobe nie mit dem Muster der Umsetzung
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Fünf Befunde, die die Roadmap kennen muss
## Recommended Stack
### Core Technologies (ExApp `pii_redaction_backend`)
| Technology | Version | Purpose | Why Recommended | Konfidenz |
|------------|---------|---------|-----------------|-----------|
| Python | 3.13 (wie Skeleton) | Laufzeit | Alle nativen Abhängigkeiten unten haben cp313- oder abi3-Wheels für x86_64 und aarch64 (einzeln geprüft); Spike lief auf 3.13.13 | HIGH |
| presidio-analyzer | **2.2.366** (27.10.2026, MIT) | Rahmen: Pattern-Erkenner, Kontextwörter, `RecognizerResult`, 13 deutsche Erkenner | Spike-Version, gemessen. Projekt jetzt unter `github.com/data-privacy-stack/presidio`; letzte Releases 2.2.364 (22.07.), 2.2.365 (25.10.), 2.2.366 (27.10.): exakt pinnen, Upgrades nur nach Gate. Telefon-Erkenner nur mit Datums-/Aktenzeichen-Filter, `DE_PLZ` aus (Spike 2.1) | HIGH |
| spaCy | **3.8.18** (26.10.2026, MIT) | NER S (PERSON/LOC) und Tokenisierung | Spike-Version. Zieht `thinc>=8.3.12,<8.4.0` (8.3.14 hat aarch64-Wheels), `preshed<3.1` (mit Presidio-Deckel `<3.0.14` ergibt das 3.0.13) | HIGH |
| `de_core_news_lg` | **3.8.0**, MIT | deutsches NER | gemessen (Personen 0,91 allein, Stapel 0,996). Wheel `github.com/explosion/spacy-models/releases/download/de_core_news_lg-3.8.0/de_core_news_lg-3.8.0-py3-none-any.whl`, 567.843.151 Byte, **sha256 `36fda650e476b54d5e87803635e36dadd1e8e034c4b5962088586d684f4c9fed`** (am 07.11. selbst gestreamt und gehasht) | HIGH |
| `en_core_web_lg` | **3.8.0**, MIT | englisches NER | Wheel 400.658.291 Byte, **sha256 `293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63`** | HIGH |
| `fr_core_news_lg` | **3.8.0**, **LGPL-LR** | französisches NER | Wheel 571.831.376 Byte, **sha256 `da5bf7fc860af64293d88638b4416b3de3a29005b785bfff67d09b06c77345de`**. Lizenz: siehe Abschnitt "Lizenzfrage fr_core_news_lg" (Ergebnis: verträglich, zur Laufzeit laden, nicht ins Image) | HIGH (Hash), MEDIUM (Lizenz) |
| gliner2 | **2.1.0** (09.10.2026, Apache-2.0), **ohne** Extra `[local]` | NER G2 (Personen, Orte) | Spike-Version. Basispaket zieht nur pydantic, requests, tqdm, urllib3; torch/transformers/safetensors werden explizit gepinnt statt über `[local]` (das zöge zusätzlich `peft`, im Code nur für LoRA-Training lazy importiert, geprüft) | HIGH |
| Modell `fastino/gliner2-privacy-filter-PII-multi` | Commit **`1cb4166094dc58fa8d836429f060d6c95f62b495`** (28.09.2026, Apache-2.0, nicht gated) | GLiNER2-PII-Gewichte | Pflichtdateien mit sha256: `model.safetensors` 1.228.421.964 Byte `0280f6f39f6012da50b6640bad438d9b7e763a1b0102094115d1b710c4dd79b6` (HF-LFS), `tokenizer.json` `f6df10ec83bea993035b2dd7c39345a3d4fcf23421c2adb6cb4ffc1e6d1bc4b5` (HF-LFS), `config.json` `164f17362bcf9d114067d3465e7374bfdd79ce6b605acb745de5a49dabb9595c`, `encoder_config/config.json` `f27dd63cc43a248d2566f0b6ad7a115db353676ce0561dcbca45bac766464c1a`, `tokenizer_config.json` `233beed1f1095cccfc7907cde31a8d90a0c6aa4fdfaf6493f8e55fd162e81ae6` (die drei kleinen am 07.11. selbst gehasht). Nicht laden: `README.md`, `SKILL.md`, Banner. Basis-Encoder mDeBERTa-v3-base (MIT) steckt vollständig in `model.safetensors` + `encoder_config/` | HIGH |
| torch | **2.15.0+cpu** aus `https://download.pytorch.org/whl/cpu` | Inferenz GLiNER2 | Siehe Befund 1. Gemessen im Spike (`torch-2.15.0+cpu.dist-info`) | HIGH |
| transformers | **4.57.6** | Encoder/Tokenizer für GLiNER2 | **Spike-Stand, nicht 5.x.** 5.22.2 ist aktuell und das Modell wurde mit 5.8.0 gespeichert; gliner2 2.1.0 hat Kompatibilitätscode für beide. Der Wechsel auf 5.x ändert Tokenizer-Laden und Standard-dtype und ist deshalb ein eigener Schritt mit Gate-Nachmessung (Leckrate und Personen-Recall müssen gleich bleiben) | HIGH (Pin), MEDIUM (Wechselrisiko) |
| huggingface-hub / tokenizers / safetensors | **0.36.2 / 0.22.2 / 0.8.0** | transitiv, Spike-Stand | transformers 4.57.6 verlangt hub `<1.0`. hub nie zum Laden benutzen, nur Importpflicht | HIGH |
| numpy | **2.4.6** | Arrays | Presidio-Deckel `<2.5.0` (Befund 2) | HIGH |
| PyMuPDF | **2.1** (AGPL-3.0) | PDF: Text mit Positionen (`rawdict`), `add_redact_annot`, `apply_redactions(images=PIXELS, graphics=REMOVE_IF_COVERED, text=REMOVE)`, `Document.scrub`, `save(garbage=4, deflate=True, clean=True)`, Seitenbilder für die Prüfseite, eingebaute OCR | Einzige Bibliothek im Feld, die Text, Bildpixel und Vektoren unter einer Fläche entfernt; Spike 0/88. AGPL passt zur App-Lizenz. Wheels abi3 x86_64 + aarch64 | HIGH |
| pikepdf | **10.17.0** (MPL-2.0) | Struktur-Nachlauf (`/AcroForm`, `/Names`, `/Outlines`, `/OpenAction`, `/Metadata`, `/Annots`, `/Thumb`, Info) und Rohobjekt-Prüfer | Spike: nötig gegen leere Hüllen nach PyMuPDF. Kann selbst keinen Text schwärzen | HIGH |
| lxml | **6.1.3** (BSD-3) | DOCX/ODT-Schwärzung direkt auf dem XML im ZIP | Spike 0/88 für DOCX und ODT. Parser fest konfigurieren: `etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)` | HIGH |
| LibreOffice headless | Debian trixie `libreoffice-writer-nogui` **4:25.2.3-2+deb13u8** (trixie-security), nicht gepinnt | DOCX/ODT immer zusätzlich als PDF ausgeben; dritter Prüfer (Textexport); Vorschau-PDF für die Prüfseite bei DOCX/ODT | Owner-Entscheid. `-nogui`-Variante ohne X11/GTK für amd64 und arm64 vorhanden. Debian-Sicherheitsteam pflegt LibreOffice in stable; Backport 26.8.2 nicht nehmen (kein Security-Support-Versprechen) | HIGH (Verfügbarkeit), LOW (Größe) |
| Tesseract | Debian `tesseract-ocr` **5.5.0-1+b1**, `tesseract-ocr-deu`/`-eng`/`-fra` **1:4.1.0-2**, **exakt gepinnt** | Unabhängige OCR für die Leck-Nachprüfung; `tessdata` auch für die in PyMuPDF eingebaute OCR | Version entscheidet das Ergebnis, also Pin wie im Skeleton-Kommentar vorgesehen; ändert sich in stable praktisch nie | HIGH |
### Supporting Libraries
| Library | Version | Purpose | When to Use | Konfidenz |
|---------|---------|---------|-------------|-----------|
| pypdf | **7.0.0** (06.11.2026, BSD-3) | Prüfer A: Seitentext, Info, XMP, Lesezeichen, Annotationen, Anhänge, Formularwerte | jede PDF-Ausgabe. Hinweis: 7.0.0 ist einen Tag alt, Spike lief ebenfalls auf 7.0.0 | HIGH |
| pdfminer.six | **20260107** (MIT) | Prüfer B: Seitentext, Rekonstruktion der ersten Revision | jede PDF-Ausgabe | HIGH |
| pypdfium2 | **5.15.0** (BSD-3/Apache-2.0, bündelt PDFium) | **Neu gegenüber Spike:** Prüfer C mit einer dritten, von MuPDF unabhängigen PDF-Engine; Rendern der Seiten für die Prüf-OCR | Regel "Gegenprobe nie mit dem Muster der Umsetzung": der Spike hat für die OCR-Prüfung mit PyMuPDF gerendert, also mit derselben Engine, die geschwärzt hat. Wheels für x86_64 und aarch64 vorhanden. Wirkung erst messen (Spike-Positivkontrollen wiederholen) | MEDIUM |
| python-docx | **1.2.0** (MIT) | nur Lesen/Prüfen von DOCX (Prüfer), nie Schreiben | Spike | HIGH |
| odfpy | **1.4.1** (Apache-2.0/GPL, nur sdist, reines Python) | nur Lesen/Prüfen von ODT | Spike. Letzter Release 2020, aber nur Prüfer; uv baut die sdist ohne Compiler | HIGH (Funktion), MEDIUM (Pflege) |
| rapidfuzz | **3.14.6** (MIT) | unscharfer Abgleich im Leck-Prüfer (NFKD, Joker für unlesbare Glyphen, 1 bis 2 Abweichungen) | Pflicht laut Spike 5.2 (exakter Abgleich übersah 7/88). Wheels beide Architekturen | HIGH |
| psutil | **7.2.2** (BSD-3, kommt ohnehin mit PyMuPDF 2.1) | RSS-Beobachtung des Worker-Prozesses | zusätzlich zum Findling-RAM-Wächter (cgroup v2) | HIGH |
| phonenumbers, regex, tldextract, pydantic | transitiv über Presidio (Spike: 9.0.43, 2026.9.29, 5.4.0) | Presidio-Abhängigkeiten | in `uv.lock` festhalten; tldextract offline konfigurieren (Befund 4) | HIGH |
| Findling-/AV-Bausteine (kopiert) | Findling 1.6.x | `memory_guard.py` (cgroup `memory.max` minus `anon`, gedeckelt durch `MemAvailable`, `memory.events` für OOM), `hardware.py` (Threads aus `cpu.max`), Downloader mit sha256 + Allowlist, Queue mit Lease | von Anfang an | HIGH |
### Modelle: Ablage und Laden
| Modell | Größe Download / entpackt | Wann laden | Spitzen-RAM (Spike, Windows `peak_wset`) |
|---|---|---|---|
| GLiNER2-PII @ `1cb41660` | 1,23 GB / 1,24 GB | `/init` | 3,00 GB allein |
| `de_core_news_lg` 3.8.0 | 0,57 GB / 0,61 GB | `/init` | 1,39 GB mit Presidio |
| `en_core_web_lg` 3.8.0 | 0,40 GB / 0,43 GB | bei erstem englischen Auftrag oder Admin-Schalter | 1,16 GB |
| `fr_core_news_lg` 3.8.0 | 0,57 GB / 0,61 GB | bei erstem französischen Auftrag oder Admin-Schalter | 1,47 GB |
| tessdata deu/eng/fra | im Image (Debian-Pakete) | immer | klein |
- **Nichts davon ins Image** (AV-Muster). Ablage `$APP_PERSISTENT_STORAGE/models/<name>/<sha256>/`, Download mit fester URL, sha256 gegen eingebauten Wert, `.tmp` + `os.replace`, Admin-Ablage für Air-Gap mit derselben Prüfung. `/init` lädt GLiNER2 + `de_core_news_lg` (ca. 1,8 GB), das passt in die 40-Minuten-Grenze auch bei ca. 1 MB/s.
- **spaCy-Wheels nicht per pip installieren**, sondern als ZIP öffnen, den Ordner `de_core_news_lg/de_core_news_lg-3.8.0/` entpacken und `spacy.load(<absoluter Pfad>)`; Presidio bekommt denselben Pfad als `model_name` (Pfad existiert, also kein Download-Versuch). Zip-Slip-Prüfung beim Entpacken.
- **Host-Allowlist** (am 07.11. an echten Weiterleitungen geprüft): `huggingface.co` leitet `model.safetensors` auf `us.aws.cdn.hf.co` (Xet-Bridge) weiter, `github.com` Release-Assets auf `release-assets.githubusercontent.com`. Die HF-CDN-Region kann je Standort abweichen: Allowlist auf Suffix `.cdn.hf.co` statt exaktem Host, vor Release erneut prüfen. **MEDIUM.**
- **Umgebung im Container:** `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `TLDEXTRACT_CACHE` auf ein schreibbares Verzeichnis, `TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata`, `OMP_NUM_THREADS` aus `cpu.max`.
### Lizenzfrage `fr_core_news_lg` (LGPL-LR): klare Antwort
- §0: "The act of running a program using the Linguistic Resource is not restricted, and output from such a program is covered only if its contents constitute a work based on the Linguistic Resource". Die geschwärzten Dokumente und Funde sind keine Bearbeitung des Treebanks.
- §3: Ein Programm, das die Ressource nur liest ("designed to work with the Linguistic Resource by reading it"), ist "in isolation ... not a derivative work" und fällt nicht unter die Lizenz. Unser AGPL-Code ist so ein Programm.
- §3/§4: Erst wer Programm **und** Ressource als ein Paket verteilt, erzeugt ein abgeleitetes Paket. §4 erlaubt das "under terms of your choice, provided that the terms permit modification of the package for the customer's own use and reverse engineering for debugging such modifications". AGPL-3.0 erlaubt beides, also kein Konflikt. Pflichten dann: deutlicher Hinweis auf die Ressource und ihre Lizenz, Lizenzkopie beilegen, und die "machine-readable legible form" der Ressource beilegen oder per schriftlichem Angebot/gleichwertigem Zugang bereitstellen.
- §2 c) (ganze Bearbeitung unter LGPL-LR) greift nur, wenn wir das Modell selbst verändern, etwa feinjustieren. Ein eigenes französisches Feintuning auf Basis von `fr_core_news_lg` wäre wieder LGPL-LR.
### OCR: direkt, nicht OCRmyPDF
| Aufgabe | Werkzeug | Warum |
|---|---|---|
| Scan erkennen (keine/kaputte Textebene) | PyMuPDF: Textmenge je Seite vs. Bildfläche | gleiche Engine wie die Schwärzung |
| Wörter mit Positionen für die Erkennung | PyMuPDF `page.get_textpage_ocr(language="deu+eng+fra" bzw. passend, dpi=300, full=True)` | Positionen kommen direkt in PDF-Koordinaten, also genau dort, wo `add_redact_annot` die Fläche braucht. MuPDF bringt Tesseract eingebaut mit, braucht nur `tessdata` |
| Alte Textebene verwerfen | `apply_redactions(text=REMOVE)` auf ganzer Seite bzw. Seite neu aus dem gerenderten, geschwärzten Bild aufbauen | Recherche: OCR-Ebenen-Leck |
| Neue Textebene nach dem Schwärzen | PyMuPDF: geschwärzte Seite rendern, `Pixmap.pdfocr_tobytes(language=...)`, Seite ersetzen | eine Bibliothek, keine Zwischenformate; entspricht Modus "Höchste Sicherheit" (Rastern + frische OCR) |
| OCR in der Leck-Nachprüfung | Tesseract-CLI 5.5.0 (Debian) als Unterprozess auf Seiten, die **pypdfium2** gerendert hat | unabhängig von MuPDF (eigene Engine für Rendern und OCR-Binary) |
### LibreOffice im Container
- **Pakete:** `libreoffice-writer-nogui` (zieht `libreoffice-core-nogui`, `libreoffice-common`, Writer-Filter), `--no-install-recommends`, dazu Schriften `fonts-liberation2`, `fonts-dejavu-core`, `fonts-crosextra-carlito`, `fonts-crosextra-caladea` (metrisch kompatibel zu Calibri/Cambria; senkt Schriftersatz, der im Spike die Glyphen-Fehlzuordnung in LibreOffice-PDFs auslöste). Kein Java (`default-jre` nur "suggests"), kein `libreoffice-math`.
- **Größe:** nicht gemessen (kein Docker hier). Schätzung 350 bis 550 MB zusätzlich. **LOW**, im ersten Container-Build messen.
- **arm64:** Paket für arm64 in trixie und trixie-security vorhanden. **HIGH.**
- **Aufruf:** je Auftrag ein eigener Prozess `soffice --headless --norestore --nolockcheck --nodefault --nologo -env:UserInstallation=file:///tmp/lo-<auftrag> --convert-to pdf:writer_pdf_Export --outdir <tmp> <datei>`, eigenes Profilverzeichnis je Auftrag (sonst blockieren sich Instanzen), harte Zeitgrenze, ganze Prozessgruppe beenden, Temp danach löschen. Erst starten, wenn der Erkenner-Worker beendet ist (RAM).
- **Härtung:** Profil vorab mit `registrymodifications.xcu` füllen: Makros aus (`DisableMacrosExecution=true`, `MacroSecurityLevel=3`), Aktualisierung externer Verknüpfungen und Bilder aus, keine Update-Prüfung. Nicht-Root (uid 10001 aus dem Skeleton), keine Capabilities. **MEDIUM**: genaue Konfigurationsschlüssel in der Phase gegen 25.2 prüfen und mit einem DOCX testen, das ein externes Bild verlinkt (darf keinen Netzaufruf erzeugen).
- **Sandbox:** bubblewrap 0.12.0 ist in trixie, braucht aber unprivilegierte User-Namespaces, die das Standard-seccomp-Profil von Docker meist blockiert; im AppAPI-Container nicht verlässlich. Also kein bwrap; Grenzen über `resource.setrlimit` im `preexec_fn` (`RLIMIT_CPU`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE`), Zeitlimit und Container-Isolation. Ein Netz-Abschalten nur für LibreOffice ist ohne Capabilities nicht möglich: Restrisiko dokumentieren. **MEDIUM.**
- **Version:** nicht exakt pinnen (Sicherheitsupdates über Basis-Digest-Rebuilds), aber `soffice --version` in Protokoll und Status schreiben; der Ende-zu-Ende-Lecktest in CI ist die Absicherung gegen Verhaltensänderungen.
### RAM-Wächter und Prozessmodell
- Ein Auftrag zur Zeit. Erkennung in einem **Worker-Unterprozess** (spawn), der Presidio + spaCy-Modell der Dokumentsprache + GLiNER2 lädt, die Seiten abarbeitet und endet; danach Schwärzung (wenig RAM), danach LibreOffice, danach Prüfer. Nie Erkenner und LibreOffice gleichzeitig.
- Start nur bei `headroom >= 4,0 GB + 1 GB Reserve` (Spike 3,96 GB Spitze für den 14-Label-Stapel); Schnellmodus (Presidio + spaCy, 1,4 GB) als ehrlicher Rückfall mit Hinweis, nie stillschweigend. Linux-RSS des Stapels ist **nicht gemessen** (Spike: Windows `peak_wset`), im ersten Container messen und Schwelle danach setzen.
- `torch.set_num_threads` aus `cpu.max` (Findling `hardware.py`), Standard 2; `torch.inference_mode()`; Stücke bis 600 Zeichen, batch 8 wie im Spike.
- Kein `RLIMIT_AS` für den torch-Worker (virtueller Speicher von torch/ORT, AV-Begründung); für LibreOffice ist es vertretbar, nach Messung.
## PHP-App `pii_redaction` (Nextcloud 33 bis 35)
| Baustein | Version / API | Zweck | Konfidenz |
|---|---|---|---|
| PHP | >= 8.2, keine Composer-Laufzeitabhängigkeit, phpunit 11.5.57 dev | wie AV | HIGH |
| Skript-Einhängung | Listener auf `OCA\Files\Event\LoadAdditionalScriptsEvent` in `Application::register`, darin `\OCP\Util::addInitScript('pii_redaction', 'pii_redaction-init')` | Dateiaktion in Dateien laden, nur dort | HIGH (Doku NC 30 bis 32, Forum-Bericht NC 33.0.2) |
| `@nextcloud/files` | **4.1.1** (21.10.2026, AGPL) | `registerFileAction({ id, displayName, iconSvgInline, enabled, exec })` mit `exec({ nodes, view, folder, contents })`; `enabled` nur für PDF/DOCX/ODT-MIME, eine Datei, Leserecht | HIGH für NC 33; MEDIUM für 34/35 (v4 gilt "33 or later", nicht an Instanz geprüft) |
| Build | Vite über **`@nextcloud/vite-config` 2.5.4** (peer `vite ^7.3.6`) | nötig, weil v4 als Modul gebündelt werden muss (Befund 5) | HIGH |
| UI-Bibliothek Prüfseite | **Vue 3 + `@nextcloud/vue` 9.14.1** (peer `@nextcloud/files ^4.1.1`, `@nextcloud/dialogs ^7.4 \|\| ^8`), `@nextcloud/dialogs` 8.0.0, `@nextcloud/axios` 2.6.0, `@nextcloud/router` 3.2.0, `@nextcloud/l10n` 3.4.1, `@nextcloud/initial-state` 3.0.0 | Prüfseite mit Vorschlagsliste, Filter, Dialogen in Nextcloud-Optik (UI-Regel `nextcloud-ui`); wenn ohnehin gebaut wird, ist Vanilla kein Vorteil mehr | MEDIUM |
| Prüfseite | eigene Route `/apps/pii_redaction/review/{jobId}` (TemplateResponse, CSP ohne Inline-Skripte) | Dokumentansicht + Vorschläge | HIGH |
| Seitenbilder | **vom Backend gerenderte PNG** je Seite (PyMuPDF `get_pixmap`, ca. 110 bis 150 dpi), über PHP-Controller nach Rechteprüfung aus dem Container geholt (`exAppRequest`), Funde als Rechtecke in PDF-Punkten, im Browser als skalierte Overlay-Ebene | Siehe "pdf.js oder Backend-PNG" | HIGH (Wahl), MEDIUM (DOCX-Zuordnung) |
| Benachrichtigung "fertig" | PHP `OCP\Notification\IManager` + eigener `INotifier` (l10n DE/EN/FR) | statt Notifications aus der ExApp, weil Text und Link in PHP übersetzt werden | MEDIUM |
| Ausgabe neben dem Original | PHP schreibt die vom Backend gelieferte Datei als Nutzer über `IRootFolder` (`_geschwärzt`/`_redacted`/`_caviardé`) | Rechte und Versionen bleiben in Nextcloud; Container hat keinen Schreibzugriff auf Nutzerdateien | MEDIUM |
### pdf.js oder Backend-PNG: Backend-PNG
- **Für Backend-PNG:** dieselbe Engine (PyMuPDF), die die Flächen berechnet und schwärzt, rendert auch das Bild: was der Prüfer sieht, wird geschwärzt. Einheitlich für Text-PDF, Scans und DOCX/ODT (über das LibreOffice-Vorschau-PDF). Kein Text-Layer im Browser, also kein zweiter Extraktor mit anderen Glyphenzuordnungen. Manuelle Flächenschwärzung: Rechteck in Bildpixeln, Umrechnung in PDF-Punkte über Seitengröße und dpi.
- **Gegen pdf.js:** Nextclouds pdf.js steckt in der App `files_pdfviewer`, ist keine öffentliche API und nicht auf jeder Instanz aktiv. Eigenes `pdfjs-dist` 6.5.438 (Apache-2.0) wären mehrere MB Bundle, ein Worker-Skript mit CSP-Sonderregeln und eine zweite Textextraktion, deren Zeichenpositionen von MuPDF abweichen (Spike 5.2: pypdf/pdfminer lasen andere Glyphen als PyMuPDF). Für DOCX/ODT bräuchte pdf.js ohnehin das Backend-PDF.
- **Offen (MEDIUM):** DOCX/ODT werden per lxml auf XML-Ebene geschwärzt, angezeigt wird aber das LibreOffice-PDF. Die Zuordnung "Fund im XML-Text" zu "Rechteck im Vorschau-PDF" muss gebaut werden (Suche der Fundzeichenkette auf der Vorschauseite, Mehrdeutigkeit bei gleichen Wörtern). Eigener Punkt in der Architektur-/Phasenrecherche.
## Installation
# pyproject.toml (Auszug), alles exakt gepinnt
# Dev zusätzlich zum Skeleton
# Laufzeit-Stufe: Systempakete (Tesseract exakt, LibreOffice ungepinnt, siehe Text)
# hadolint ignore=DL3008
# PHP-App, Frontend
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| PyMuPDF 2.1 (gemessen) | PyMuPDF 1.28.2 (25 MB, keine Abhängigkeiten) | Wenn Image-Größe oder onnxruntime-Angriffsfläche wichtiger werden. Gleiche Redaction-API, aber ungemessen: nur nach Wiederholung der Spike-Schwärzungsprobe (0/88 plus Positivkontrollen) |
| transformers 4.57.6 (gemessen) | transformers 5.22.2 | Sobald das Release-Gate mit 5.x dieselbe Leckrate und denselben Personen-Recall zeigt; dann hub 2.x und tokenizers 0.23 mitziehen |
| torch-CPU aus PyTorch-Index | Export von GLiNER2 nach ONNX und Inferenz mit onnxruntime (ist über PyMuPDF ohnehin im Image) | Spart ca. 0,6 GB Image und evtl. RAM. GLiNER2 hat keinen offiziellen ONNX-Export für das Extractor-Modell; eigener Export und Gate-Nachweis nötig. Kandidat für nach v1 |
| Backend-PNG für die Prüfseite | eigenes pdfjs-dist 6.5.438 | Nur wenn Textauswahl im Browser zwingend gewünscht wird |
| PyMuPDF-OCR + Tesseract-CLI | OCRmyPDF 17.13.0 | Wenn PDF/A-Ausgabe oder Deskew/Clean für schlechte Scans Pflicht werden |
| Debian-tessdata 4.1.0 | `tessdata_best` (GitHub, Apache-2.0, eigener Download) | Wenn eine Scan-Messung eine geringere Leckrate zeigt |
| LibreOffice je Auftrag als Prozess | `unoserver` (dauerhaft laufendes soffice) | Wenn Startzeit (wenige Sekunden je Auftrag) stört. Kostet dauerhaft RAM neben dem 4-GB-Stapel: nicht auf kleinen Servern |
| `fr_core_news_lg` zur Laufzeit geladen | FR nur GLiNER2 + Regeln | Nur wenn der Owner LGPL-LR grundsätzlich ausschließt; vorher messen |
| PHP-Dateiaktion über `@nextcloud/files` v4 | AppAPI-Dateiaktion aus der ExApp (`nc_py_api` `ui.files_dropdown_menu`) | Nie hier: Prüfseite, Rechte und Ausgabe liegen ohnehin in der PHP-App; AppAPI-Aktion schickt nur eine Anfrage an den Container |
| eigene Pseudonymisierung (Spike `pseudo.py`) | `presidio-anonymizer` 2.2.366 | Nicht nötig: Schwärzung macht PyMuPDF/lxml, Pseudonyme brauchen Cluster über Varianten, die der Anonymizer nicht kennt; er zöge `cryptography` 50 nur für den Verschlüsselungs-Operator |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `torch` von PyPI | zieht unter Linux CUDA 13.2 (`cuda-toolkit`, `cuda-bindings`, `triton`), mehrere GB | `torch==2.15.0` aus `download.pytorch.org/whl/cpu`, `explicit = true` |
| `gliner2[local]` | zieht `peft` ohne Nutzen | Basispaket + torch/transformers/safetensors explizit |
| `GLiNER2.from_pretrained("<repo-id>")`, `GLiNER2API`/`API` aus `gliner2.api_client` | Netzaufruf bzw. Cloud-Inferenz bei Fastino: Owner-Regel, kein Inhalt nach außen | lokaler Ordner mit gepinnten Dateien, `HF_HUB_OFFLINE=1`; Import von `api_client` per Test verbieten |
| Presidio `AnalyzerEngine()` ohne eigene `NlpEngine`, Modellname statt Pfad | `spacy.cli.download` zur Laufzeit; Standard lädt `en_core_web_lg` | `SpacyNlpEngine` mit absoluten Modellpfaden je Sprache |
| Presidio `EmailRecognizer` in Standardkonfiguration | `tldextract` lädt Public Suffix List aus dem Netz | eigener E-Mail-Erkenner oder `tldextract.TLDExtract(suffix_list_urls=())` mit mitgelieferter Liste |
| Presidio `DE_PLZ`, roher `PhoneRecognizer` | Spike: 45/243 Fristdaten als Telefon, PLZ-Fehlalarme | eigene PLZ+Ort-Regel, Telefon mit Datumsfilter und Kontext |
| `presidio-image-redactor` | Bild-Overlay-Ansatz, zieht OpenCV/Tesseract-Wrapper, nicht im Spike | PyMuPDF `apply_redactions(images=PIXELS)` |
| Flair `ner-german-large` | Lizenz ungeklärt, 7,2 GB RAM, 42 s/Seite (Spike) | Stapel R+S+G2 |
| `numpy>=2.5` | Presidio verlangt `<2.5.0` | `numpy==2.4.6` |
| pikepdf oder pypdf zum Schwärzen | keine Text-Positions-API; pypdf-Ersetzen trifft keine Bildpixel | PyMuPDF; pikepdf nur Nachlauf und Prüfung |
| `draw_rect`/Annotationen ohne `apply_redactions`, inkrementelles Speichern | Spike-Positivkontrollen: 84/88 bzw. 81 Geheimnisse in der Altrevision | `apply_redactions` + `scrub` + Neuschreiben `garbage=4` + pikepdf |
| python-docx oder odfpy zum Schreiben | ersetzen nur Läufe im Hauptteil; Spike "naiv" 19/88 Lecks | lxml direkt auf allen XML-Teilen |
| `defusedxml.lxml` | seit Jahren als veraltet markiert, letzter Release 2021 | lxml-Parser mit `resolve_entities=False, no_network=True` + ZIP-Größenprüfung gegen Zip-Bomben |
| OCRmyPDF, pytesseract | siehe OCR-Abschnitt | PyMuPDF-OCR + Tesseract-CLI |
| LibreOffice aus trixie-backports (26.8) | kein Sicherheits-Supportversprechen wie stable | trixie + trixie-security |
| LibreOffice mit gemeinsamem Profil oder Dauerinstanz | Sperren, Zustand zwischen Aufträgen, Dokumentreste im Profil | Profil je Auftrag in tmp, danach löschen |
| bubblewrap im Container | User-Namespaces unter Docker-seccomp meist gesperrt | rlimits + Zeitlimit + Nicht-Root |
| Netzwerk-Prüfung nur "lokal ausprobiert" | Befund 4: drei Bibliotheken rufen still ins Netz | CI-Test im Container mit `--network none`, der Erkennung, Schwärzung und Prüfung komplett durchläuft |
| `@nextcloud/files` 3.x oder Vanilla-Registrierung über globale Objekte | v3-Registrierungen werden vom Files-App-Code in NC 33+ nicht gefunden | `@nextcloud/files` 4.1.1 gebündelt |
| `files_pdfviewer`/Viewer als Prüfansicht | keine API für Overlays, nicht überall installiert | eigene Prüfseite mit Backend-PNG |
| Faker zur Laufzeit | nur Testdaten | dev-Gruppe |
## Stack Patterns by Variant
- nur Schnellmodus (Presidio + spaCy, Spike 1,4 GB, 0,07 s/Seite) mit sichtbarem Hinweis "gründlicher Modus braucht mehr Speicher"
- weil der volle Stapel 3,96 GB Spitze hat und LibreOffice danach zusätzlich Speicher braucht
- gründlicher Modus als Standard (Owner 07.11.), ein Auftrag zur Zeit
- `/init` nur DE + GLiNER2, EN/FR nach Admin-Schalter oder beim ersten Auftrag dieser Sprache laden (ehrlicher Status "Sprachmodell wird geladen")
- Spracherkennung je Dokument ohne neues Modell: Stoppwort-Quote mit den Findling-Listen; Nutzer kann die Sprache in der Prüfseite überschreiben. `lingua` (170 MB) nicht nötig
- gleicher Stack; alle Wheels einschließlich `torch+cpu`, spaCy/thinc/blis, PyMuPDF, pikepdf, pypdfium2, rapidfuzz vorhanden (geprüft); LibreOffice und Tesseract als Debian-Pakete
- Tempo ungemessen; GLiNER2 auf Cortex-A76 kann ein Vielfaches der 8 bis 11 s/Seite brauchen. Vor Release messen, Fortschrittsanzeige muss das tragen
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| presidio-analyzer 2.2.366 | numpy `<2.5.0`, spaCy `>=3.4.4,<4` (3.8.18), `preshed<3.0.14`, phonenumbers `>=9.0.28,<10`, pydantic `>=2.12.5`, tldextract `>=5.3.1,<6` | Python `>=3.11,<3.15` |
| spaCy 3.8.18 | thinc `>=8.3.12,<8.4.0` (8.3.14), preshed `!=3.0.14,<3.1` (zusammen mit Presidio: 3.0.13), srsly `<3.0.0` | Modelle 3.8.0 verlangen spaCy `>=3.8.0,<3.9.0` (meta.json) |
| gliner2 2.1.0 | torch `>=2.1,<3`, transformers `>=4.43,<6` (Extras, wir pinnen selbst) | Modell mit transformers 5.8.0 gespeichert, mit 4.57.6 gemessen |
| transformers 4.57.6 | huggingface-hub `<1.0` (0.36.2), tokenizers 0.22.x | nicht mit hub 2.x mischen |
| torch 2.15.0+cpu | Python `>=3.11`, manylinux_2_28 | trixie glibc 2.41 passt |
| PyMuPDF 2.1 | onnxruntime (1.31.1), numpy, networkx 3.7, pymupdf4llm/pymupdf-layout 2.1 exakt | abi3, Python `>=3.11` |
| pikepdf 10.17.0 | Pillow `>=10.0.1`, lxml `>=4.8` | Pillow 13.0.0 im Spike |
| pdfminer.six 20260107 | cryptography `>=36` | |
| Tesseract 5.5.0 (CLI) | tessdata 4.1.0 (LSTM) | MuPDF-intern ist eine eigene Tesseract-Version; beide lesen dieselben `.traineddata` (MEDIUM, im Container prüfen) |
| `@nextcloud/files` 4.x | Nextcloud 33 oder neuer | `@nextcloud/vue` 9.14.1 verlangt `@nextcloud/files ^4.1.1` |
| nc-py-api 0.30.3 | starlette `>=1.0.1`, filelock-Override `>=4.2.1` | wie Skeleton |
## Lücken für die Roadmap
## Sources
- PyPI JSON-API, abgefragt 07.11.2026: presidio-analyzer/-anonymizer 2.2.366 (requires_dist inkl. `numpy<2.5.0`), spacy 3.8.18, thinc 8.3.14/10.0.0, gliner2 2.1.0 (Extras), gliner 0.2.30, torch 2.15.0 (requires_dist mit cuda-toolkit 13.2.2), transformers 5.22.2 und 4.57.6, huggingface-hub 2.4.0/0.36.2, tokenizers 0.23.3/0.22.2, safetensors 0.8.0, numpy 2.5.4/2.4.6, pymupdf 2.1 und 1.28.2 (requires_dist, Wheelgrößen), pymupdf-layout/pymupdf4llm 2.1, pikepdf 10.17.0, pypdf 7.0.0, pdfminer.six 20260107, pypdfium2 5.15.0, lxml 6.1.3, odfpy 1.4.1, python-docx 1.2.0, ocrmypdf 17.13.0, pytesseract 0.3.13, rapidfuzz 3.14.6, psutil 7.2.2, defusedxml 0.7.1, onnxruntime 1.31.1, preshed 3.0.13; cp313-Wheels x86_64/aarch64 einzeln geprüft (HIGH)
- `https://download.pytorch.org/whl/cpu/torch/`: `torch-2.15.0+cpu` cp313 manylinux_2_28 x86_64 und aarch64 mit sha256, Größen per HEAD (HIGH)
- uv-Doku "Using uv with PyTorch", https://docs.astral.sh/uv/guides/integration/pytorch/ (CPU-Index, `explicit = true`) (HIGH)
- GitHub API: `microsoft/presidio` 301 Moved Permanently, `data-privacy-stack/presidio` Releases 2.2.364 bis 2.2.366 (HIGH)
- GitHub `explosion/spacy-models` Releases `*-3.8.0`: Assets und Größen; sha256 am 07.11.2026 per Stream selbst berechnet (HIGH)
- Hugging Face API `fastino/gliner2-privacy-filter-PII-multi` (sha `1cb41660...`, Commits, LFS-sha256, Lizenz apache-2.0, `config.json` mit `model_name: microsoft/mdeberta-v3-base`), Weiterleitung auf `us.aws.cdn.hf.co` (HIGH)
- Spike-venv `C:/Users/Student/pii-spike-2026-11-06/.venv`: Paketstände, `meta.json` der spaCy-Modelle (Lizenzen und Quellen), `presidio_analyzer/nlp_engine/spacy_nlp_engine.py:74-82`, `predefined_recognizers/generic/email_recognizer.py:52`, `tldextract/tldextract.py:70,329-389`, `gliner2/models/base.py:36-60,576-630`, `gliner2/models/span/model.py:24,981`, `gliner2/__init__.py:10-27`, `pymupdf-2.1.dist-info/METADATA` und `COPYING` (HIGH)
- LGPL-LR Volltext: https://scancode-licensedb.aboutcode.org/lgpllr.LICENSE, SPDX https://spdx.org/licenses/LGPLLR, Modellkarte https://huggingface.co/spacy/fr_core_news_lg/raw/main/LICENSE (Auslegung MEDIUM)
- Debian madison (qa.debian.org), trixie/trixie-security/trixie-backports: tesseract-ocr 5.5.0-1+b1, tesseract-ocr-deu/eng/fra 1:4.1.0-2, libreoffice-writer-nogui 4:25.2.3-2+deb13u8 (amd64/arm64), Backport 26.8.2, ocrmypdf 16.7.0, ghostscript, bubblewrap 0.12.0, Schriftpakete; packages.debian.org Abhängigkeiten von `libreoffice-writer-nogui` (HIGH)
- OCRmyPDF Installationsdoku https://ocrmypdf.readthedocs.io/en/latest/installation.html (Ghostscript optional seit 17.0.0, pypdfium2-Rendering) (HIGH)
- PyMuPDF-Doku via Context7 `/pymupdf/pymupdf`: `get_textpage_ocr`, `pdfocr_tobytes`, eingebaute Tesseract-OCR mit `TESSDATA_PREFIX` (HIGH)
- `@nextcloud/files` CHANGELOG https://github.com/nextcloud-libraries/nextcloud-files/blob/main/CHANGELOG.md (4.0.0: NC 33+, `registerFileAction({...})`, Kontextobjekt, Scoping) und npm-Registry 07.11.2026 (files 4.1.1, vue 9.14.1, dialogs 8.0.0, vite-config 2.5.4, pdfjs-dist 6.5.438) (HIGH)
- Nextcloud Developer Manual Front-end JS (NC 30 bis 32): `LoadAdditionalScriptsEvent`, `Util::addInitScript`; Forum https://help.nextcloud.com/t/how-to-add-custom-file-actions-to-the-files-app-context-menu-in-nc33/247896 (MEDIUM)
- Spike `C:/Users/Student/pii-spike-2026-11-06/SPIKE-REPORT.md` (Erkennerstapel, RAM, Laufzeit, Schwärzungsverfahren, Glyphen-Befund) und Recherche `C:/Users/Student/neue-apps-recherche-2026-11-04/bigtech-pii-redaction-2026-11-04.md` (HIGH, gemessen bzw. belegt)
- AV-Stack `C:/Users/Student/nextcloud-audio-video-search/.planning/research/STACK.md` (gemeinsame ExApp-Teile) (HIGH)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
