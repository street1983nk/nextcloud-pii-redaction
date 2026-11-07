# Phase 1: Zwei-App-Gerüst und Integrationsbeweis - Research

**Researched:** 2026-11-07
**Domain:** Nextcloud-Zwei-App-Integration (PHP-App `pii_redaction` + AppAPI-ExApp `pii_redaction_backend`), Dateiaktion über `@nextcloud/files` 4.x mit Vite/Vue 3, Auftragsmodell ohne Klartext, Pull-Warteschlange mit Lease, Etag-Bindung, Seitenbild über PHP-Proxy, Benachrichtigung, Ablage per `newFile()`, Logging-Allowlist mit Kanarien-Nachweis
**Confidence:** HIGH für Plattformfakten (Quelltext NC stable33/34/35, app_api stable33, nextcloud-files v4.1.1 heute gelesen) und für alles, was Audio & Video Search (AVS) in CI schon grün belegt hat; MEDIUM für leere Routenliste unter HaRP, Streaming großer Antworten durch HaRP und LibreOffice im Image (Größe ungemessen)

<user_constraints>
## User Constraints

Für Phase 1 gibt es keine CONTEXT.md. Die folgenden Punkte stammen aus PROJECT.md, STATE.md (alle 14 Empfehlungen aus research/SUMMARY.md am 07.11. vom Owner übernommen), ROADMAP.md und dem Auftrag; sie gelten als gesetzt.

### Locked Decisions
- Zwei Apps im Lockstep: PHP-App `pii_redaction` (Zertifikat #1411, gemergt 05.11.2026) und ExApp `pii_redaction_backend` (Zertifikat #1419, offen; Status nur lesen, nicht kommentieren).
- Die PHP-App ist die Sicherheits- und Workflow-Grenze; der Container hat keine Browser-Routen, jede Nutzeranfrage geht über PHP mit Rechte-Recheck bei jeder Anfrage (PLAT-05).
- Klartext-PII nur im Container-Volume; Nextcloud-DB nur geschlossene Status- und Grundlisten, kein Freitext, keine Einzelwert-Hashes.
- Einstieg als Dateiaktion in der Dateien-App für PDF, DOCX, ODT; Analyse als Hintergrundauftrag; Benachrichtigung ohne Fundinhalt; eigene Prüfseite in der PHP-App.
- Seitenbilder serverseitig gerendert (Backend-PNG), nicht pdf.js.
- Download-Sperre der Freigabe blockiert den Start, ohne Admin-Ausnahme in v1 (Owner-Entscheid 5).
- Ausgabe erst nach Freigabe; Ablage per `getNonExistingName()` + `newFile()` als Auftraggeber neben dem Original, nie überschreiben.
- Ein Auftrag zur Zeit je Container, Zulassung über RAM-Wächter; RAM-Schwellen erst nach Messung festschreiben.
- Seitenlimit 300, TTL Prüfzustand 14 Tage (Owner-Entscheid 13; Durchsetzung in späteren Phasen, Spalten jetzt).
- Datenschutz: kein Inhalt, kein Fund, keine Telemetrie verlässt den Server.
- Alle nutzersichtbaren Texte und README DE/EN/FR im Gleichstand, Deutsch zuerst, echte Umlaute nur in Prosa (nie in Code, URLs, YAML), keine Gedankenstriche (U+2013/U+2014), keine Emojis.
- Qualität vor Speed, Produkt-Fix vor Harness-Patch, Gegenprobe nie mit dem Muster der Umsetzung (immer mit Positivkontrolle).
- Gates: ruff-Vollsatz, ruff format, pyright basic (`PYRIGHT_PYTHON_FORCE_VERSION=latest`), vulture lokal grün.
- Commits nur als `street1983nk <k.cherif@outlook.de>`, ohne Claude-Session-Zeilen, nie "closes #N" (oder "fixes/resolves #N").
- Vor jedem Push, Merge oder Kommentar den Owner fragen; UI-Abnahme gemeinsam per Playwright (375/768/1280, hell/dunkel).

### Claude's Discretion
- Form der Warteschlange (Spalten, Lease-Dauer, Claim-Regel), Inhalt der Dummy-Kopie, Rendering-Weg für Seite 1, Ort und Art der Container-Messungen, Logging-Allowlist, Form des Kanarien-Nachweises: in diesem Dokument je mit Empfehlung.

### Deferred Ideas (OUT OF SCOPE für Phase 1)
- Echte Erkennung, Positionsindex, Funde, Prüf-UI mit Kästchen (Phasen 3, 8, 9).
- Kindprozess-Sandbox in voller Härte, Bomben-/XXE-Korpus, Ablehnung verschlüsselter/defekter Dateien mit Grund (Phase 2, JOB-05, SAFE-*).
- Vier-Augen-Freigabe, TTL-Durchsetzung, Lebenszyklus-Purge vollständig (Phase 10), Protokoll (Phase 11).
- Netzfreiheitsbeweis `--network none` über den ganzen Pfad (PLAT-04, Phase 10).
- Store-Upload (Phase 15).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-01 | Zwei Apps aus dem Store, Lockstep, Upgrade-Beweis in CI | Entscheid 1 und 11; AVS `test_lockstep_versions.py`, Job `upgrade` mit `occ upgrade` + `app_api:app:update` (in AVS-CI grün, Lauf 42330693906), Viewer-Checkout-Fix |
| PLAT-02 | Klare Meldung bei fehlender, nicht erreichbarer oder anders versionierter Gegen-App | AVS `ExAppService::backendState` mit 7 Zuständen + `companion`-Zustand im Container, `PublicFunctions::getExApp()` (stable33 gelesen) |
| PLAT-03 | NC 33/34/35, HaRP, amd64 + arm64, nur CPU | AVS `deploy-harp.yml` sechs Beine grün; alle drei Server-Zweige pinnen `@nextcloud/files ^4.1.1`, `@nextcloud/vue ^9.14`, `vue ^3.5.44` (package.json gelesen) |
| PLAT-05 | Keine Browser-Routen im Container; PHP prüft Rechte bei jeder Anfrage | Entscheid 9: `ExAppProxyController::prepareProxy` gibt 404, wenn keine Route passt (stable33 gelesen); Recheck-Muster `ReaderContext::actAs` + `FileAccess::readableFile` |
| JOB-01 | Dateiaktion für PDF, DOCX, ODT | Entscheid 2: `registerFileAction` v4.1.1 (Quelltext), Laden über `LoadAdditionalScriptsEvent` + `Util::addInitScript` (ViewController stable33), `.mjs` wird geladen (`JSResourceLocator::appendScriptIfExist`) |
| JOB-02 | Hintergrundauftrag, ehrlicher Fortschritt, Benachrichtigung ohne Fundinhalt | Entscheid 4 (Fortschritt über OCS-Meldungen des Containers), Entscheid 7 (`INotifier::prepare`, stable33), Warteschlangenposition aus `oc_pii_jobs` |
| JOB-03 | Nur Leserecht startet und prüft (Gruppenordner-ACL, Freigaben); Download-Sperre blockiert | Entscheid 5: `ISharedStorage::getShare()` (seit 30) + Attribut `permissions/download` wie `files_sharing/lib/ViewOnly.php`; JS-Spiegel `isDownloadable` (apps/files/src/utils/permissions.ts) |
| JOB-04 | Bindung an Datei-ID + Etag, Änderung macht ungültig | Entscheid 6: Etag beim Start, Gateway verweigert bei Abweichung, `NodeWrittenEvent`-Listener, Recheck auf jeder Prüfseiten-Anfrage und vor der Ablage |
| JOB-06 | Ein Auftrag zur Zeit je Container, RAM-Zulassung, sichtbare Position | Entscheid 4: Claim nur ohne aktiven Lease (PHP) + Semaphore 1 (Container) + Findling `memory_guard.headroom_bytes`; Schwellen vorläufig, Messung nach Entscheid 12 |
</phase_requirements>

## Summary

Phase 1 ist ein Walking Skeleton nach dem AVS-Muster, aber mit einer anderen Achse: AVS bewies den Weg "Suche -> Treffer -> Abspielseite", hier muss der Weg "Dateiaktion -> Auftrag -> Container zieht Arbeit -> lädt über das Gateway -> rendert Seite 1 -> meldet fertig -> Benachrichtigung -> Platzhalter-Prüfseite zeigt das Bild über PHP -> Platzhalter-Kopie per `newFile()`" auf NC 33/34/35 und amd64/arm64 echt durchlaufen. Rund zwei Drittel lassen sich aus AVS kopieren und sind dort in CI grün (Lockstep, Gateway, ReaderContext, ExAppService mit sieben Zuständen, Handshake, Admin-Statusbereich, deploy-harp-Matrix, Upgrade-Job, Drift-Schritte, zwei Store-Archive, Playwright-Gerüst, Secret-Scan). Neu sind fünf Bausteine: die Dateiaktion mit Vite-Build, die Warteschlange mit Lease (Vorlage Findling `QueueMapper`), das Auftragsmodell mit Etag-Bindung und geschlossenen Listen, der Seitenbild-Proxy mit Recheck und die Ablage per `newFile()`.

Die Plattformfragen sind am Quelltext geklärt. Alle drei Server-Zweige pinnen `@nextcloud/files ^4.1.1`; die Bibliothek legt Aktionen unter `window._nc_files_scope.v4_0` ab, also findet die Dateien-App eine mit 4.1.1 gebündelte Aktion auf 33, 34 und 35. Nextcloud lädt `js/<app>-<name>.mjs` als Modul, wenn die Datei existiert, und die Dateien-App feuert `LoadAdditionalScriptsEvent`. AppAPI gibt für jede ExApp-Route, die in `info.xml` fehlt, 404 zurück (`prepareProxy`); der Container kann also ganz ohne Routen auskommen, signierte Aufrufe aus PHP prüft HaRP nicht. `exAppRequest` reicht `options` bis zum Nextcloud-HTTP-Client durch; `stream => true` liefert über `getBody()` eine PHP-Ressource, die `newFile($name, $resource)` (seit 19) und `StreamResponse` (Handle oder Pfad) direkt annehmen. Der Standard-Timeout ist 3 s und muss je Aufruf gesetzt werden.

Drei Dinge verlangen eine bewusste Entscheidung des Planers, und hier ist je eine Empfehlung: (1) LibreOffice kommt schon in Phase 1 ins Image, weil Erfolgskriterium 2 Seite 1 auch für DOCX/ODT verlangt und die Image-Größe (heute LOW, geschätzt +350 bis 550 MB) sonst erst spät gemessen würde; Rendering und Konvertierung laufen bereits als Kindprozess mit leerer Umgebung, Zeitgrenze und Gruppen-Kill (Vorform der Phase-2-Sandbox). (2) Das Gateway von AVS/Findling erlaubt dem Container, jede Datei jedes Nutzers zu lesen; für PII wird es auftragsgebunden (Job-ID + Claim-Token, nur die Datei des Auftrags, nur als Auftraggeber, nur bei gleichem Etag). (3) Die Platzhalter-Kopie enthält keinen Originalinhalt, nur einen festen Hinweistext, damit ein Phase-1-Build nie eine ungeschwärzte Datei mit Schwärzungs-Suffix erzeugt.

**Primary recommendation:** Repo auf `php/` + `backend/` umbauen (AVS-Commit-Folge 01-01 als Vorlage), AVS-Bausteine kopieren statt neu schreiben, die fünf neuen Bausteine nach den Mustern unten bauen, und CI ab Welle 2 früh auf einem Branch `phase-01` laufen lassen (AVS-Plan 01-12), weil PHP, Vite-Build, HaRP und Playwright lokal nicht prüfbar sind.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dateiaktion anzeigen (Mime, Leserecht, Download-Sperre) | Browser (Dateien-App, `@nextcloud/files` 4.1.1) | - | Nur Komfort; keine Sicherheitsentscheidung |
| Auftrag anlegen nach Rechteprüfung | PHP-App (JobController/JobService) | DB (`oc_pii_jobs`) | Echtes Rechtemodell nur in Nextcloud |
| Warteschlange, Lease, Position, ein Auftrag zur Zeit | PHP-App (QueueController/QueueMapper) | Container (Semaphore 1, RAM-Zulassung) | Ein Ort für Zustand; Container ist Rechenknecht |
| Originalbytes lesen | PHP-App (Gateway, auftragsgebunden) | Container (Download mit sha256 im Strom) | Container hat keinen eigenen Dateizugang |
| Rendering Seite 1, DOCX/ODT -> PDF | Container (Kindprozess PyMuPDF, soffice) | Volume `work/<job>/` | C-Code auf fremden Eingaben, nie im FastAPI-Prozess |
| Seitenbild an den Browser | PHP-App (ReviewController, Recheck je Anfrage) | Container (signierte Route) | PLAT-05: keine Browser-Route im Container |
| Benachrichtigung | PHP-App (`INotifier`) | - | Übersetzung DE/EN/FR in PHP, Link auf PHP-Route |
| Kopie neben dem Original | PHP-App (PublishJob, `newFile()` in `actAs`) | Container (liefert Bytes, nur im Zustand fertig) | Container schreibt nie in Nutzerdaten |
| Etag-Bindung | PHP-App (Start, Gateway, Listener, Recheck, Ablage) | Container (meldet gesehenen Etag) | Etag kennt nur Nextcloud |
| Lockstep, Gegen-App-Zustände | PHP-App (Admin-Statusbereich) | Container (`/status`, Handshake) | Meldung erscheint dort, wo der Admin schaut |
| Logging ohne Inhalt | beide | CI (Kanarien-Scan) | Owner-Regel, mechanisch geprüft |

## Die zwölf Entscheide für Phase 1

### Entscheid 1: Repo-Umbau und IDs

- Layout wie AVS: `backend/` (ExApp, Python-Paket `pii_redaction_backend`, `appinfo/info.xml` mit `<id>pii_redaction_backend</id>`, Image `ghcr.io/street1983nk/pii_redaction_backend`), `php/` (App `pii_redaction`, Namespace `OCA\PiiRedaction`), `ci/` (Playwright, Saat, Fixtures, Skripte), Doku an der Wurzel. [VERIFIED: AVS-Repo, Commits bae7b42 ff.]
- Heute liegt das Skeleton mit `<id>pii_redaction</id>` an der Wurzel (`appinfo/`, `src/pii_redaction/`, `Dockerfile`). Die ID wandert an die PHP-App (Zertifikat #1411 gehört zu `pii_redaction`, Pin `4f61842e...` in `release.yml` stimmt mit `~/.nextcloud/certificates/pii_redaction.crt` überein, heute nachgerechnet). [VERIFIED: openssl]
- Der Schlüssel für das Backend liegt lokal vor (`pii_redaction_backend.key`/`.csr`); der Pin des öffentlichen Schlüssels, auf demselben Weg wie in `release.yml` berechnet, ist `7a8c64ae174d6d7aebf968519725989c5a8672d4abb54eb4366887a980ab6d4d`. Nach Ausstellung von #1419 gegen das Zertifikat gegenprüfen und eintragen; bis dahin `BACKEND_CERT_PUBKEY_SHA256: pending-certificate` wie AVS. [VERIFIED: gh PR #1419 OPEN, updatedAt 06.11.; Pin lokal berechnet]

### Entscheid 2: Dateiaktion mit `@nextcloud/files` 4.1.1, Vite und Vue 3

**Belege:**
- `registerFileAction(action: IFileAction)` validiert `id` (string), `displayName`, `iconSvgInline`, `exec` (Pflicht, Funktionen), optional `enabled`, `title`, `order`, `execBatch`, `default`, `hotkey`, `parent`. Alle Callbacks bekommen ein Kontextobjekt `{ nodes, view, folder, contents }`; `exec` bekommt `ActionContextSingle` mit `nodes: [INode]` und gibt `Promise<boolean | null>` zurück. [VERIFIED: nextcloud-files v4.1.1 `lib/ui/actions/fileAction.ts`, `lib/ui/types.ts`]
- Speicher der Aktionen: `window._nc_files_scope.v4_0.fileActions`. Jede 4.x-Version schreibt in denselben Bereich; stable33, stable34 und stable35 pinnen `@nextcloud/files ^4.1.1`. Eine 3.x-Registrierung landet woanders und wird nicht gefunden. [VERIFIED: `lib/globalScope.ts`; server `package.json` je Zweig]
- Einhängen: `apps/files/lib/Controller/ViewController.php` (stable33) ruft `Util::addInitScript('files','init')`, `Util::addScript('files','main')` und feuert `OCA\Files\Event\LoadAdditionalScriptsEvent`. In einem Listener darauf `Util::addInitScript('pii_redaction', 'pii_redaction-init')`. `addInitScript` lädt die Übersetzungen der App vor dem Skript. [VERIFIED: ViewController.php, `lib/public/Util.php` Z. 114 bis 135]
- Modul-Ausgabe: `JSResourceLocator::appendScriptIfExist` sucht zuerst `<datei>.mjs`, dann `.js`. [VERIFIED: stable33 `lib/private/Template/JSResourceLocator.php`]
- Build: `@nextcloud/vite-config` 2.5.4 (`createAppConfig({ init: 'src/init.ts', review: 'src/review.ts', admin: 'src/admin.ts' })`), Ausgabe nach `js/`, Peer `vite ^7.3.6`. Aktuell ist vite 8.3.6, also **vite 7.3.7 exakt pinnen** (Server nutzt `^7.3.7`). [VERIFIED: npm registry, README der vite-config]

**Empfehlung `enabled()` (nur Komfort, PHP prüft alles nochmal):**
- genau ein Knoten, `node.type === FileType.File`;
- Mime in `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.oasis.opendocument.text`;
- `(node.permissions & Permission.READ) !== 0`;
- `isDownloadable(node)` nachgebaut aus `apps/files/src/utils/permissions.ts` (nicht exportiert): `hide-download` falsch und Share-Attribut `permissions/download` nicht `false`;
- nicht in den Ansichten `trashbin` und nicht ohne angemeldeten Nutzer (`getCurrentUser() === null`);
- `node.attributes['is-encrypted']` nicht wahr (E2EE-Ordner; die echte Ablehnung mit Grund ist JOB-05, Phase 2). [ASSUMED: Attributname `is-encrypted` aus Erfahrung, in CI prüfen]

**`exec()`:** `axios.post(generateUrl('/apps/pii_redaction/api/v1/jobs'), { fileId: node.fileid })` (`@nextcloud/axios` setzt das Request-Token), danach `showSuccess` mit Text "Analyse gestartet, Position N" und einem Link auf die Platzhalter-Prüfseite; bei Fehler `showError` mit einem Satz aus der geschlossenen Grundliste. Rückgabe `null` (keine eigene Erfolgsmeldung der Dateien-App). Läuft für dieselbe Datei mit demselben Etag schon ein offener Auftrag, liefert der Server diesen zurück (idempotent).

**Build-Ausgabe nicht einchecken:** `php/js/` in `.gitignore`; `npm ci && npm run build` in `php.yml`, `deploy-harp.yml` (vor `mv app-src/php apps/pii_redaction`), `upgrade` und `release.yml`; `store-archive.sh stage-companion` nimmt `js/` aus dem Build mit und prüft, dass `js/pii_redaction-init.mjs` darin liegt. `package-lock.json` eingecheckt, Dependabot für npm. Keine der Bibliotheken hat ein `postinstall` (npm view). [VERIFIED: npm view scripts.postinstall leer für vite-config, files, vue, vite]

### Entscheid 3: Datenmodell in Nextcloud ohne Klartext

Phase 1 legt alle Spalten an, die die Architektur für die Nextcloud-DB vorsieht, damit keine spätere Phase Klartextspalten nachzieht. [CITED: research/ARCHITECTURE.md "State Management"]

```
oc_pii_jobs(
  id BIGINT PK, file_id BIGINT, initiator_uid STRING(64), file_etag STRING(40),
  mode STRING(16)         -- 'redact' | 'pseudonymize' (Phase 1 nur 'redact')
  status STRING(16)       -- geschlossene Liste
  reason STRING(32) NULL  -- geschlossene Liste
  task STRING(16) NULL    -- 'analyze' | 'apply' | 'purge'
  stage STRING(16) NULL   -- geschlossene Liste des Fortschritts
  pages_done INT NULL, pages_total INT NULL,
  claim_token STRING(64) NULL, lease_until BIGINT NULL, attempts SMALLINT,
  revision INT NULL, revision_hash STRING(64) NULL,
  output_file_id BIGINT NULL,
  created_at BIGINT, updated_at BIGINT, expires_at BIGINT)
oc_pii_job_events(id, job_id, uid, action STRING(32), at BIGINT)
```

- `status`: `queued, analyzing, review, submitted, approved, applying, verified, published, failed, stale, cancelled, expired` (ganze Liste jetzt, Phase 1 nutzt `queued, analyzing, review, applying, verified, published, failed, stale, cancelled`).
- `reason`: `encrypted_pdf, unsupported_format, too_many_pages, out_of_memory, repeatedly_stuck, leak_detected, check_error, original_changed, original_deleted, target_not_writable, backend_state_lost, download_blocked, not_readable, render_failed, backend_unavailable`.
- `stage`: `waiting, fetching, converting, rendering, done`.
- Status, Grund und Stufe als PHP-`enum` (string-backed) und als Python-`Literal`/`StrEnum`; der Mapper weist alles außerhalb der Liste zurück; der Container darf in Meldungen nur Werte der Liste schicken (PHP prüft, Container liegt außerhalb der Vertrauensgrenze).
- **Kein** Dateiname, kein Pfad, kein Mime, kein Basisname in der DB (Dateiname ermittelt PHP bei Bedarf aus `file_id` im Nutzerkontext).
- Nextcloud-Regeln für Migrationen: `BOOLEAN`-Spalten nur mit `notnull => false` (Findling-Migration so); Tabellen- und Indexnamen kurz halten (Präfix `pii_`). [VERIFIED: Findling `Version001000Date20260816000000.php`; Längengrenze ASSUMED]

### Entscheid 4: Warteschlange mit Lease und "ein Auftrag zur Zeit"

**Muster:** Pull wie Findling `QueueMapper`: Kandidaten ohne Sperre lesen, dann **eine** bedingte `UPDATE`, die die Frei-Bedingung im `WHERE` wiederholt und ein zufälliges `claim_token` setzt; gewonnen hat nur, wessen Token zurückgelesen wird. Abgelaufener Lease macht die Zeile wieder frei, `attempts` zählt beim Ausgeben. Kein dialektabhängiges `SELECT ... FOR UPDATE`. [VERIFIED: Findling `php/lib/Db/QueueMapper.php` Kopfkommentar und `claimBatch`]

**OCS-Routen der PHP-App (alle `#[ExAppRequired]` + `EX-APP-ID == pii_redaction_backend`, AVS `rejectForeignCaller`):**

| Route | Zweck | Antwort |
|---|---|---|
| `POST /ocs/v2.php/apps/pii_redaction/api/v1/queue/claim` | höchstens **eine** Aufgabe, Reihenfolge purge > apply > analyze, FIFO; `analyze`/`apply` nur, wenn kein anderer Lease dieser Arten aktiv ist | `{jobId, task, token, fileId, userId, etag, leaseSeconds}` oder `{}` |
| `POST .../queue/{jobId}/progress` | `{token, stage, pagesDone, pagesTotal}`; verlängert den Lease; nur Werte der Liste | `{ok}` oder 409 (Token fremd, Auftrag ungültig) |
| `POST .../queue/{jobId}/ack` | `{token, result, reason?, pages?, etagSeen, output?: {sha256, size}}` | `{ok}`; setzt Status, Benachrichtigung, ggf. PublishJob |
| `GET .../handshake` | Companion-Version (AVS) | `{version}` |
| `GET .../files/{jobId}?token=` | Gateway, auftragsgebunden (Entscheid 5) | Datei-Strom + `X-Pii-Etag` |

**"Ein Auftrag zur Zeit" doppelt:** PHP gibt `analyze`/`apply` nur aus, wenn keine andere Zeile dieser Arten einen gültigen Lease hat (Bedingung in derselben `UPDATE`); der Container führt einen einzigen Runner mit `asyncio.Semaphore(1)` und fragt nur, wenn der Wächter zulässt. `purge` läuft daneben (kein Rendering).

**Lease-Werte (vorläufig):** `analyze` 120 s, `apply` 300 s, Verlängerung bei jeder `progress`-Meldung; drei Ausgaben ohne `ack` -> `failed(repeatedly_stuck)`. Die echten Werte (Seitenzahl x Dauer je Seite + Kaltstart) setzt Phase 8 nach Messung.

**Warteschlangenposition:** PHP zählt `queued`-Zeilen mit `task = analyze` und kleinerer `id` plus 1, wenn gerade ein Lease läuft. Die Prüfseite fragt `GET /apps/pii_redaction/api/v1/jobs/{id}` alle 3 s (mit Recheck) und zeigt Status, Stufe, `pagesDone/pagesTotal`, Position. Keine geschätzte Restzeit in Phase 1 (nichts gemessen; "ehrlich" heißt: nur echte Zähler).

**RAM-Zulassung (Grundform):** Findling `memory_guard.py` + `hardware.py` kopieren (stdlib, cgroup v2 `memory.max` minus `anon`, gedeckelt durch `MemAvailable`; unlesbar = nicht zulassen). Bedarf je Kindprozess-Art als Konstante mit Kommentar "vorläufig, nach Messung Phase 1/2 festschreiben": `render` 512 MiB, `soffice` 1 GiB. [VERIFIED: Findling `memory_guard.py`]

### Entscheid 5: Rechte bei Start und bei jeder Anfrage, Download-Sperre

- **Recheck-Funktion** (eine, in `FileAccess`): `actAs($uid, fn() => FileAccess::readableFile($rootFolder->getUserFolder($uid), $fileId))` aus AVS 1:1 (Gruppenordner-Falle `in_share`, Findling #14), dann `downloadBlocked($node)`, dann Etag-Vergleich. [VERIFIED: AVS `GatewayController`, `FileAccess`, `ReaderContext`]
- **Download-Sperre** wie `apps/files_sharing/lib/ViewOnly.php::checkFileInfo`, aber über öffentliche API: `$storage->instanceOfStorage(\OCP\Files\Storage\ISharedStorage::class)` (seit 30), dann `$storage->getShare()->getAttributes()?->getAttribute('permissions', 'download') === false` -> gesperrt; zusätzlich `getHideDownload()` defensiv. Nicht `OCA\Files_Sharing\ViewOnly` aufrufen (fremde App, keine öffentliche API). [VERIFIED: ViewOnly.php Z. 82 bis 97, ISharedStorage.php stable33]
- Gilt beim Start **und** bei jeder Prüfseiten-Anfrage (ein Bild der Seite ist Inhalt); Grund `download_blocked`.
- **Mitgliedschaft:** Phase 1 kennt nur den Auftraggeber als Mitglied. Anderer Nutzer mit Leserecht auf die Datei sieht den Auftrag trotzdem nicht (403/404 ohne Namen). Mit-Prüfer und Freigeber kommen in Phase 10.
- **Gateway auftragsgebunden** (Verbesserung gegenüber AVS/Findling, die jede Datei jedes Nutzers lesen lassen): Pfad enthält `jobId`, Query `token`; PHP prüft Token = `claim_token`, Lease gültig, Status `analyzing`, dann Recheck als `initiator_uid` auf genau `file_id`; Etag ungleich -> 409 und Auftrag `stale(original_changed)`. Antwort-Header `X-Pii-Etag`. Damit kann ein kompromittierter Container nicht beliebige Dateien ziehen.

### Entscheid 6: Etag-Bindung

| Kante | Prüfung | Folge bei Abweichung |
|---|---|---|
| Start | `file_etag = $node->getEtag()` als Auftraggeber | - |
| Gateway | aktueller Etag = `file_etag` | 409, `stale(original_changed)` |
| `ack` | `etagSeen` (aus `X-Pii-Etag`) = `file_etag` und aktueller Etag = `file_etag` | `stale(original_changed)`, keine Benachrichtigung "bereit" |
| Listener `NodeWrittenEvent` | offene Aufträge mit `file_id` | `stale(original_changed)` + `purge` |
| Listener `NodeDeletedEvent` | dito | `cancelled(original_deleted)` + `purge` |
| Prüfseite, Seitenbild, Status | aktueller Etag | Seite zeigt "Datei wurde geändert, bitte neu starten", Bild 409 |
| PublishJob | aktueller Etag | keine Ablage, `stale` |

Test deterministisch ohne Zeitrennen: (a) phpunit für Gateway und `ack` mit falschem Etag; (b) CI: Auftrag bis `review`, dann Datei per WebDAV `PUT` ändern, Prüfseite und Seitenbild müssen "geändert" bzw. 409 liefern, Status `stale`. Hinweis: Externe Speicher können den Etag ohne Inhaltsänderung wechseln; das ergibt ein harmloses falsches `stale` (fail-safe), in der Doku nennen. [ASSUMED: Etag-Verhalten externer Speicher]

### Entscheid 7: Benachrichtigung ohne Fundinhalt

- `OCP\Notification\IManager` + eigener `INotifier` (`getID()`, `getName()`, `prepare(INotification, string $languageCode)`; seit 30 `UnknownNotificationException` statt `InvalidArgumentException` werfen). [VERIFIED: stable33 `INotifier.php`]
- Betreff aus geschlossener Liste: `review_ready`, `job_failed`, `job_stale`, `copy_created`; Objekt `('job', jobId)`; Link auf `/apps/pii_redaction/review/{jobId}`; `markProcessed`, wenn der Nutzer die Seite öffnet.
- **Empfehlung: auch kein Dateiname im Text.** Der Push-Weg der Notifications-App schickt den aufbereiteten Betreff (verschlüsselt) über den Push-Proxy zu Apple/Google; Dateinamen tragen in Behörden oft Namen ("Bescheid_Müller.pdf"). Die Prüfseite zeigt den Namen nach Recheck. Owner bestätigt (Offene Frage 2). [ASSUMED: Push-Payload enthält den Betreff]
- **CI-Falle:** Die Notifications-App liegt nicht im Server-Repo (Liste `apps/` stable33 heute gelesen: keine `notifications`). `nextcloud/notifications` Zweig `stable33/34/35` auschecken und aktivieren, sonst gibt es keine OCS-Route zum Prüfen. [VERIFIED: gh API]

### Entscheid 8: Platzhalter-Kopie und Ablage per `newFile()`

- **Ablauf Phase 1:** Prüfseite zeigt im Zustand `review` einen Knopf "Platzhalter-Kopie anlegen" (simuliert die spätere Freigabe) -> Status `approved`, `task = apply` -> Container erzeugt eine einseitige PDF mit festem Hinweistext ("Platzhalter aus PII Redaction, keine Schwärzung", dreisprachig, Auftragsnummer), **ohne jeden Originalinhalt** -> `ack(verified, {sha256, size})` -> PHP stellt einen `QueuedJob` (`PublishJob`) ein.
- **PublishJob:** `exAppRequest(..., 'GET', options: ['stream' => true, 'timeout' => 120])` auf die signierte Container-Route `/jobs/{id}/output`; Strom in `php://temp` kopieren mit `hash_update` und Größendeckel, sha256 und Größe gegen `ack` prüfen; dann in `actAs(initiator)`: Recheck (lesbar, Etag gleich), Elternordner `isCreatable()`, `getNonExistingName(<stamm>_<suffix>.pdf)`, `newFile($name, $tempStream)`; `output_file_id` speichern, Status `published`, Benachrichtigung `copy_created`, `task = purge`. [VERIFIED: `Folder::newFile` string|resource seit 19, `getNonExistingName`; Client `stream` -> `getBody()->detach()`]
- **Suffix** nach Sprache des Auftraggebers (`_geschwärzt`, `_redacted`, `_caviardé`) als reine Funktion mit phpunit; Dateiname ist UTF-8, Nextcloud erlaubt Umlaute im Namen (Umlaut-Regel betrifft Code/URLs, nicht Nutzerdaten). Weil der Inhalt nur ein Hinweis ist, ist der echte Suffix unschädlich; alternativ ein eigener Phase-1-Suffix `_platzhalter` (Offene Frage 3).
- **Warum QueuedJob statt direkt im `ack`:** Der `ack` ist eine Anfrage des Containers; ein Rückruf in den Container aus demselben PHP-Worker koppelt beide Laufzeiten, und der eingebaute PHP-Server der CI hat nur `NEXTCLOUD_WORKERS` (Standard 4) Arbeiter. In CI den Job mit `./occ background-job:execute --force-execute <id>` oder einer `cron.php`-Schleife anstoßen; in der Doku auf Cron-Modus hinweisen. [VERIFIED: server `composer.json` `serve` mit `PHP_CLI_SERVER_WORKERS=${NEXTCLOUD_WORKERS:=4}`; occ-Befehl ASSUMED, im CI-Lauf prüfen]

### Entscheid 9: Keine Browser-Routen im Container

- `backend/appinfo/info.xml` bekommt **ein leeres `<routes/>`-Element** statt `^/status$` ADMIN. `ExAppProxyController::prepareProxy` antwortet 404, wenn `passesExAppProxyRoutesChecks` keine Route findet; `heartbeat`, `init`, `enabled` sind ohnehin gesperrt. Signierte `exAppRequest`-Aufrufe aus PHP prüft HaRP nicht gegen die Liste (Skeleton-Kommentar, AVS belegt). [VERIFIED: app_api stable33 `ExAppProxyController.php` Z. 236 bis 279]
- **Warum leer statt weglassen:** `ExAppService` setzt Routen nur `if (isset($appInfo['external-app']['routes']))`; fehlt das Element bei einem Update von einer Version mit Routen, bleiben die alten in der DB. Ein leeres Element ergibt ein leeres Array und überschreibt. [VERIFIED: ExAppService.php Z. 98 bis 100; dass das Update denselben Pfad nimmt: ASSUMED, CI-Upgrade-Job prüft es]
- **Tests:** Python-Gate auf `info.xml` (kein `<route>`, `<routes/>` vorhanden); CI als `alice` und als `admin`: `GET /index.php/apps/app_api/proxy/pii_redaction_backend/status` und `.../jobs/1/pages/1.png` -> 404; unsigniert direkt über HaRP `/exapps/pii_redaction_backend/status` -> nicht 200. Das gleiche nach dem Upgrade.
- Achtung: Die Skeleton-CI prüft heute "the admin route answers through HaRP"; dieser Schritt wird zur Negativprüfung umgebaut.

### Entscheid 10: Logging-Allowlist und Kanarien-Nachweis

**Python:** `logs.py` wird strenger als das Skeleton: (a) `extra`-Felder nur aus einer Allowlist (`job_id, task, stage, status, reason, pages, bytes, duration_ms, attempt, http_status, exc_type, child, rss_kb`), alles andere fällt weg; (b) keine Ausnahme-Nachrichten und keine Tracebacks in die Zeile (heute schreibt `formatException` den Traceback samt Nachricht), nur `exc_type` und `module:lineno` des innersten eigenen Rahmens; (c) uvicorn-Zugriffslog aus (`access_log=False`), Fehlerlogger von uvicorn/starlette über denselben Formatter; (d) stdout/stderr von Kindprozessen (soffice, PyMuPDF-Warnungen) nie loggen, nur Exit-Code -> `reason`. AST-Gate: jeder Logger-Aufruf hat als erstes Argument ein String-Literal ohne `%`/`{}`-Platzhalter, kein f-String, kein `logger.exception`, kein `print`.
**PHP:** AVS-Regel 6 (kein Pfad/Name in Log-Aufrufen) übernehmen und erweitern: Kontext-Schlüssel nur `jobId, fileId, status, reason, app, exception` (AVS legt Ausnahmen in `exception`, Nachricht statisch).

**Kanarie in CI (Erfolgskriterium 5):**
1. Fixtures `ci/fixtures/canary.pdf|.docx|.odt` per stdlib-Skript erzeugen (`ci/make_fixtures.py`: minimale PDF mit unkomprimiertem Textstrom, DOCX/ODT als ZIP aus festem XML), Kanarienwert z. B. `PIIKANARIE7Q4XZ9` nur im Textkörper, **nicht** im Dateinamen und nicht in Metadaten.
2. **Positivkontrolle** (Owner-Regel): derselbe grep findet die Kanarie in der hochgeladenen Originaldatei unter `data/<uid>/files/` (PDF direkt, DOCX/ODT über `unzip -p`). Ohne Treffer dort ist der Scan wertlos und der Schritt rot.
3. Nach dem ganzen Durchlauf (Start, Fortschritt, Seite 1, Benachrichtigung, Platzhalter-Kopie, Stale-Test): Kanarie darf nicht vorkommen in SQLite-Dump der Nextcloud-DB (`python3 -c "import sqlite3; ...iterdump()"`, kein `sqlite3`-CLI nötig), `data/nextcloud.log`, PHP-Server-Log, `docker logs` des Containers, HaRP- und nginx-Log, Dump von `state.db` im Container. Seitenbilder (PNG, komprimiert) und `work/<job>/src` sind ausgenommen und benannt.

### Entscheid 11: Lockstep, Gegen-App-Zustände, Upgrade

Aus AVS kopieren, IDs tauschen: `test_lockstep_versions.py` (drei Werte + `pyproject.toml` + Serverfenster + CI-Matrix), `ExAppService::backendState` (Zustände `no_app_api, backend_missing, backend_disabled, backend_unreachable, version_drift, version_patch_differs, ok`, dazu "Neuprüfung gescheitert" im Statusbereich), `HandshakeController` + `companion.py` (Container meldet `companion: ok|missing|unknown`, arbeitet bei `missing` nicht; 412 vor der Aktivierung zählt nicht als Fehler, AVS-Fix 7e423e1), Admin-Statusbereich, Drift 1 bis 4, Job `upgrade` 0.0.1 -> 0.1.0 mit Volume-, Inode- und Datenabgleich. Zusätzlich zu AVS: Bei `version_drift`, `backend_*` und `companion missing` verweigert `POST /jobs` mit Grund `backend_unavailable`, und die Dateiaktion zeigt die Meldung statt eines Fehlers. [VERIFIED: AVS-Code und CI-Lauf 42330693906 grün, 6 Beine + 4 Upgrade-Beine]

### Entscheid 12: Container-Messungen (wo und welche)

| Messwert | Wo | Wie | Wofür |
|---|---|---|---|
| Image-Größe amd64/arm64 (mit LibreOffice, PyMuPDF 2.1) | `docker.yml` je Architektur | `docker image inspect --format '{{.Size}}'` + komprimierte Größe aus dem Manifest | STACK-Lücke "LOW, im ersten Build messen" |
| Kaltstart bis bereit | `deploy-harp.yml` je Bein | Zeitstempel vor `app_api:app:register --wait-finish` bis erstes `/status` mit `ready` über signierten Weg | Lease- und Timeout-Werte |
| Leerlauf-RSS des Containers | `deploy-harp.yml` | `/sys/fs/cgroup/memory.current`, `memory.stat anon`, `memory.peak` per `docker exec` | Reserve des Wächters |
| Spitze je Kindprozess (render, soffice) | Container selbst | `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` vor/nach, als Zahl in `/status` (`lastChild: {kind, rssKb, ms}`) | vorläufige Bedarfskonstanten in Entscheid 4 |
| Spitze des Erkennerstapels (Linux-RSS, 3,96 GB laut Spike unter Windows) | **nicht Phase 1**: eigener `workflow_dispatch`-Job `measure.yml` in Phase 2 oder 8 mit den gepinnten Modellen | gleiche Kindprozess-Messung + `memory.peak` | RAM-Schwelle "4,0 GB + 1 GB Reserve" belegen |

Alle Werte als JSON-Artefakt `measurements-<server>-<arch>.json` hochladen (nur Zahlen, keine Namen). Schwellen werden **nicht** in Phase 1 festgeschrieben (Owner-Regel), die Konstanten tragen den Vermerk "vorläufig". [Empfehlung; Werkzeuge VERIFIED auf GitHub-Runnern Ubuntu 24.04 mit cgroup v2: ASSUMED]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Nextcloud OCP (PHP) | NC 33 bis 35, PHP >= 8.2 | Controller, OCS, Migrationen, Listener, Notifier, QueuedJob, Folder | einzige Integrationsfläche [VERIFIED: stable33 Quelltext] |
| AppAPI `PublicFunctions` | app_api stable33 bis 35 | `exAppRequest` (mit `options`), `getExApp` | signierter Weg PHP -> Container [VERIFIED] |
| nc-py-api[app] | 0.30.3 | AppAPI-Vertrag im Container, nur Async | Skeleton-Pin [VERIFIED: pyproject.toml] |
| FastAPI | 0.162.0 | Container-HTTP (nur signiert) | Skeleton-Pin [VERIFIED] |
| httpx | 0.28.1 | Gateway-Strom mit sha256 (AVS `nc.py`) | AVS/Findling-Muster [VERIFIED] |
| PyMuPDF | 2.1 (AGPL-3.0) | Seite 1 als PNG, Platzhalter-PDF | STACK-Pin; zieht `onnxruntime`, `networkx`, `numpy`, `psutil`, `pymupdf4llm==2.1`, `pymupdf-layout==2.1`, `pyyaml`, `tabulate`; Wheels manylinux_2_28 x86_64 + aarch64 [VERIFIED: PyPI JSON heute] |
| LibreOffice | Debian trixie `libreoffice-writer-nogui` (ungepinnt, trixie-security) + Schriften `fonts-liberation2 fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea` | DOCX/ODT -> PDF für Seite 1 | STACK-Entscheid; ab Phase 1 im Image für die Größenmessung [CITED: research/STACK.md] |
| `@nextcloud/files` | 4.1.1 | `registerFileAction`, `Permission`, `FileType` | Server 33 bis 35 pinnen `^4.1.1` [VERIFIED: npm + package.json] |
| `@nextcloud/vite-config` | 2.5.4 | App-Build nach `js/*.mjs` | Peer `vite ^7.3.6` [VERIFIED: npm] |
| vite | **7.3.7** (nicht 8.x) | Bundler | vite-config verlangt 7.x [VERIFIED: npm] |
| vue | 3.5.x (Server `^3.5.44`, npm aktuell 3.5.45) | Prüfseite, Admin-Teil | [VERIFIED: npm] |
| `@nextcloud/vue` | 9.14.1 | NcAppContent, NcButton, NcNoteCard, NcLoadingIcon, NcEmptyContent | Server 35 `^9.14.1` [VERIFIED: npm] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@nextcloud/dialogs` | 8.0.0 | `showSuccess`/`showError` in der Dateiaktion | Peer von `@nextcloud/vue` 9.14.1 erlaubt `^7.4 \|\| ^8` [VERIFIED] |
| `@nextcloud/axios` / `router` / `l10n` / `initial-state` | 2.6.0 / 3.2.0 / 3.4.1 / 3.0.0 | Request-Token, URLs, `t()`/`n()`, Startzustand der Prüfseite | immer [VERIFIED: npm] |
| phpunit | 11.5.x | PHP-Tests (nur CI) | AVS `php/composer.json` [VERIFIED] |
| @playwright/test | 1.65.0 | Dateiaktion, Prüfseite, Admin, Screenshots | nur CI und Owner-Abnahme [VERIFIED: npm] |
| pytest / ruff / pyright / vulture | 9.2.0 / 0.17.3 / 1.1.414 / 2.16 | Python-Gates | Owner-Regel [VERIFIED: pyproject] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LibreOffice ab Phase 1 | Platzhalterbild für DOCX/ODT bis Phase 2/7 | Kleineres Image jetzt, aber Erfolgskriterium 2 verlangt Seite 1 für DOCX/ODT, und die Image-Größe bliebe ungemessen |
| Auftragsgebundenes Gateway | AVS-Gateway 1:1 (jede Datei jedes Nutzers) | Weniger Code, aber ein übernommener Container liest alles |
| PublishJob als QueuedJob | Ablage direkt im `ack` | Keine Cron-Abhängigkeit, aber gekoppelte Laufzeiten und Engpass bei wenigen PHP-Arbeitern |
| Vue 3 + `@nextcloud/vue` 9 | Vanilla-JS wie AVS `play.js` | Phase 1 braucht nur eine Platzhalterseite, Phase 9 aber Liste, Kästchen, Tastatur; Build ist für `@nextcloud/files` 4 ohnehin nötig |
| Seitenbild ohne Streaming mit Größendeckel | `stream => true` auch für PNG | PNG ist klein (Seite bei 110 bis 150 dpi), Puffern erlaubt Magic-Byte- und Größenprüfung vor der Antwort; Streaming nur für Ausgaben |

**Installation:**
```bash
# backend/
uv add "pymupdf==2.1"
# php/
npm install --save-exact @nextcloud/files@4.1.1 @nextcloud/vue@9.14.1 @nextcloud/dialogs@8.0.0 \
  @nextcloud/axios@2.6.0 @nextcloud/router@3.2.0 @nextcloud/l10n@3.4.1 @nextcloud/initial-state@3.0.0 vue@3.5.45
npm install --save-exact --save-dev @nextcloud/vite-config@2.5.4 vite@7.3.7
# ci/playwright/ wie AVS: @playwright/test@1.65.0
```

## Package Legitimacy Audit

slopcheck ließ sich nicht installieren (Ausführung fremden Codes vom Klassifizierer abgelehnt, wie bei AVS). Alle Pakete sind deshalb formal `[ASSUMED]`. Registerprüfung und Herkunft aus offiziellen Quellen liefen: die npm-Pakete stehen wortgleich in `nextcloud/server` `package.json` stable33 bis 35, PyMuPDF ist im Spike gemessen.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pymupdf 2.1 | PyPI | Projekt seit Jahren | nicht erhoben | github.com/pymupdf/PyMuPDF | nicht gelaufen | Approved (Spike, STACK) [ASSUMED] |
| @nextcloud/files 4.1.1 | npm | 21.10.2026, Projekt seit Jahren | nicht erhoben | github.com/nextcloud-libraries/nextcloud-files | nicht gelaufen | Approved (Server-Abhängigkeit), postinstall leer |
| @nextcloud/vue 9.14.1 | npm | 29.10.2026 | nicht erhoben | github.com/nextcloud-libraries/nextcloud-vue | nicht gelaufen | Approved, postinstall leer |
| @nextcloud/vite-config 2.5.4 | npm | 19.08.2026 | nicht erhoben | github.com/nextcloud-libraries/nextcloud-vite-config | nicht gelaufen | Approved, postinstall leer |
| vite 7.3.7 | npm | Projekt seit Jahren | nicht erhoben | github.com/vitejs/vite | nicht gelaufen | Approved, postinstall leer |
| vue 3.5.45 | npm | 05.11.2026 | nicht erhoben | github.com/vuejs/core | nicht gelaufen | Approved, postinstall leer |
| @nextcloud/dialogs 8.0.0, axios 2.6.0, router 3.2.0, l10n 3.4.1, initial-state 3.0.0 | npm | seit Jahren | nicht erhoben | github.com/nextcloud-libraries/* | nicht gelaufen | Approved (Server-Abhängigkeiten) |
| @playwright/test 1.65.0 | npm | seit Jahren | nicht erhoben | github.com/microsoft/playwright | nicht gelaufen | Approved, nur CI (AVS) |

**Packages removed due to slopcheck [SLOP] verdict:** keine
**Packages flagged as suspicious [SUS]:** keine (slopcheck nicht gelaufen). Empfehlung an den Planer: kein eigener Checkpoint je npm-Paket, weil alle aus `nextcloud/server` stammen; ein Sammel-`checkpoint:human-verify` vor dem ersten `npm install` reicht (Owner-Entscheid).

## Architecture Patterns

### System Architecture Diagram

```
Nutzer klickt "Schwärzen / Pseudonymisieren" (Dateien-App, enabled() nur Komfort)
   │ POST /apps/pii_redaction/api/v1/jobs {fileId}       Sitzung + CSRF
   ▼
PHP JobController ──actAs(uid)──► readableFile? downloadBlocked? Lockstep ok?
   │   nein ──► 4xx mit Grund aus geschlossener Liste (Toast)
   ▼ ja
oc_pii_jobs: status=queued, task=analyze, file_etag, initiator ──► Antwort {jobId, position}

Container-Runner (Semaphore 1, Wächter lässt zu, companion ok)
   │ POST OCS queue/claim (signiert) ──► PHP: bedingte UPDATE, nur ohne aktiven Lease
   ▼ {jobId, token, fileId, etag}
   │ GET OCS files/{jobId}?token ──► PHP Gateway: Token, Lease, Recheck als Auftraggeber, Etag
   │      409 bei Etag-Wechsel ──► Job stale
   ▼ Strom + X-Pii-Etag ──► work/<job>/src (sha256 im Strom)
Kindprozess (leere Umgebung, Zeitgrenze, Gruppen-Kill):
   DOCX/ODT ──soffice──► preview.pdf ──PyMuPDF──► page-1.png        PDF ──PyMuPDF──► page-1.png
   │ progress(stage, pagesDone/Total) ──► PHP (verlängert Lease)
   ▼ ack(review, pages, etagSeen) ──► PHP: Etag-Abgleich ──► status=review ──► INotifier "review_ready"

Browser: Benachrichtigung ──► GET /apps/pii_redaction/review/{jobId}   (Template + Vue)
   │ GET .../api/v1/jobs/{id}          ──► Recheck ──► Status, Stufe, Position
   │ GET .../review/{id}/page/1        ──► Recheck (Mitglied, lesbar, keine Sperre, Etag)
   │                                       ──► exAppRequest GET /jobs/{id}/pages/1.png (signiert)
   │                                       ◄── PNG (Magic + Größe geprüft), no-store
   │ POST .../review/{id}/placeholder  ──► status=approved, task=apply
Container: claim(apply) ──► Platzhalter-PDF ohne Originalinhalt ──► ack(verified, sha256, size)
PHP: QueuedJob PublishJob ──► exAppRequest GET /jobs/{id}/output (stream) ──► sha256/size
   ──► actAs(initiator): Recheck, isCreatable, getNonExistingName, newFile() ──► published
   ──► INotifier "copy_created" ──► task=purge ──► Container löscht work/<job>/

Nebenwege: NodeWrittenEvent/NodeDeletedEvent ──► stale/cancelled + purge
           Container ──GET handshake──► PHP (Companion-Version);  PHP ──/status──► Container (Lockstep)
           Browser ──/apps/app_api/proxy/pii_redaction_backend/*──► 404 (keine Routen)
```

### Recommended Project Structure
```
php/                                   # App pii_redaction (Namespace OCA\PiiRedaction)
├── appinfo/info.xml                   # Serverfenster 33..35, Lockstep-Version, Settings, Background-Jobs
├── lib/AppInfo/Application.php        # Listener (LoadAdditionalScripts, NodeWritten/Deleted), Notifier
├── lib/Controller/JobController.php   # POST /api/v1/jobs, GET /api/v1/jobs/{id}
├── lib/Controller/ReviewController.php# GET /review/{id} (Seite), /review/{id}/page/{n}, POST placeholder
├── lib/Controller/QueueController.php # OCS claim/progress/ack (ExAppRequired)
├── lib/Controller/GatewayController.php   # OCS files/{jobId} (auftragsgebunden)
├── lib/Controller/HandshakeController.php # AVS
├── lib/Controller/SettingsController.php  # AVS (Admin-Zustand)
├── lib/Service/{JobService,ExAppService,FileAccess,ReaderContext,PublishService}.php
├── lib/Db/{Job,JobMapper,JobEvent,JobEventMapper}.php, lib/Model/{Status,Reason,Stage,Task}.php (enums)
├── lib/Notification/Notifier.php
├── lib/BackgroundJob/PublishJob.php
├── lib/Listener/{LoadFilesScripts,FileLifecycle}Listener.php
├── lib/Migration/Version000100Date20261107000000.php
├── lib/Settings/{Admin,Section}.php
├── src/init.ts, src/review.ts, src/ReviewPlaceholder.vue, src/admin.ts
├── templates/review.php, admin.php
├── l10n/ (de, de_DE, en, fr)  css/ img/
├── package.json, package-lock.json, vite.config.ts, tsconfig.json
└── tests/ (phpunit, bootstrap aus AVS)
backend/                               # ExApp pii_redaction_backend
├── appinfo/info.xml                   # <routes/> leer
├── Dockerfile                         # + libreoffice-writer-nogui, Schriften
├── src/pii_redaction_backend/
│   ├── main.py, config.py, settings.py, logs.py, nc.py, companion.py
│   ├── tasks/client.py, fetch.py      # claim/progress/ack, Gateway-Strom
│   ├── runner/runner.py               # Semaphore 1, Stufen
│   ├── resources/hardware.py, memory_guard.py   # Findling-Kopie
│   ├── workers/child.py, render.py, soffice.py  # Kindprozess-Einstieg, leere Umgebung
│   ├── store/schema.sql, repo.py      # state.db, ohne Text in Phase 1
│   └── api/status.py, pages.py, output.py      # nur signiert
└── tests/
ci/ playwright/, seed.sh, make_fixtures.py, redeploy.sh, admin-state.sh, measure.sh
```

### Pattern 1: Dateiaktion
```typescript
// Quelle: nextcloud-files v4.1.1 fileAction.ts; isDownloadable aus server apps/files/src/utils/permissions.ts
import { registerFileAction, FileType, Permission, type INode } from '@nextcloud/files'
import { getCurrentUser } from '@nextcloud/auth'
import axios from '@nextcloud/axios'
import { generateUrl } from '@nextcloud/router'
import { t } from '@nextcloud/l10n'
import { showError, showSuccess } from '@nextcloud/dialogs'
import iconSvg from './icon.svg?raw'

const MIMES = new Set([
	'application/pdf',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'application/vnd.oasis.opendocument.text',
])

function downloadable(node: INode): boolean {
	if ((node.permissions & Permission.READ) === 0) return false
	if (node.attributes['hide-download'] === true || node.attributes['hide-download'] === 'true') return false
	const raw = node.attributes['share-attributes']
	if (raw) {
		const attr = (JSON.parse(raw) as Array<{ scope: string, key: string, value: unknown }>)
			.find((a) => a.scope === 'permissions' && a.key === 'download')
		if (attr !== undefined) return attr.value === true
	}
	return true
}

registerFileAction({
	id: 'pii_redaction-start',
	displayName: () => t('pii_redaction', 'Redact / pseudonymize'),
	iconSvgInline: () => iconSvg,
	order: 60,
	enabled: ({ nodes, view }) => getCurrentUser() !== null && view.id !== 'trashbin'
		&& nodes.length === 1 && nodes[0].type === FileType.File
		&& MIMES.has(nodes[0].mime ?? '') && downloadable(nodes[0]),
	exec: async ({ nodes }) => {
		try {
			const { data } = await axios.post(generateUrl('/apps/pii_redaction/api/v1/jobs'), { fileId: nodes[0].fileid })
			showSuccess(t('pii_redaction', 'Analysis started'))   // Text und Link laut UI-SPEC
			return null
		} catch (e) {
			showError(t('pii_redaction', 'The analysis could not be started'))  // Grund aus geschlossener Liste
			return null
		}
	},
})
```
`@nextcloud/auth` ist transitive Abhängigkeit von `@nextcloud/files`; als direkte Abhängigkeit exakt pinnen, falls importiert.

### Pattern 2: Claim als bedingte Aktualisierung (PHP)
```php
// Quelle: Findling QueueMapper::claimBatch, auf eine Zeile und "kein aktiver Lease" reduziert
$now = time();
$token = bin2hex(random_bytes(16));
$qb = $this->db->getQueryBuilder();
$qb->update('pii_jobs')
	->set('claim_token', $qb->createNamedParameter($token))
	->set('lease_until', $qb->createNamedParameter($now + $lease, IQueryBuilder::PARAM_INT))
	->set('attempts', $qb->createFunction('attempts + 1'))
	->set('status', $qb->createNamedParameter(Status::Analyzing->value))
	->where($qb->expr()->eq('id', $qb->createNamedParameter($candidateId, IQueryBuilder::PARAM_INT)))
	->andWhere($this->freeCondition($qb, $now));   // queued ODER Lease abgelaufen
// "Ein Auftrag zur Zeit": vorher in derselben Transaktion prüfen, dass keine andere
// analyze/apply-Zeile lease_until > now hat; Gewinner ist, wessen Token zurückgelesen wird.
```
Die Ein-Auftrag-Regel als `NOT EXISTS`-Teilabfrage auf dieselbe Tabelle ist in MySQL nicht erlaubt (Update mit Selbstbezug); deshalb Transaktion mit vorheriger Zählung und Token-Rücklesen, oder eine Sperrzeile in `oc_appconfig`. In CI zusätzlich ein MariaDB-Bein erwägen (Offene Frage 5). [ASSUMED: MySQL-Einschränkung aus Fachwissen, bekannte Fehlermeldung 1093]

### Pattern 3: Seitenbild mit Recheck (PHP)
```php
#[NoAdminRequired]
#[NoCSRFRequired]   // GET, rein lesend, Bild; Sitzung genügt
#[FrontpageRoute(verb: 'GET', url: '/review/{jobId}/page/{n}', requirements: ['jobId' => '\d+', 'n' => '\d{1,3}'])]
public function page(int $jobId, int $n): Response {
	$job = $this->jobs->forMember($jobId, $this->uid);          // null -> 404 ohne Namen
	$check = $this->files->recheck($job, $this->uid);           // lesbar, keine Sperre, Etag
	if ($check !== Recheck::Ok) { return $this->denied($check); }   // 404 / 403 / 409
	$png = $this->exApp->page($job, $n);                        // timeout 10 s, Deckel 16 MiB, PNG-Magic
	if ($png === null) { return new DataResponse([], Http::STATUS_BAD_GATEWAY); }
	$r = new DataDisplayResponse($png, Http::STATUS_OK, ['Content-Type' => 'image/png']);
	$r->addHeader('Cache-Control', 'private, no-store');
	$r->addHeader('X-Content-Type-Options', 'nosniff');
	return $r;
}
```

### Pattern 4: Kindprozess ohne Geheimnis (Python, Vorform Phase 2)
```python
# Quelle: Entwurf nach research/ARCHITECTURE.md Pattern 5; Phase 2 ergänzt rlimits und Korpus
SAFE_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8", "OMP_THREAD_LIMIT": "1"}

async def run_child(args: list[str], *, timeout_s: float) -> int:
    proc = await asyncio.create_subprocess_exec(
        *args, env=SAFE_ENV, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True)
    try:
        return await asyncio.wait_for(proc.wait(), timeout_s)
    except TimeoutError:
        os.killpg(proc.pid, signal.SIGKILL)   # ganze Gruppe, auch soffice.bin
        await proc.wait()
        raise
```
Test: Kind liest `os.environ` und meldet, ob `APP_SECRET`, `AA_VERSION`, `NEXTCLOUD_URL` oder `APP_ID` sichtbar sind -> muss leer sein. soffice je Aufruf mit `-env:UserInstallation=file:///tmp/lo-<job>` und `--headless --norestore --nolockcheck --nodefault --nologo --convert-to pdf`.

### Anti-Patterns to Avoid
- **USER- oder ADMIN-Routen im Container** (AVS hatte `^/search$` USER): jede angemeldete Person erreicht sie über den Proxy.
- **Gateway ohne Auftragsbindung:** übernommener Container liest jede Datei.
- **Dateiname/Pfad/Mime in `oc_pii_*`, Benachrichtigung oder Log.**
- **Ausnahmetext in Logs:** PyMuPDF- und LibreOffice-Meldungen tragen Pfade und Textstücke.
- **Platzhalter-Kopie aus dem Original** (z. B. Seite 1 kopiert): erzeugt eine ungeschwärzte Datei mit Schwärzungs-Suffix.
- **Rendering im FastAPI-Prozess:** MuPDF-Absturz nimmt Status und Warteschlange mit.
- **`@nextcloud/files` 3.x** oder globale Objekte: wird in NC 33+ nicht gefunden.
- **Ablage im `ack`-Request** (siehe Entscheid 8).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Signierter Aufruf PHP -> Container | eigener HTTP-Client | `PublicFunctions::exAppRequest` mit `options['timeout']`, `options['stream']` | Signatur, HaRP, Fehlerbehandlung |
| Gegen-App-Zustände, Lockstep, Handshake | neue Logik | AVS `ExAppService`, `HandshakeController`, `companion.py` | in CI auf 6 Beinen grün |
| Gruppenordner-ACL beim Recheck | eigene ACL-Logik | AVS/Findling `ReaderContext::actAs` + `FileAccess::readableFile` | `in_share`-Falle |
| Download-Sperre | eigene Freigabe-Abfrage per SQL | `ISharedStorage::getShare()->getAttributes()` | öffentliche API seit 30 |
| Claim mit Lease | Zeilensperren je Dialekt | Findling bedingte `UPDATE` + Token | dialektfrei, getestet |
| RAM-Kopfraum | `psutil.virtual_memory()` | Findling `memory_guard.headroom_bytes` | cgroup-Grenze statt Host-RAM |
| Dateiname ohne Kollision | eigenes Zählen | `Folder::getNonExistingName` | Nextcloud-Regeln, Sperren |
| Bild-Auslieferung | `echo` + `header()` | `DataDisplayResponse` / `StreamResponse` | CSP, Header, Tests |
| Lockstep-Gates, Store-Archiv, Signatur, Secret-Scan | neue Skripte | AVS `test_lockstep_versions.py`, `store-archive.sh`, `release.yml`, `test_public_artifacts.py` | erprobt |
| App-Build | eigene Vite-Konfiguration | `@nextcloud/vite-config` `createAppConfig` | Ausgabepfade, CSS, Lizenzdateien |

**Key insight:** Neu und eigen sind nur Dateiaktion, Auftragsmodell, Queue-Routen, Seitenbild-Proxy, PublishJob und Kindprozess-Runner. Alles andere ist AVS- oder Findling-Code mit neuer ID.

## Runtime State Inventory

Phase 1 benennt die bestehende ExApp-ID `pii_redaction` in `pii_redaction_backend` um und gibt `pii_redaction` an die PHP-App.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Keine bekannte Installation mit Daten; CI-Instanzen sind Wegwerf. Ob auf budachst oder lokal eine ExApp `pii_redaction` registriert ist, ist nicht geprüft [ASSUMED: nein] | Owner fragen; falls ja: `occ app_api:app:unregister pii_redaction --rm-data` vor der ersten PHP-App-Installation (gleiche ID) |
| Live service config | App-Store: Zertifikat `pii_redaction` (#1411) gilt jetzt für die PHP-App; `pii_redaction_backend` #1419 offen | nichts in Phase 1; Store-Registrierung Phase 15 |
| OS-registered state | Keine (keine Tasks, Dienste) [VERIFIED: nichts im Repo] | keine |
| Secrets/env vars | GitHub-Secrets `APP_PRIVATE_KEY` (Schlüssel `pii_redaction` = jetzt PHP-App) und `APPSTORE_TOKEN` vorhanden, `BACKEND_PRIVATE_KEY` fehlt [VERIFIED: gh secret list]; `release.yml` `APP_ID: pii_redaction`, Pin `4f61842e...`; Umgebungsvariable `PII_REDACTION_LOG_LEVEL` in `info.xml` | Secret `BACKEND_PRIVATE_KEY` nach #1419 (Owner); zweite Pin (`7a8c64ae...` gegenprüfen); Präfix der Backend-Variablen festlegen (Empfehlung `PII_REDACTION_` behalten, kollidiert nicht) |
| Build artifacts | `docker.yml` pushte bisher `ghcr.io/street1983nk/pii_redaction` (Paketliste ohne `read:packages` nicht abrufbar); lokales `.venv` mit Paket `pii_redaction`, `__pycache__`, `uv.lock` mit Projektname `pii_redaction` | neues Image `pii_redaction_backend`; altes ghcr-Paket später löschen oder privat stellen (Owner); `uv lock` + `uv sync` nach Umbenennung; `__pycache__` löschen |

## Common Pitfalls

### Aus AVS Phase 1 gelöst (nicht wiederholen)
1. **Verlorene Backslashes beim Umbenennen** in `composer.json` (`"OCA\\PiiRedaction\\"`) und `php/tests/bootstrap.php` (`rtrim($serverRoot, '/\\')`): `php -l` und `composer validate` werden rot. AVS-Regel 9 in `test_php_gates.py` mitkopieren. [VERIFIED: AVS cb7373e]
2. **phpunit-Helfer überschreibt finale Methode** (`status()`): AVS-Regel 10. [VERIFIED: 4795ccc]
3. **412 vor der Aktivierung** beim Handshake ist kein Fehler; `/status` und Prüfschleife fragen bei `unknown` sofort nach. [VERIFIED: 7e423e1]
4. **`[hidden]` verliert gegen Server-CSS** (`button:not(...) > span[class^=icon-] { display: block }`): jede `[hidden]`-Regel an eine ID hängen, kein `!important`; AVS-Regel 11 + Playwright-Prüfung. Gilt auch für Vue-Komponenten mit `v-show` nicht, aber für eigenes CSS. [VERIFIED: 3538d3c]
5. **Playwright wie ein Mensch:** Schalter über das Label klicken (Checkbox außer Sicht), auf sichtbare Auslöser warten (Button oder Combobox je NC-Version), abgelaufene Sitzung erst `about:blank`, dann Cookies löschen. [VERIFIED: 229dbd6]
6. **Listennamen unterscheiden sich je NC-Version** (33/34 vs. 35 "More from ..."): Elemente über Rollen in einem benannten Container suchen, nicht über Freitext; für die Dateien-App die stabilen Attribute `data-cy-files-list-row-name`, `data-cy-files-list-row-fileid`, `data-cy-files-list-row-action="<id>"` (auf stable33 und stable35 heute gelesen). [VERIFIED: e91715b, FileEntry.vue]
7. **Upgrade-Job: `viewer` fehlt im Server-Checkout**, ist laut `core/shipped.json` aber immer aktiv; `occ upgrade` bricht auf 33/34 mit "files of the app viewer were not correctly replaced". `nextcloud/viewer` im passenden Zweig auschecken wie ein Release-Tarball. [VERIFIED: cd44ea6, 05d636d]
8. **Drift-Schritte brauchen `INFO_XML`**, `ci/redeploy.sh` bricht sonst ab; Gate "jede Pflichtvariable des Skripts ist im Workflow gesetzt". [VERIFIED: 05d636d]
9. **`occ upgrade` Exit 0 oder 3**; maßgeblich ist, dass `installed_version` springt. **`app_api:app:update` behält das Volume** (HaRP löscht nur bei `remove_data`); Beweis über Inode von `state.db` und `CreatedAt` des Volumes. [VERIFIED: 01-10-SUMMARY]
10. **Routen-URLs sind Regex** (`^/<name>$`), HaRP nutzt `re.match` mit führendem Schrägstrich. Hier entfällt das, weil keine Routen deklariert werden. [VERIFIED: Skeleton-Kommentar]
11. **PHP-Archiv zusätzlich mit `occ integrity:sign-app`** signieren (`signature.json`), Backend-Pin `pending-certificate`. [VERIFIED: 01-10-SUMMARY]
12. **Logs ohne Testdateinamen** als CI-Schritt; hier erweitert zur Kanarie mit Positivkontrolle. [VERIFIED: AVS deploy-harp "No test file name ..."]
13. **Frühe Pushes auf `phase-01`** (nie `main`, jeder Push mit Owner-Freigabe): PHP-Fehler fielen erst in CI auf. [VERIFIED: 01-12-SUMMARY]

### Neu für PII Redaction

### Pitfall A: Notifications-App und Gruppenordner fehlen in der CI-Instanz
**What goes wrong:** Benachrichtigungen lassen sich nicht prüfen, ACL-Tests laufen ins Leere.
**Why it happens:** `nextcloud/server` enthält weder `notifications` noch `groupfolders`.
**How to avoid:** `nextcloud/notifications` Zweig `stable3x` auschecken; groupfolders wie AVS `seed.sh` (Store, sonst Release-Tarball), ACL mit `occ groupfolders:permissions <id> --enable` und `occ groupfolders:permissions <id> --user carol <pfad> -- -read`. [CITED: groupfolders README]
**Warning signs:** OCS `/apps/notifications/api/v2/notifications` 404.

### Pitfall B: Zu wenige PHP-Arbeiter in CI
**What goes wrong:** Container-Polling, Gateway-Strom, Browser und Proxy-Aufrufe stauen sich; Timeouts sehen wie Produktfehler aus.
**How to avoid:** `NEXTCLOUD_WORKERS=8 composer run serve`; Polling-Intervall des Containers mit Rückoff (1 s nach Arbeit, bis 10 s im Leerlauf).

### Pitfall C: Standard-Timeout von `exAppRequest` ist 3 s
**What goes wrong:** Seitenbild oder Ausgabe bricht ab, PHP meldet "nicht erreichbar".
**How to avoid:** Timeout je Aufruf (`status` 1,5 s, Seite 10 s, Ausgabe 120 s), alles in `ExAppService`. [VERIFIED: AppAPIService.php Z. 186]

### Pitfall D: Leere Routenliste und Update
**What goes wrong:** Nach einem Update ohne `<routes>` bleiben alte Routen aktiv.
**How to avoid:** Leeres `<routes/>` und Negativprüfung nach dem Upgrade-Job (Entscheid 9). Vorher prüfen, dass `pre-info.xslt` und das Store-Schema ein leeres Element akzeptieren; sonst Element nur im Archiv (das AppAPI liest) und nicht im Store-Upload. [ASSUMED]

### Pitfall E: Vite 8 statt 7
**What goes wrong:** `npm install vite` zieht 8.3.6, `@nextcloud/vite-config` verlangt `^7.3.6`, Peer-Konflikt oder stiller Bruch.
**How to avoid:** `vite@7.3.7` exakt, Dependabot-Regel "major von vite ignorieren", bis vite-config 3.x erscheint.

### Pitfall F: Dateiaktion erscheint auf öffentlichen Freigabeseiten oder im Papierkorb
**How to avoid:** `getCurrentUser() !== null`, `view.id !== 'trashbin'`; Server lehnt ohnehin ab.

### Pitfall G: Etag-Vergleich als falscher Alarm
**What goes wrong:** Externe Speicher oder Scans ändern den Etag ohne Inhaltsänderung.
**How to avoid:** fail-safe akzeptieren (lieber neu analysieren), in Doku und Meldung "Datei wurde geändert oder neu eingelesen".

### Pitfall H: Ausnahmen tragen Inhalt in Logs
**What goes wrong:** `logging.exception`, uvicorn-Fehlerseite oder PHP-Ausnahmen mit Bibliotheksnachricht schreiben Pfade oder Textstücke.
**How to avoid:** Entscheid 10; Kanarien-Scan mit Positivkontrolle.

### Pitfall I: Kanarie wird durch die Prüfung selbst nicht gefunden
**What goes wrong:** Der Scan ist grün, weil er nie hätte treffen können (komprimierter Strom, falscher Pfad).
**How to avoid:** Positivkontrolle auf die Originaldatei im Datenordner im selben Schritt; Kanarie in der PDF unkomprimiert.

### Pitfall J: Seitenbild aus dem Browser-Cache
**How to avoid:** `Cache-Control: private, no-store` auf jeder Bild- und Statusantwort; Playwright prüft den Header.

### Pitfall K: Doppelter Start derselben Datei
**How to avoid:** Offener Auftrag mit gleicher `file_id` + Etag + Auftraggeber wird zurückgegeben, nicht neu angelegt (eindeutiger Teilindex ist in Nextcloud-Migrationen nicht portabel, also Prüfung im Service in einer Transaktion).

## Code Examples

### Download-Sperre (PHP)
```php
// Quelle: server stable33 apps/files_sharing/lib/ViewOnly.php::checkFileInfo, über OCP\Files\Storage\ISharedStorage
public static function downloadBlocked(\OCP\Files\Node $node): bool {
	$storage = $node->getStorage();
	if (!$storage->instanceOfStorage(\OCP\Files\Storage\ISharedStorage::class)) {
		return false;
	}
	/** @var \OCP\Files\Storage\ISharedStorage $storage */
	$share = $storage->getShare();
	if ($share->getHideDownload()) {
		return true;
	}
	return $share->getAttributes()?->getAttribute('permissions', 'download') === false;
}
```

### Ausgabe holen und ablegen (PHP)
```php
// Quelle: app_api stable33 AppAPIService::prepareRequestToExApp (options), server Client::get (stream)
$res = $this->publicFunctions->exAppRequest(
	Application::BACKEND_APP_ID, '/jobs/' . $jobId . '/output', $uid, 'GET', [],
	['stream' => true, 'timeout' => 120],
);
if (is_array($res) || $res->getStatusCode() !== 200) { return Outcome::BackendFailed; }
$in = $res->getBody();                        // Ressource
$tmp = fopen('php://temp/maxmemory:8388608', 'w+b');
$ctx = hash_init('sha256'); $size = 0;
while (!feof($in)) {
	$chunk = fread($in, 65536);
	if ($chunk === false) { break; }
	$size += strlen($chunk);
	if ($size > self::MAX_OUTPUT_BYTES) { return Outcome::TooLarge; }
	hash_update($ctx, $chunk); fwrite($tmp, $chunk);
}
if (!hash_equals($job->expectedSha256, hash_final($ctx)) || $size !== $job->expectedSize) { return Outcome::Mismatch; }
rewind($tmp);
return $this->readerContext->actAs($uid, function () use ($uid, $job, $tmp) {
	$file = FileAccess::readableFile($this->rootFolder->getUserFolder($uid), $job->getFileId());
	if ($file === null || $file->getEtag() !== $job->getFileEtag()) { return Outcome::Stale; }
	$parent = $file->getParent();
	if (!$parent->isCreatable()) { return Outcome::NotWritable; }
	$name = $parent->getNonExistingName(Suffix::outputName($file->getName(), $this->lang($uid)));
	return Outcome::published($parent->newFile($name, $tmp)->getId());
});
```

### Gateway-Strom mit Etag (Python)
```python
# Quelle: AVS nc.py _hash_stream, erweitert um Auftrag, Token und Etag
async with client.stream("GET", gateway_url(job.job_id), params={"token": job.token},
                         headers=app_api_headers(job.user_id)) as resp:
    if resp.status_code == 409:
        return FetchResult.stale()
    if resp.status_code != 200:
        return FetchResult.failed(resp.status_code)
    etag = resp.headers.get("X-Pii-Etag", "")
    digest, size = hashlib.sha256(), 0
    with target.open("wb") as out:
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                return FetchResult.failed(413)
            digest.update(chunk)
            out.write(chunk)
return FetchResult.ok(digest.hexdigest(), size, etag)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@nextcloud/files` 3.x, `new FileAction(...)` | 4.x `registerFileAction({...})` mit Kontextobjekt, Ablage `_nc_files_scope.v4_0` | 4.0.0 (NC 33+) | v3-Code wird nicht gefunden |
| Webpack-Builds der Apps | Vite über `@nextcloud/vite-config`, `.mjs` | NC 28 ff. | `JSResourceLocator` lädt `.mjs` zuerst |
| `InvalidArgumentException` im Notifier | `UnknownNotificationException` | NC 30 | Notifier für 33 bis 35 nur neu |
| AppAPI-Dateiereignisse | PHP-Listener in eigener App | app_api stable32 | Zwei-App-Muster |
| nc_py_api Sync-API | nur Async | entfällt in 0.31.0 | Skeleton-Regel |

**Deprecated/outdated:**
- `exAppRequestWithUserInit` (seit AppAPI 3.0.0): nur `exAppRequest` nutzen. [VERIFIED: PublicFunctions.php]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Knotenattribut `is-encrypted` kennzeichnet E2EE-Ordner in der Dateien-App | Entscheid 2 | Aktion erscheint in E2EE-Ordnern; Server lehnt ohnehin ab (Phase 2) |
| A2 | Push-Weg der Notifications-App überträgt den Betreff (verschlüsselt) | Entscheid 7 | Dateiname im Text wäre harmloser als angenommen; Empfehlung bleibt sicher |
| A3 | `occ background-job:execute --force-execute` existiert auf 33 bis 35 | Entscheid 8 | CI nutzt `php cron.php`-Schleife |
| A4 | Leeres `<routes/>` überschreibt Routen auch beim `app_api:app:update` und wird vom Store-XSLT/Schema akzeptiert | Entscheid 9, Pitfall D | Alte Route bleibt nach Update aktiv; Negativtest im Upgrade-Job fängt es |
| A5 | MySQL verbietet Selbstbezug in `UPDATE ... WHERE NOT EXISTS (SELECT ... gleiche Tabelle)` | Pattern 2 | Andere Claim-Form nötig; nur relevant mit MariaDB-Bein |
| A6 | Etag externer Speicher wechselt ohne Inhaltsänderung | Entscheid 6 | Nur Doku-Satz betroffen |
| A7 | GitHub-Runner Ubuntu 24.04 haben cgroup v2 mit `memory.peak` | Entscheid 12 | Messung fällt auf `docker stats` zurück |
| A8 | Keine ExApp `pii_redaction` auf budachst/lokal registriert | Runtime State | ID-Kollision bei PHP-Installation |
| A9 | Tabellen-/Indexnamen-Längengrenze von Nextcloud-Migrationen | Entscheid 3 | Migration scheitert in CI, Namen kürzen |
| A10 | LibreOffice-nogui + Schriften bleiben unter ca. 550 MB zusätzlich | Entscheid 12 | Image größer; Messung in Phase 1 entscheidet, Alternativen in STACK |

## Open Questions

1. **LibreOffice schon in Phase 1?**
   - What we know: Erfolgskriterium 2 verlangt Seite 1 für DOCX/ODT; Image-Größe ist ungemessen.
   - Recommendation: ja (Entscheid 12), Härtung in Phase 2. Owner bestätigt, weil Phase 1 damit fremde Office-Dateien vor der vollen Sandbox konvertiert (nur Testinstanzen, kein Store-Release vor Phase 15).
2. **Dateiname in Benachrichtigungen?** Empfehlung: nein, nur "Eine Prüfung ist bereit" mit Link; Name auf der Prüfseite. Owner entscheidet.
3. **Suffix der Platzhalter-Kopie:** echter Suffix (`_geschwärzt` usw., Inhalt ist nur ein Hinweis) oder `_platzhalter`? Empfehlung: echter Suffix, damit die Suffix-Logik ab Phase 1 im echten Weg läuft.
4. **Startet der Platzhalter-Weg ohne Debug-Schalter?** AVS sperrte die Saat hinter `debug`. Empfehlung: Dateiaktion und Platzhalter-Kopie ohne Debug-Schalter (sie sind der spätere Produktweg), aber der Knopf "Platzhalter-Kopie anlegen" nur, solange es keine echte Freigabe gibt (wird in Phase 10 ersetzt).
5. **MariaDB-Bein in `deploy-harp.yml`?** Claim-Logik und Migrationen sind dialektabhängig. Empfehlung: ein zusätzliches Bein stable35/amd64 mit MariaDB-Dienstcontainer, sonst erst in Phase 15.
6. **de_DE (Sie-Form) zusätzlich zu de?** AVS liefert beide. Empfehlung: ja, Behörden nutzen oft `de_DE`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | Python-Gates | ✓ | 0.11.7 | - |
| Python | Backend-Tests | ✓ | 3.13.1 | - |
| Node / npm | Vite-Build, Playwright-Liste | ✓ | 22.21.0 / 11.14.1 | - |
| gh | CI-Läufe, PR-Status #1419 | ✓ | 2.92.0 | - |
| Docker | Image-Build | ✓ | 29.5.2 | lokal nicht starten (RAM knapp, Owner-Regel seriell), Builds in CI |
| PHP / Composer | phpunit, `php -l` | ✗ | - | nur CI (`php.yml`), wie AVS |
| LibreOffice (`soffice`) | Konvertierung | ✗ lokal | - | nur im Container/CI |
| Nextcloud-Testinstanz | Integration | ✗ lokal | - | CI `deploy-harp.yml` (33/34/35 x amd64/arm64) |

**Missing dependencies with no fallback:** keine.
**Missing dependencies with fallback:** PHP, LibreOffice, Nextcloud: alles in CI.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.2.0 (backend), phpunit 11.5 (php, CI), Playwright 1.65.0 (CI, `ci/playwright/`), GitHub Actions mit HaRP |
| Config file | `backend/pyproject.toml` (aus der Wurzel verschoben), `php/phpunit.xml` (Wave 0, AVS-Kopie), `ci/playwright/playwright.config.ts` (AVS-Kopie) |
| Quick run command | `cd backend && uv run pytest -q -x` |
| Full suite command | `cd backend && uv run ruff check . && uv run ruff format --check . && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright && uv run vulture && uv run pytest -q`; dazu `cd php && npm ci && npm run build` lokal; PHP, Integration, Playwright in CI |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-01 | Drei Versionswerte + pyproject + Serverfenster + Matrix gleich | unit | `uv run pytest tests/test_lockstep_versions.py -x` | ❌ W0 (AVS-Kopie) |
| PLAT-01 | Upgrade 0.0.1 -> 0.1.0 beider Apps, Volume/Inode/Aufträge bleiben, Routen weiter 404 | integration | `deploy-harp.yml` Job `upgrade` | ❌ W0 |
| PLAT-01 | Zwei Store-Archive, `js/pii_redaction-init.mjs` im PHP-Archiv, zwei Pins | unit | `uv run pytest tests/test_release_archives.py -x` | ❌ W0 |
| PLAT-02 | Sieben Zustände + Patch-Hinweis; `POST /jobs` verweigert bei Drift/fehlend | unit (php) | `composer run test -- --filter BackendStateTest` | ❌ W0 |
| PLAT-02 | Drift 1 bis 4 im echten Lauf, Admin-Bereich zeigt Zustand | integration + e2e | `deploy-harp.yml` Drift-Schritte, Playwright `@drift @patch @missing` | ❌ W0 |
| PLAT-02 | Container `companion: missing` stoppt Claims | unit | `uv run pytest tests/test_companion.py -x` | ❌ W0 |
| PLAT-03 | Matrix 33/34/35 x amd64/arm64 vollständig | unit | `uv run pytest tests/test_workflows.py -x` | ✅ erweitern |
| PLAT-03 | Installation + Kernweg auf 6 Beinen | integration | `deploy-harp.yml` | ✅ teilweise (3 Beine, nur ExApp) |
| PLAT-05 | `info.xml` ohne Route, `<routes/>` vorhanden | unit | `uv run pytest tests/test_store_metadata.py -x` | ✅ erweitern |
| PLAT-05 | Proxy als Nutzer/Admin -> 404, unsigniert über HaRP -> nicht 200 | integration | `deploy-harp.yml` Schritt "No browser route" | ❌ W0 |
| PLAT-05 | Jede Prüfseiten-Route ruft Recheck (statisches Gate), nur `ExAppService` ruft den Container | unit | `uv run pytest tests/test_php_gates.py -x` | ❌ W0 (AVS-Kopie + neue Regeln) |
| JOB-01 | `enabled()` für PDF/DOCX/ODT ja, für TXT/Ordner/Mehrfachauswahl/Papierkorb/Download-Sperre nein | unit (TS) oder e2e | Playwright `fileaction.spec.ts` (TS-Unit optional mit vitest) | ❌ W0 |
| JOB-01 | Klick legt Auftrag an, Toast, idempotent bei zweitem Klick | e2e + unit (php) | Playwright, `--filter JobControllerTest` | ❌ W0 |
| JOB-02 | Fortschritt/Position/Status nur aus geschlossener Liste, Container-Werte außerhalb abgewiesen | unit (php) | `--filter QueueControllerTest` | ❌ W0 |
| JOB-02 | Benachrichtigung `review_ready` ohne Dateiname/Fund, Link auf Prüfseite, DE/EN/FR | unit (php) + integration | `--filter NotifierTest`; OCS `notifications/api/v2` in CI | ❌ W0 |
| JOB-02 | Platzhalter-Prüfseite zeigt Seite 1 (PDF, DOCX, ODT), Screenshots 375/768/1280 hell/dunkel/Hochkontrast | e2e | Playwright `review.spec.ts` | ❌ W0 |
| JOB-02 | Platzhalter-Kopie neben dem Original, Name per `getNonExistingName`, Inhalt ohne Kanarie | integration | `deploy-harp.yml` + WebDAV-Abruf, grep Kanarie = 0 in der Kopie | ❌ W0 |
| JOB-03 | Nutzer ohne Leserecht (fremd, ACL `-read` im Gruppenordner, entzogene Freigabe) kann weder starten noch Seite/Bild öffnen; Download-Sperre blockiert Start | integration + unit | `deploy-harp.yml` Rechte-Schritt (curl je Nutzer), `--filter FileAccessTest` | ❌ W0 |
| JOB-03 | Gateway nur mit gültigem Token, nur Auftragsdatei, fremde `EX-APP-ID` 403 | unit (php) | `--filter GatewayControllerTest` | ❌ W0 |
| JOB-04 | Etag-Wechsel nach `review` -> Seite "geändert", Bild 409, Status `stale`; Gateway/`ack` mit falschem Etag | integration + unit | `deploy-harp.yml` Stale-Schritt, `--filter EtagBindingTest` | ❌ W0 |
| JOB-06 | Zwei Aufträge: nie zwei aktive Leases; Lease-Ablauf gibt frei; 3 Ausgaben -> `repeatedly_stuck` | unit (php) + integration | `--filter QueueMapperTest`; CI startet zwei Aufträge und protokolliert Status | ❌ W0 |
| JOB-06 | Wächter lässt nicht zu, wenn Kopfraum unlesbar oder zu klein; Semaphore 1 | unit | `uv run pytest tests/test_memory_guard.py tests/test_runner.py -x` | ❌ W0 |
| (Krit. 5) | Kanarie mit Positivkontrolle: nicht in NC-DB, nextcloud.log, PHP-, Container-, HaRP-, nginx-Log, `state.db` | integration | `deploy-harp.yml` Schritt "Canary" | ❌ W0 |
| (Krit. 5) | Log-Gates: Allowlist, keine Tracebacks, keine f-Strings; PHP-Logkontext-Allowlist | unit | `uv run pytest tests/test_logs.py tests/test_log_calls.py tests/test_php_gates.py -x` | ✅ test_logs erweitern, Rest ❌ W0 |
| (Krit. 5) | Migrationen ohne Klartextspalten (keine Spalten wie name, path, text, value, snippet, title, comment) | unit | `uv run pytest tests/test_php_gates.py -x` (Regel "migration columns") | ❌ W0 |
| (Sandbox-Vorform) | Kindprozess sieht kein AppAPI-Geheimnis, Zeitgrenze tötet Gruppe | unit | `uv run pytest tests/test_child.py -x` | ❌ W0 |
| (Sprache) | DE/EN/FR (+ de_DE) im Gleichstand, U+00A0 in FR, keine U+2013/U+2014, keine Emojis, auch in `php/l10n` und `php/src` | unit | `uv run pytest tests/test_trilingual.py tests/test_public_texts.py -x` | ✅ erweitern |
| (Messung) | Messwerte-JSON je Bein vorhanden, nur Zahlen | integration | `deploy-harp.yml` Schritt "Measure", `docker.yml` Image-Größe | ❌ W0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest -q -x`
- **Per wave merge:** volle Python-Gates lokal, `npm run build` lokal, dann Push auf `phase-01` nur nach Owner-Freigabe: `python.yml`, `php.yml`, `docker.yml`, `deploy-harp.yml`
- **Phase gate:** alles grün auf 6 Beinen + 4 Upgrade-Beinen, Messwerte-Artefakte vorhanden, danach gemeinsame Playwright-Abnahme mit dem Owner (375/768/1280, hell/dunkel), dann `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Repo-Umbau `backend/` + `php/`, Pfade in Workflows, Dependabot (pip + npm), `.dockerignore`, Tests
- [ ] `php/composer.json`, `php/phpunit.xml`, `php/tests/bootstrap.php` (AVS-Kopie, Backslash-Regel)
- [ ] `php/package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`; `php/js/` in `.gitignore`
- [ ] `backend/tests/test_lockstep_versions.py`, `test_php_gates.py` (Regeln 1 bis 11 + Recheck-Regel, Migrationsspalten, Logkontext), `test_release_archives.py`, `test_log_calls.py`, `test_child.py`
- [ ] `ci/make_fixtures.py` (PDF/DOCX/ODT mit Kanarie, stdlib), `ci/seed.sh` (Nutzer alice/bob/carol/dora, Gruppenordner mit ACL, Freigabe mit Download-Sperre, Fixtures), `ci/playwright/` (AVS-Gerüst + `fileaction.spec.ts`, `review.spec.ts`, `admin.spec.ts`), `ci/measure.sh`
- [ ] `deploy-harp.yml`: 6 Beine, Checkout `notifications` und `viewer`, `NEXTCLOUD_WORKERS=8`, Node-Build vor PHP-App, Rechte-, Stale-, Routen-, Kanarien-, Mess-Schritte, Hintergrundjob-Anstoß

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | ja (indirekt) | Nextcloud-Sitzung für Browser; Container nur über signiertes AppAPI; OCS-Routen `#[ExAppRequired]` + `EX-APP-ID`-Vergleich |
| V3 Session Management | ja | Nextcloud; POST mit Request-Token (`@nextcloud/axios`); GET-Bild ohne CSRF ist rein lesend |
| V4 Access Control | ja | Recheck je Anfrage (`actAs` + `readableFile` + Download-Sperre + Etag + Mitgliedschaft); auftragsgebundenes Gateway mit Token |
| V5 Input Validation | ja | Routen-Requirements `\d+`; Status/Grund/Stufe nur aus Enums; Größen- und Magic-Prüfung der PNG/Ausgabe; sha256-Abgleich |
| V6 Cryptography | ja (Hash, Token) | `random_bytes(16)` für Claim-Token, `hash_equals`, `hashlib.sha256`; nichts selbst gebaut |
| V7 Error Handling and Logging | ja | Logging-Allowlist, keine Ausnahmetexte, Kanarien-Scan mit Positivkontrolle |
| V8 Data Protection | ja | kein Klartext/Dateiname in `oc_pii_*`, `Cache-Control: no-store`, Platzhalter ohne Originalinhalt |
| V12 Files and Resources | ja | Kindprozess ohne Geheimnis, Zeitgrenze, Gruppen-Kill; Magic-Bytes statt Endung (Grundform) |
| V14 Configuration | ja | keine Container-Routen, CSP Standard, keine Inline-Skripte |

### Known Threat Patterns for PHP-App + ExApp

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR über `review/{jobId}` oder Seitenbild | Information Disclosure | Mitgliedschaft + Recheck je Anfrage; 404 ohne Namen |
| Entzogenes Recht wirkt weiter (ACL, Freigabe) | Elevation of Privilege | Recheck je Anfrage statt gespeicherter Rechte |
| Geschwärzte Kopie umgeht Download-Sperre | Information Disclosure | Start und Recheck lehnen `download_blocked` ab |
| Fremde ExApp nutzt Gateway/Queue | Spoofing | `#[ExAppRequired]` + `EX-APP-ID == pii_redaction_backend` |
| Übernommener Container zieht fremde Dateien | Elevation of Privilege | Gateway nur für geleasten Auftrag, Token, Auftraggeber, Etag |
| Browser erreicht Container direkt | Elevation of Privilege | keine Routen, 404 im Proxy; Test |
| Manipulierte Container-Antwort (Status, Größe, Bild) | Tampering | Enums, Größendeckel, PNG-Magic, sha256 gegen `ack` |
| Fund-/Dateiname in Logs, DB, Benachrichtigung | Information Disclosure | Allowlist, Gates, Kanarien-Scan |
| Bösartiges DOCX/PDF beim Rendern | Tampering/EoP | Kindprozess ohne Geheimnis, Zeitgrenze, Nicht-Root (uid 10001); volle Härtung Phase 2 |
| XSS über Dateinamen auf der Prüfseite | Tampering | Vue-Textbindung, kein `v-html`, Template nur `p()` |

## Project Constraints (from CLAUDE.md)

- Kein Dokumentinhalt, kein Fund, keine Telemetrie verlässt den Server.
- Bestes Ergebnis für den Nutzer, Aufwand ist kein Grund; Qualitätsentscheide belegen.
- Python-ExApp aus dem Skeleton (FastAPI 0.162.0, nc-py-api 0.30.3, nur Async).
- NC 33 bis 35, AppAPI mit HaRP, amd64 + arm64, nur CPU.
- RAM-Wächter, nie zwei Aufträge parallel auf kleinen Servern.
- AGPL-3.0-or-later; Testkorpora nicht ins Repo (Phase-1-Fixtures sind synthetisch und klein, per Skript erzeugt).
- Texte DE/EN/FR im Gleichstand, Deutsch zuerst, echte Umlaute nur in Prosa, keine Gedankenstriche, keine Emojis.
- Gates: ruff-Vollsatz, ruff format, pyright basic, vulture lokal grün.
- Commits nur als street1983nk <k.cherif@outlook.de>, ohne Claude-Session-Zeilen, ohne "closes #N".
- Vor jedem Push, Merge oder Kommentar den Owner fragen; UI-Abnahme gemeinsam per Playwright (3 Breiten, hell/dunkel); Gegenprobe nie mit dem Muster der Umsetzung.
- GSD-Workflow für alle Änderungen.

## Sources

### Primary (HIGH confidence)
- nextcloud/app_api stable33: `lib/Controller/ExAppProxyController.php` (prepareProxy, 404 ohne Route, Zugriffsebenen), `lib/PublicFunctions.php` (`exAppRequest`, `getExApp`), `lib/Service/AppAPIService.php` (Timeout 3 s, Optionen bis zum Client), `lib/Service/ExAppService.php` (Routen nur bei `isset`), gelesen 07.11.2026
- nextcloud/server stable33: `lib/private/Http/Client/{Client,Response}.php` (`stream`, `getBody()->detach()`), `lib/public/Files/Folder.php` (`newFile` string|resource, `getNonExistingName`, `getFirstNodeById`), `lib/public/AppFramework/Http/StreamResponse.php`, `lib/public/Util.php` (`addInitScript`), `apps/files/lib/Controller/ViewController.php`, `lib/private/Template/JSResourceLocator.php` (`.mjs`), `apps/files_sharing/lib/ViewOnly.php`, `lib/public/Files/Storage/ISharedStorage.php`, `lib/public/Notification/INotifier.php`, `apps/files/src/utils/permissions.ts`, `apps/files/src/components/FileEntry*.vue` (stable33 + stable35), `composer.json` (`serve`), `package.json` stable33/34/35, Liste `apps/`
- nextcloud-libraries/nextcloud-files v4.1.1: `lib/ui/actions/fileAction.ts`, `lib/ui/types.ts`, `lib/globalScope.ts`, `lib/permissions.ts`
- npm registry 07.11.2026: Versionen und `postinstall` der genannten Pakete; PyPI JSON pymupdf 2.1 (requires_dist, Wheels)
- gh: app-certificate-requests #1411 (MERGED 05.11.), #1419 (OPEN); Repo-Secrets; AVS-CI-Läufe 42330693906 (grün), 42266020471, 42237222653, 42249446521 (fehlgeschlagene Schritte)
- AVS-Repo `C:/Users/Student/nextcloud-audio-video-search`: Phase-1-Planung (01-RESEARCH, 01-VALIDATION, 01-10/12/13-SUMMARY, deferred-items), Code `php/lib`, `backend/src`, `.github/workflows/deploy-harp.yml`, `ci/seed.sh`, Fix-Commits
- Findling `C:/Users/Student/nextcloud-search`: `php/lib/Db/QueueMapper.php`, Migration, `backend/src/findling/memory_guard.py`
- Projekt: `.planning/PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `research/{SUMMARY,ARCHITECTURE,PITFALLS,STACK}.md`, Skeleton (`appinfo/info.xml`, `pyproject.toml`, `src/pii_redaction/logs.py`, Workflows)

### Secondary (MEDIUM confidence)
- groupfolders README (occ-Syntax für ACL)
- `@nextcloud/vite-config` README 2.5.4

### Tertiary (LOW confidence)
- Push-Payload der Notifications-App, Längengrenzen von Migrationsnamen, MySQL-Fehler 1093 (Fachwissen, als Annahmen geführt)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (Registry und Server-`package.json` je Zweig geprüft, AVS-Pins)
- Architecture: HIGH für Integrationsgrenzen (Quelltext), MEDIUM für leere Routenliste beim Update, Streaming großer Ausgaben durch HaRP und Claim-Form unter MySQL
- Pitfalls: HIGH für AVS-Lehren (Commits und CI-Läufe), MEDIUM für neue PII-Punkte (begründet, in CI zu belegen)

**Research date:** 2026-11-07
**Valid until:** 2026-12-07 (Plattform stabil; `@nextcloud/files` und vite-config bewegen sich, vor Phase 9 erneut prüfen)
