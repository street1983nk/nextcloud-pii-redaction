---
phase: 1
slug: zwei-app-ger-st-und-integrationsbeweis
status: approved
shadcn_initialized: false
preset: none
created: 2026-11-07
---

# Phase 1: UI Design Contract

> Visueller und Interaktionsvertrag für Phase 1 (Zwei-App-Gerüst und Integrationsbeweis). Erstellt vom gsd-ui-researcher, geprüft vom gsd-ui-checker.
> Quellen: DESIGN.md (Vorrang), Skill nextcloud-ui, 01-CONTEXT.md (Owner 07.11.), 01-RESEARCH.md (Entscheide 2 bis 9 und 11, Pattern 1 und 3, Pitfalls 4 bis 6, F, G, J, K), PROJECT.md, Schwester-App Audio & Video Search (AVS) mit freigegebener UI-SPEC Phase 1 und deren Screenshot-Abnahme vom 07.11. (Commits 4291faa, 3d07c81, fed53b4, 1fb003d), `@nextcloud/vue` 9.14.1 und `@nextcloud/dialogs` 8.0.0 (Typdefinitionen und CSS heute gelesen).

Phase 1 hat genau fünf UI-Flächen, sonst keine:

1. **Dateiaktion** "Schwärzen / Pseudonymisieren" in der Dateien-App, mit Start-Rückmeldung als Toast
2. **Prüfseite (Platzhalter)** `/apps/pii_redaction/review/{jobId}` mit Status, Fortschritt, Warteschlange und Seite 1 als Bild
3. **Benachrichtigung** (Notifications-App), ohne Dateiname und ohne Fundinhalt
4. **Platzhalter-Kopie** neben dem Original (Dateiname und Inhalt der einseitigen PDF)
5. **Admin-Statusbereich** (Zustand der Gegen-App, AVS-Muster)

Nicht in Phase 1: Vorschlagsliste, Kästchen auf dem Seitenbild, Annehmen/Ablehnen (Phasen 8, 9), Modus-Wahl Schwärzen oder Pseudonymisieren (Phase 13; Phase 1 läuft immer im Modus `redact`), Seiten 2 und folgende, Zoom, Vier-Augen-Freigabe (Phase 10), Protokoll (Phase 11), Fortschritts- und Speicherangaben im Admin (Phase 15), Debug-Schalter (Owner: Platzhalter-Weg ohne Debug-Schalter), App-Navigationseintrag, eigene Übersicht aller Aufträge.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (shadcn nicht anwendbar: Nextcloud-App, UI-Konformität über Server-Variablen) |
| Preset | not applicable |
| Component library | Dateiaktion und Prüfseite: Vue 3.5.45 + `@nextcloud/vue` 9.14.1 + `@nextcloud/dialogs` 8.0.0 (Build über `@nextcloud/vite-config` 2.5.4, vite 7.3.7; Research Entscheid 2 und Standard Stack). Admin-Statusbereich: PHP-Template plus kleines Modul `src/admin.ts` ohne Vue, 1:1 aus AVS (`php/templates/admin.php`, `php/css/admin.css`, `php/js/admin.js`), damit er ohne JS lesbar bleibt und das in CI belegte Muster unverändert gilt |
| Icon library | Material Design Icons: in Vue über `vue-material-design-icons` (Größe 20), in der Dateiaktion als Inline-SVG-Zeichenkette (`iconSvgInline`, Pfaddaten von MDI, `viewBox="0 0 24 24"`, `fill="currentColor"`), im PHP-Admin als Inline-SVG mit `aria-hidden="true" focusable="false"` wie AVS |
| Font | Server-Schrift über `var(--font-face)`, keine Webfonts |

**DESIGN.md-Folgeaufgabe:** `TODO(skeleton)` in DESIGN.md auflösen: "Stufe 2 und 3 in der Begleit-App `pii_redaction`: Vue 3 mit `@nextcloud/vue` 9 für Dateiaktion und Prüfseite, weil `@nextcloud/files` 4 ohnehin einen Build braucht und die Prüfseite ab Phase 9 Liste, Kästchen und Tastatur trägt; PHP-Template für den Admin-Statusbereich (AVS-Muster, ohne JS lesbar). Die ExApp hat nur deklarative Einstellungen." PRODUCT.md bekommt Nutzer und Core Value aus PROJECT.md. Eine kleine Aufgabe im Plan.

**Verbindliche Regeln (DESIGN.md, nicht verhandelbar):**
- Nur Nextcloud-CSS-Variablen, kein Hex-, RGB- oder Farbname im Code, kein `!important`, kein `outline: none`, kein `style`-Attribut, keine `color`-Prop an Nc-Komponenten.
- Flach: keine Schatten, keine Verläufe, keine Karten in Karten.
- Keine Inline-Skripte (CSP); Skripte über `\OCP\Util::addInitScript()` (Dateiaktion, im Listener auf `LoadAdditionalScriptsEvent`) bzw. `\OCP\Util::addScript()` im Template; Startzustand über `IInitialState` / `@nextcloud/initial-state`, nie als Inline-JSON.
- Jeder sichtbare Text über `$l->t()` / `$l->n()` (PHP) bzw. `t('pii_redaction', ...)` / `n('pii_redaction', ...)` (JS). Fremdangaben (Dateiname, Versionen, Zeit) in PHP mit `p()`, in Vue nur über Textinterpolation `{{ }}`, nie `v-html`; Toasts nie mit `isHTML: true`.
- Nc-Komponenten werden nicht umgestylt (kein Überschreiben ihrer Klassen); eigene Klassen nur für Layout um sie herum.
- CSS-Klassen und IDs mit Präfix `pii-` (Muster `avs-`, `findling-`).
- Hell, dunkel und hoher Kontrast ohne eigenen Code, allein über Server-Variablen.
- Jede `[hidden]`-Regel an eine ID gebunden (`#pii-review [hidden]`, `#pii-admin [hidden]`), AVS-Pitfall 4.

---

## Spacing Scale

Alle Abstände als `calc(var(--default-grid-baseline) * n)`, Grundwert 4 px (gleiche Tokens wie AVS).

| Token | Value | CSS | Usage |
|-------|-------|-----|-------|
| xs | 4px | `var(--default-grid-baseline)` | Abstand zwischen zwei Label-Zeilen (Versionen, Zuletzt geprüft), Abstand Titel zu Satz in einer Statuskarte |
| sm | 8px | `* 2` | Icon zu Text in Bannern und in der Statuszeile, Lücke zwischen Knöpfen einer Zeile, Überschrift zu Metazeile, Statustext zu Fortschrittsbalken, Bild zu Bildunterschrift |
| md | 16px | `* 4` | Innenabstand Admin-Banner, **Abstand Banner bzw. Statuskarte zum nächsten Block** (AVS-Abnahme 07.11.), Abstand zwischen Blöcken der Prüfseite, Seitenrand bei 375 px |
| lg | 24px | `* 6` | Seitenrand ab 768 px |
| xl | 32px | `* 8` | Oberer Abstand der Prüfseite unter dem Kopf ab 768 px |

Nicht genutzt in Phase 1: 48 px, 64 px.

Exceptions:
- Klickflächen: mindestens `var(--default-clickable-area)` (34 px, Server-Vorgabe für die Mindest-Klickfläche, kein Wert der 4er-Abstandsskala), bei `@media (pointer: coarse)` mindestens 44 px (`* 11`). Gilt für Knöpfe, Links in Statuskarten und Bannern. `NcButton` erfüllt das selbst.
- `NcNoteCard` bringt eigenen Innenabstand (8 px) und Außenrand (16 px oben und unten) mit; das passt zur Skala und wird nicht überschrieben. Folgt eine Karte direkt auf eine andere, gilt deren Außenrand (16 px), kein zusätzlicher Abstand.
- Lesespalte der Prüfseite: `max-width: calc(var(--default-grid-baseline) * 240)` (960 px), linksbündig, kein zentrierter Hero-Block.
- Seitenbild: `max-width: 100%`, `height: auto`, nie über die natürliche Breite hinaus vergrößert; Platzhalterfläche vor dem Laden mit `aspect-ratio` aus der vom Server gemeldeten Bildgröße (`width`/`height` am `<img>`), damit nichts springt.

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body (Fließtext, Satz in Statuskarten und Bannern, Toast) | 15px = `var(--default-font-size)` | 400 | `var(--default-line-height)` (Ref. 1,5) |
| Label (Metazeile, Versionen, "Zuletzt geprüft", Bildunterschrift, Seitenzähler) | 13px = `var(--font-size-small)` | 400 | `var(--default-line-height)` |
| Heading (h2: Dateiname bzw. "Prüfung" auf der Prüfseite, Abschnittstitel im Admin) | 20px | 700 | `var(--default-line-height)` |
| Titelzeile (Titel in Statuskarte, Statuszeile und Admin-Banner) | 15px = `var(--default-font-size)` | 700 | `var(--default-line-height)` |

Genau drei Größen (13, 15, 20) und zwei Gewichte (400, 700), wie AVS. Kein Display-Grad. Zeilenhöhe nur über `var(--default-line-height)`.

Zusatzregeln:
- `NcNoteCard` wird **ohne** `heading`-Prop benutzt (die Prop setzt 20 px in Gewicht 600 und bräche die Zwei-Gewichte-Regel). Titel und Satz kommen in den Standard-Slot: `<p class="pii-note__title">` (15 px, 700) und `<p class="pii-note__text">` (15 px, 400).
- Dateinamen: `overflow-wrap: anywhere`, nie abgeschnitten (lange Behördennamen ohne Leerzeichen bei 375 px).
- Zahlen in Zählern und Uhrzeiten mit `font-variant-numeric: tabular-nums`.
- Rang über Gewicht, nicht über weitere Größen.

---

## Color

Werte sind Server-Variablen; die Hex-Angaben sind nur Referenz des Standard-Themes (DESIGN.md) und gehören nie in den Code.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `--color-main-background` (Ref. #ffffff) | Seitengrund der Prüfseite und des Admin-Bereichs |
| Secondary (30%) | `--color-background-hover` (Ref. #f5f5f5), Linie `--color-border` (Ref. #ededed) | Platzhalterfläche des Seitenbilds während des Ladens, 1-px-Rahmen um das Seitenbild (damit eine weiße Seite auf weißem Grund erkennbar ist), Statuszeile in Warteschlange und Lauf |
| Accent (10%) | `--color-primary-element` mit `--color-primary-element-text` (Ref. #00679e / #ffffff) | nur die unten gelisteten Elemente |
| Destructive | `--color-error` mit `--color-error-text` | nur Fehlerzustände (Statuskarte, Admin-Banner, Fehler-Toast); Phase 1 hat keine zerstörende Aktion |

Gedämpfter Text: `--color-text-maxcontrast` nur für die Label-Rolle. **Nie** für Banner- oder Kartentext (AVS-Abnahme 07.11.: geerbtes Grau aus der Server-Regel `.section p` ergab nur knapp 4,5:1).

Statuspaare (Pair Rule, nie gemischt):

| Status | Fläche / Text | Icon | MDI-Icon |
|--------|---------------|------|----------|
| Fehler | `--color-error` / `--color-error-text` | `--color-element-error` | `alert-circle-outline` |
| Warnung | `--color-warning` / `--color-warning-text` | `--color-element-warning` | `alert-outline` |
| Hinweis | `--color-info` / `--color-info-text` | `--color-element-info` | `information-outline` |
| Erfolg | `--color-success` / `--color-success-text` | `--color-element-success` | `check-circle-outline` |

Textfarbe in Statusflächen (Pflicht, Lehre aus AVS):
- **Admin-Banner (PHP):** Titel und Satz mit zwei Klassen gegen `.section p` abgesichert (`.pii-banner .pii-banner__title, .pii-banner .pii-banner__text { color: inherit; max-width: none; margin: 0; }`), der Banner selbst trägt `color: var(--color-<status>-text)`. Ergebnis: Text im Status-Textton, nie im gedämpften Grau.
- **Prüfseite (Vue):** `NcNoteCard` setzt Text auf `--color-main-text` und den Streifen auf den Status-Textton; das bleibt so. Eigene `<p>` im Slot setzen `color: inherit` und `max-width: none`, damit keine Server-Regel sie grau färbt.

Accent reserved for:
1. Prüfseite, Zustand bereit: der Knopf "Platzhalter-Kopie anlegen" (`NcButton variant="primary"`), die einzige Hauptaktion der Seite.
2. Prüfseite: die Füllung des Fortschrittsbalkens (`NcProgressBar`, Standardfarbe der Komponente, keine `color`-Prop).
3. Admin: die eine Aktion "Apps öffnen" in einem Fehler-Banner, als Link wie `button.primary` gestaltet (AVS `avs-admin .avs-banner__action`).

Sonst nirgends: nicht für Überschriften, nicht für Dateinamen, nicht für "In Dateien anzeigen", "Erneut laden", "Erneut prüfen", nicht für den Link im Toast (Toast-Gestaltung kommt vom Server).

Never Color Alone: Jeder Status trägt Icon und Satz; Farbe ist nie alleiniger Träger.

Seitenbild im Dunkelmodus: **nicht** invertieren, kein `--background-invert-if-dark`. Die Prüfung muss das Dokument so zeigen, wie es ausgegeben wird.

---

## Fläche 1: Dateiaktion und Start-Rückmeldung

Registrierung über `registerFileAction` aus `@nextcloud/files` 4.1.1 (Research Pattern 1). Die Dateien-App zeichnet Menüeintrag und Icon selbst; die App liefert nur Daten. Kein eigenes CSS in der Dateien-App.

| Feld | Vertrag |
|------|---------|
| `id` | `pii_redaction-start` (stabil, Playwright nutzt `data-cy-files-list-row-action="pii_redaction-start"`) |
| `displayName` | DE "Schwärzen / Pseudonymisieren", EN "Redact / pseudonymize", FR "Caviarder / pseudonymiser" (Schrägstrich mit je einem Leerzeichen) |
| `iconSvgInline` | MDI `eye-off-outline`, `fill="currentColor"`, ohne Breite/Höhe (die Dateien-App setzt 20 px) |
| `order` | 60 (nach den Server-Einträgen für Öffnen, Teilen, Herunterladen) |
| `default` | nicht gesetzt (Klick auf den Dateinamen öffnet weiter die Datei) |
| `enabled()` | genau ein Knoten, Datei, Mime PDF/DOCX/ODT, Leserecht, herunterladbar (Download-Sperre nachgebaut), angemeldeter Nutzer, nicht Papierkorb, nicht `is-encrypted` (Research Entscheid 2). Nur Komfort, PHP prüft alles erneut |
| Mehrfachauswahl | Aktion nicht angeboten (kein `execBatch`) |

### Ablauf von `exec()`

1. `POST /apps/pii_redaction/api/v1/jobs {fileId}`. Währenddessen zeigt die Dateien-App ihre eigene Ladeanzeige am Eintrag; die App zeigt keinen zusätzlichen Lade-Toast.
2. Antwort `201` (neu) oder `200` (schon offener Auftrag für dieselbe Datei, denselben Etag und denselben Nutzer, Pitfall K): Toast über `showMessage(node, { type: ToastType.SUCCESS bzw. INFO, timeout: 10000, close: true })`. `node` ist ein per `document.createElement` gebautes Element mit Satz (Textknoten) und einem Link `<a href="/apps/pii_redaction/review/{jobId}">` "Prüfseite öffnen". Kein `isHTML`, kein Dateiname im Toast.
3. Fehler: `showMessage(node, { type: ToastType.ERROR bzw. WARNING, timeout: -1, close: true })`, Satz aus der geschlossenen Grundliste (Tabelle unten). Fehler bleiben stehen, bis sie geschlossen werden (BITV: genug Zeit zum Lesen).
4. Rückgabe `null` (keine zweite Meldung der Dateien-App).

Warteschlangenposition: Der Server liefert `ahead` = Zahl der Aufträge, die vor diesem laufen oder warten (Research Entscheid 4: wartende Aufträge mit kleinerer ID plus 1, wenn gerade einer läuft). Angezeigt wird nur diese Zahl, nie Namen, nie eine geschätzte Restzeit.

Barrierefreiheit: Der Toast ist nur eine Abkürzung. Gleichwertige Wege zur Prüfseite ohne Zeitdruck: erneuter Klick auf die Aktion (liefert idempotent denselben Auftrag und denselben Toast) und die Benachrichtigung, sobald die Prüfung bereit ist. Erfolgs-Toasts `aria-live="polite"`, Fehler-Toasts `assertive` (Standard der Bibliothek).

### Zustände der Dateiaktion

| Zustand | Erkennung | Toast-Art | Copy-Schlüssel |
|---------|-----------|-----------|----------------|
| Gestartet, nichts davor | 201, `ahead = 0` | Erfolg | Start: als Nächstes |
| Gestartet, Aufträge davor | 201, `ahead >= 1` | Erfolg | Start: n davor (Plural) |
| Läuft schon | 200, offener Auftrag zurückgegeben | Hinweis | Start: läuft schon |
| Backend nicht bereit | 503, Grund `backend_unavailable` (Drift, fehlt, aus, nicht erreichbar, Companion fehlt) | Warnung | Start: Backend nicht bereit |
| Download gesperrt | 403, Grund `download_blocked` | Fehler | Start: Download gesperrt |
| Nicht lesbar oder weg | 404, Grund `not_readable` | Fehler | Start: nicht verfügbar |
| Format | 415, Grund `unsupported_format` | Fehler | Start: Format |
| Sonstiges, Netz, 5xx | alles andere | Fehler | Start: allgemein |

Die HTTP-Codes sind Vorschlag für den Plan; maßgeblich ist der Grund aus der geschlossenen Liste im Antwortkörper.

---

## Fläche 2: Prüfseite (Platzhalter)

Route `GET /apps/pii_redaction/review/{jobId}`, `TemplateResponse` im normalen Nextcloud-Rahmen (Kopfleiste sichtbar), ohne App-Navigation. Das Template enthält nur `<div id="pii-review" class="pii-review">`; PHP gibt per `IInitialState` den Startzustand mit (`state`, `jobId`, `fileId`, `fileName` nur wenn sichtbar, `status`, `stage`, `reason`, `ahead`, `pagesDone`, `pagesTotal`, `createdAt`, `backendReady`, `image: {width, height}` nur im Zustand bereit). Vue mountet darauf. HTTP-Status setzt PHP vor dem Rendern (Tabelle unten).

### Aufbau (DOM-Reihenfolge = Lese- und Tab-Reihenfolge)

1. Wurzel `#pii-review` innerhalb des Server-`#app-content`; kein zweites `<main>`.
2. `h2` Dateiname (nach Recheck) bzw. "Prüfung", wenn der Name nicht gezeigt werden darf oder die Datei weg ist.
3. Metazeile (Label-Rolle): "Gestartet am {Datum, Uhrzeit}" (`Intl.DateTimeFormat` mit `getCanonicalLocale()` aus `@nextcloud/l10n`, `dateStyle: 'medium'`, `timeStyle: 'short'`, im Markup `<time datetime="ISO">`). Entfällt, wenn kein Auftrag sichtbar ist.
4. Statusbereich `#pii-review-state` mit `role="status"` und `aria-live="polite"`: genau eine Statuszeile (Warteschlange, Lauf, Kopie wird angelegt) oder genau eine Statuskarte (`NcNoteCard`).
5. Nur wenn `backendReady === false` und der Auftrag nicht abgeschlossen ist: zusätzliche Warnkarte "Backend nicht bereit" (ohne Versionen, die sieht nur der Admin).
6. Nur im Zustand bereit: Hinweiskarte "Platzhalter", dann Aktionszeile (sm-Lücke, bricht bei 375 px um): `NcButton variant="primary"` "Platzhalter-Kopie anlegen", `NcButton variant="tertiary"` als Link (`href` = `generateUrl('/f/{fileId}')`) "In Dateien anzeigen".
7. Nur im Zustand bereit: `<figure class="pii-review__page">` mit `<img>` (Seite 1, `src` = `/apps/pii_redaction/review/{jobId}/page/1`, `width`/`height` aus dem Startzustand, `alt` siehe Copy, `decoding="async"`, kein `loading="lazy"`), 1-px-Rahmen `--color-border`, Radius `--border-radius-small`, darunter `<figcaption>` (Label-Rolle) "Seite 1 von {n}" bzw. "Seite 1", solange `pagesTotal` unbekannt ist.

Aktionen stehen vor dem Bild, damit sie bei 375 px ohne Scrollen über die ganze Seitenhöhe erreichbar sind.

### Statuszeile (Warteschlange, Lauf, Kopie wird angelegt)

Fläche `--color-background-hover`, Radius `--border-radius-container`, Innenabstand md, Text `--color-main-text`. Inhalt: `NcLoadingIcon` (20 px, `aria-hidden`, weil der Text die Bedeutung trägt) mit sm-Abstand vor Titelzeile (700) und Satz (400). Darunter, nur wenn `pagesTotal` bekannt ist und größer als 0: `NcProgressBar` (`size="medium"`, `value = round(100 * pagesDone / pagesTotal)`, `aria-label` = Titelzeile) und Seitenzähler (Label-Rolle) "{done} von {total} Seiten". Ohne bekannte Seitenzahl kein Balken (kein vorgetäuschter Fortschritt). Keine Restzeit, keine Prozentzahl ohne echten Zähler.

### Abfrage (Polling)

- `GET /apps/pii_redaction/api/v1/jobs/{id}` alle 3 s, solange der Status `queued`, `analyzing`, `approved`, `applying` oder `verified` ist; Antwort mit `Cache-Control: private, no-store` (Pitfall J).
- Bei verdecktem Tab (`document.visibilityState === 'hidden'`) pausieren, beim Zurückkehren sofort abfragen.
- Abfrage scheitert (Netz, 5xx): Warnkarte "Stand nicht aktualisiert" zusätzlich unter dem letzten Stand, weiter versuchen mit Rückoff 3, 6, 12, 30 s; beim nächsten Erfolg verschwindet die Karte.
- 401: Karte "Sitzung abgelaufen" mit Knopf "Seite neu laden", Abfrage stoppt.
- Endzustände (`review`, `published`, `failed`, `stale`, `cancelled`, `expired`) stoppen die Abfrage.
- Live-Region: Der Text in `#pii-review-state` ändert sich nur bei Wechsel von Status oder Stufe, nicht bei jedem Seitenzähler-Schritt (Seitenzähler und Balken liegen außerhalb der Live-Region). So bleibt die Ansage ruhig.

### Seitenbild

- PHP liefert das PNG nach Recheck (Mitglied, lesbar, keine Download-Sperre, Etag gleich) mit `Cache-Control: private, no-store` und `X-Content-Type-Options: nosniff` (Research Pattern 3).
- Während des Ladens: Platzhalterfläche `--color-background-hover` im Seitenformat mit `NcLoadingIcon` in der Mitte, `aria-busy="true"` an der `figure`.
- `error`-Ereignis am Bild: Vue fragt sofort den Status ab. Status `stale` oder Download-Sperre: Wechsel in den passenden Zustand. Sonst Warnkarte "Seite nicht abrufbar" mit Knopf "Erneut laden" (sekundär, setzt `src` mit neuem Abfrageparameter `?r={n}`), das Bild wird ausgeblendet.

### Zustände der Prüfseite

| Zustand | Erkennung | Darstellung | Dateiname | HTTP |
|---------|-----------|-------------|-----------|------|
| Warteschlange | `queued` | Statuszeile "In der Warteschlange" + Satz nach `ahead` | ja | 200 |
| Warteschlange, Backend nicht bereit | `queued` und `backendReady = false` | Statuszeile + Warnkarte "Backend nicht bereit" | ja | 200 |
| Läuft: Vorbereitung | `analyzing`, Stufe `waiting` | Statuszeile "Analyse startet" | ja | 200 |
| Läuft: Laden | Stufe `fetching` | Statuszeile "Datei wird geladen" | ja | 200 |
| Läuft: Umwandeln | Stufe `converting` (nur DOCX/ODT) | Statuszeile "Datei wird in PDF umgewandelt" | ja | 200 |
| Läuft: Seitenbild | Stufe `rendering` | Statuszeile "Seitenbild wird erstellt", Balken wenn Seitenzahl bekannt | ja | 200 |
| Bereit | `review` | Hinweiskarte Platzhalter, Aktionszeile, Seite 1 | ja | 200 |
| Seite nicht abrufbar | Bild-Fehler, Status weiter `review` | wie Bereit, Bild ersetzt durch Warnkarte mit "Erneut laden" | ja | 200 (Bild 502) |
| Kopie wird angelegt | `approved`, `applying`, `verified` | Statuszeile "Kopie wird angelegt", Knopf entfällt, kein Bild | ja | 200 |
| Kopie angelegt | `published` | Erfolgskarte mit Namen der Kopie und Link "Kopie in Dateien anzeigen" (`/f/{outputFileId}`) | ja | 200 |
| Ungültig, Original geändert | `stale(original_changed)` oder Etag weicht beim Aufruf ab | Warnkarte "Datei wurde geändert", Link "In Dateien anzeigen", kein Bild | ja | 200 (Bild 409) |
| Original gelöscht | `cancelled(original_deleted)` | Hinweiskarte "Datei wurde gelöscht", Link "Zu Dateien" | **nein** ("Prüfung") | 200 |
| Download gesperrt | Recheck meldet Sperre (Freigabe nachträglich geändert) | **Hinweis**karte (keine Fehlfarbe: bewusste Einstellung, AVS-Muster), kein Bild, kein Knopf | ja | 200 (Bild 403) |
| Fehlgeschlagen | `failed(reason)` | Fehlerkarte mit Titel und Satz je Grund (Copy), Link "In Dateien anzeigen" | ja, wenn lesbar | 200 |
| Abgelaufen | `expired` (Spalte existiert, Durchsetzung ab Phase 10) | Hinweiskarte "Prüfung abgelaufen" | ja, wenn lesbar | 200 |
| Nicht verfügbar | Auftrag fehlt, Nutzer ist nicht Auftraggeber, kein Leserecht mehr (auch Gruppenordner-ACL, entzogene Freigabe) | Fehlerkarte "Prüfung nicht verfügbar", Link "Zu Dateien"; fehlend und verboten sind nicht unterscheidbar; keine Metazeile | **nein** ("Prüfung") | 404 |
| Backend nicht bereit, bereit-Zustand | `review` und `backendReady = false` | Warnkarte "Backend nicht bereit" statt Bild; Knopf "Platzhalter-Kopie anlegen" `disabled` | ja | 200 |
| Stand nicht aktualisiert | Abfrage scheitert | letzter Stand + Warnkarte | wie zuvor | 200 |
| Sitzung abgelaufen | 401 bei Abfrage | Warnkarte + "Seite neu laden" | wie zuvor | 200 |
| Abgemeldet aufgerufen | keine Sitzung | Server-Anmeldeseite, danach zurück auf die Prüfseite | n. a. | 303 |

Kein Zustand nennt Versionen, Pfade, Ordnernamen oder Fundinhalt. Der Dateiname erscheint nur, wenn der Recheck für den aufrufenden Nutzer gerade bestanden ist.

### Interaktion "Platzhalter-Kopie anlegen"

- Klick: `POST /apps/pii_redaction/review/{jobId}/placeholder` (Request-Token über `@nextcloud/axios`). Währenddessen Knopf `disabled` mit `NcLoadingIcon` im Icon-Slot, Text "Wird angelegt…". Danach Wechsel in "Kopie wird angelegt" und Abfrage läuft weiter.
- Keine Rückfrage-Dialoge: die Aktion überschreibt nichts (immer neuer Name per `getNonExistingName`), ist also nicht zerstörend.
- Fehler beim POST: Fehlerkarte unter der Aktionszeile mit dem Satz aus der Grundliste, Knopf wieder aktiv.
- Fokus: Nach diesem nutzerausgelösten Wechsel geht der Fokus auf die neue Statuszeile bzw. die Ergebniskarte (`tabindex="-1"`, programmatisch), damit Tastatur- und Screenreader-Nutzer nicht auf einem verschwundenen Knopf stehen.

### Responsives Verhalten

| Breite | Vertrag |
|--------|---------|
| 375 px | Seitenrand md, Bild volle Spaltenbreite, Aktionszeile umbrechend (jeder Knopf eigene Zeile, wenn nötig), Klickflächen 44 px bei `pointer: coarse` |
| 768 px | Seitenrand lg, oberer Abstand xl |
| 1280 px | Lesespalte max. 960 px, linksbündig |

Dokumenttitel (WCAG 2.4.2): "Prüfung: {Dateiname}" bzw. "Prüfung", wenn kein Name gezeigt wird; API je NC-Version im Plan prüfen (AVS-Weg übernehmen).

---

## Fläche 3: Benachrichtigung

Eigener `INotifier` (Research Entscheid 7). Owner 07.11.: **kein Dateiname, kein Fundinhalt, kein Pfad** in Betreff oder Nachricht; die Benachrichtigung verlinkt nur auf die Prüfseite. Grund: Push-Weg über Push-Proxy, Behörden-Dateinamen tragen oft Personennamen.

| Feld | Vertrag |
|------|---------|
| App-Name (`getName()`) | "PII Redaction" (nicht übersetzt) |
| Icon | `imagePath('pii_redaction', 'app-dark.svg')` absolut |
| Objekt | `('job', jobId)` |
| Link | absolute URL der Prüfseite `/apps/pii_redaction/review/{jobId}` |
| Aktionen | keine (der Link ist die Aktion) |
| Betreff | geschlossene Liste `review_ready`, `job_failed`, `job_stale`, `copy_created` (Copy unten); keine Parameter |
| Nachricht | ein Satz je Betreff ohne Parameter (Copy unten) |
| Erledigt | `markProcessed` für dieses Objekt, sobald der Auftraggeber die Prüfseite öffnet; ein neuer Betreff desselben Auftrags ersetzt den alten (vorher `markProcessed`) |
| Sprache | Sprache des Empfängers zur Zeit des Abrufs (`prepare($n, $languageCode)`) |
| Unbekannter Betreff | `UnknownNotificationException` |
| Original gelöscht | keine Benachrichtigung (der Nutzer hat selbst gelöscht) |

---

## Fläche 4: Platzhalter-Kopie

Owner 07.11.: Die Kopie trägt schon den echten späteren Namenszusatz, Schwärzen und Pseudonymisieren getrennt.

| Feld | Vertrag |
|------|---------|
| Ort | derselbe Ordner wie das Original, angelegt als Auftraggeber per `newFile()` |
| Name | `{Stamm}{Zusatz}.pdf`; Stamm = Name des Originals ohne letzte Endung; Endung immer `.pdf` (auch bei DOCX/ODT, weil die Kopie in Phase 1 eine PDF ist) |
| Zusatz `redact` | de, de_DE: `_geschwärzt`; en (und jede andere Sprache): `_redacted`; fr: `_caviardé` |
| Zusatz `pseudonymize` | de, de_DE: `_pseudonymisiert`; en: `_pseudonymized`; fr: `_pseudonymisé` (Funktion und Tests ab Phase 1, Nutzung ab Phase 13) |
| Sprache | Sprache des Auftraggebers beim Anlegen des Auftrags (im Auftrag nicht als Freitext, sondern als Kürzel `de`/`en`/`fr` aus geschlossener Liste) |
| Kollision | `getNonExistingName()` des Servers ("Bericht_geschwärzt (2).pdf"); nie überschreiben |
| Unicode | Name in NFC (ä, é als ein Zeichen) |
| Beispiel | `Bescheid 2026-114.docx` -> `Bescheid 2026-114_geschwärzt.pdf` |

Inhalt der einseitigen PDF (ohne jeden Originalinhalt, Research Entscheid 8), A4 hochkant, Standardschrift Helvetica, linksbündig mit 72 pt Rand, drei Blöcke untereinander (DE, EN, FR), je Titel 20 pt fett und Satz 12 pt normal, darunter eine gemeinsame Zeile 12 pt mit der Auftragsnummer:

| Zeile | DE | EN | FR |
|-------|----|----|----|
| Titel | Platzhalter aus PII Redaction | Placeholder from PII Redaction | Fichier provisoire de PII Redaction |
| Satz | Nicht geschwärzt: Diese Datei enthält nichts aus dem Original. | Not redacted: this file contains nothing from the original. | Non caviardé : ce fichier ne contient rien de l'original. |
| Auftrag | Auftrag %d | Job %d | Tâche %d |

PDF-Metadaten: Titel "PII Redaction placeholder", kein Autor, kein Originalname. Der Kanarien-Test prüft die Kopie (Research Entscheid 10).

---

## Fläche 5: Admin-Statusbereich

1:1 AVS Fläche 3 mit neuen IDs; nur der Debug-Block entfällt. Eigene Admin-Sektion "PII Redaction" (`IIconSection`, ID `pii_redaction`, Priorität 75, `app-dark.svg`). Serverseitig vollständig gerendert, ohne Lade-Skelett.

### Aufbau

1. `div.section#pii-admin` mit `h2` "Verbindung zum Backend".
2. Genau ein Zustands-Banner `#pii-backend-state` im Container mit `role="status" aria-live="polite"`. Banner-Aufbau wie AVS: `<div class="pii-banner pii-banner--{error|warning|info|success}">`, Icon (20 px) im eigenen Container mit `display: flex; align-items: center; height: var(--default-line-height)`, Titelzeile 700, Satz 400, optional eine Aktion; Innenabstand md, Radius `--border-radius-container`, sm zwischen Icon und Text, keine Rahmenlinie, kein Schatten; **Text im Status-Textton** (siehe Color).
3. **md (16 px) Abstand** zwischen Banner und Versionszeile (AVS-Abnahme 07.11.).
4. Versionszeile (Label-Rolle): "Diese App: {a} · Backend: {b}".
5. xs, dann "Zuletzt geprüft: {Uhrzeit}" (Label-Rolle, `IDateTimeFormatter`).
6. md, dann Knopf "Erneut prüfen" (sekundär). Während der Prüfung `disabled`, `.icon-loading-small`, Text "Wird geprüft…", `aria-busy="true"` am Statuscontainer; Ergebnis ersetzt Banner und Zeilen an Ort und Stelle; Fokus danach auf `#pii-backend-state` (`tabindex="-1"`). Ohne JS zeigt Neuladen den neuen Stand.

### Zustände Gegen-App

| Zustand | Banner | Wirkung auf Nutzer | Aktion |
|---------|--------|--------------------|--------|
| `ok` | Erfolg | normal | keine |
| `version_patch_differs` | Hinweis | normal | keine |
| `version_drift` | Fehler | keine neue Analyse, wartende Aufträge warten | "Apps öffnen" |
| `backend_missing` | Fehler | dito | "Apps öffnen" |
| `backend_disabled` | Fehler | dito | "Apps öffnen" |
| `backend_unreachable` | Fehler | dito | "Apps öffnen" |
| `no_app_api` | Fehler | dito | "Apps öffnen" |
| Neuprüfung gescheitert | Warnung zusätzlich zum letzten Banner | unverändert | keine |

Link "Apps öffnen": Ziel ist die App-Verwaltung des Servers, **ab NC 34 Route `appstore.page.viewApps`, bis NC 33 `settings.AppSettings.viewApps`** (AVS-Fix 4291faa); Auswahl im PHP über die Serverversion, nicht über Ausprobieren. Öffnet im selben Tab, einziger Akzent im Banner, Gestalt wie `button.primary`, Hover und Fokus mit `--color-primary-element-hover`. **Pflichttest:** In jedem der fünf Fehlerzustände existiert der Link, ist per Tab erreichbar, und sein `href` liefert nach Anmeldung als Admin 200 auf NC 33, 34 und 35.

Kein Banner nennt Dateinamen, Pfade oder Auftragszahlen. Versionen werden genannt (für den Admin nötig).

### Backend-App (ExApp)

Keine eigene Oberfläche außer einem statischen Beschreibungssatz in den deklarativen Einstellungen (falls das Skelett die Seite rendert), Copy "Backend-Beschreibung".

---

## Copywriting Contract

Regeln:
- Deutsch zuerst. `de` und `de_DE` (Owner: `de_DE` zusätzlich, Sie-Form) bekommen **denselben** Text in unpersönlicher Form: weder "du" noch "Sie" als Anrede, Aufforderungen im Infinitiv ("Die Seite neu laden."). Damit ist der Text in beiden Registern korrekt und beide Kataloge bleiben im Gleichstand (AVS- und Findling-Muster). "Sie" am Satzanfang als Pronomen für "die Datei" ist erlaubt.
- Französisch mit Infinitiv- bzw. Vous-Form; **geschütztes Leerzeichen U+00A0** vor `:` `;` `?` `!` und innerhalb `« »`. In den Tabellen unten steht dort ein normales Leerzeichen nur aus Darstellungsgründen; im Katalog ist es U+00A0.
- Echte Umlaute und ß, keine Gedankenstriche (U+2013, U+2014), keine Emojis, kein Ausrufezeichen, Satzanfang groß, Auslassung als `…` (U+2026).
- Platzhalter: PHP `%s`, `%1$s`, `%2$s`, `%d`; Plural über `n()` mit `%n`. In allen drei Sprachen dieselben Platzhalter.
- "PII Redaction", "AppAPI" und "PII Redaction Backend" werden nicht übersetzt.
- Begriffe: **Analyse** = Maschinenlauf, **Prüfung** = Seite für den Menschen, **Kopie** = Ergebnisdatei. FR: analyse / vérification / copie. EN: analysis / review / copy.

### Pflichtfelder (Template)

| Element | Copy (DE) |
|---------|-----------|
| Primary CTA | Dateien: "Schwärzen / Pseudonymisieren" (Dateiaktion). Prüfseite: "Platzhalter-Kopie anlegen". Admin: "Apps öffnen" im Fehler-Banner |
| Empty state heading | Prüfseite, Warteschlange: "In der Warteschlange" |
| Empty state body | "Der Auftrag ist als Nächstes dran." bzw. "%n Auftrag ist vorher dran." / "%n Aufträge sind vorher dran." |
| Error state | "Diese Prüfung ist nicht verfügbar" / "Sie wurde beendet, oder für die Datei besteht keine Berechtigung mehr. Die Datei in Dateien neu analysieren." |
| Destructive confirmation | keine: Phase 1 hat keine zerstörende Aktion (die Kopie bekommt immer einen neuen Namen, das Original bleibt unverändert) |

### Fläche 1: Dateiaktion und Toasts

| Schlüssel | DE | EN | FR |
|-----------|----|----|----|
| Aktion | Schwärzen / Pseudonymisieren | Redact / pseudonymize | Caviarder / pseudonymiser |
| Start: als Nächstes | Analyse gestartet. Der Auftrag ist als Nächstes dran. | Analysis started. It is next in line. | Analyse lancée. Elle est la prochaine. |
| Start: n davor (Singular) | Analyse gestartet. %n Auftrag ist vorher dran. | Analysis started. %n job is ahead of it. | Analyse lancée. %n analyse la précède. |
| Start: n davor (Plural) | Analyse gestartet. %n Aufträge sind vorher dran. | Analysis started. %n jobs are ahead of it. | Analyse lancée. %n analyses la précèdent. |
| Start: läuft schon | Für diese Datei läuft bereits eine Analyse. | An analysis is already running for this file. | Une analyse est déjà en cours pour ce fichier. |
| Toast-Link | Prüfseite öffnen | Open review page | Ouvrir la page de vérification |
| Start: Backend nicht bereit | PII Redaction ist gerade nicht bereit, deshalb startet keine Analyse. Die Verwaltung dieser Instanz informieren. | PII Redaction is not ready right now, so no analysis starts. Tell the administrators of this instance. | PII Redaction n'est pas prêt pour le moment, aucune analyse ne démarre donc. Prévenez l'administration de cette instance. |
| Start: Download gesperrt | Die Freigabe erlaubt kein Herunterladen, deshalb ist keine Analyse möglich. Wer die Datei freigegeben hat, kann das Herunterladen erlauben. | This share does not allow downloads, so no analysis is possible. The person who shared the file can allow downloads. | Ce partage n'autorise pas le téléchargement, aucune analyse n'est donc possible. La personne qui a partagé le fichier peut autoriser le téléchargement. |
| Start: nicht verfügbar | Die Datei ist nicht mehr verfügbar oder nicht lesbar. Die Ansicht neu laden. | The file is no longer available or cannot be read. Reload the view. | Le fichier n'est plus disponible ou ne peut pas être lu. Rechargez la vue. |
| Start: Format | Analysiert werden nur PDF-, DOCX- und ODT-Dateien. | Only PDF, DOCX and ODT files can be analysed. | Seuls les fichiers PDF, DOCX et ODT peuvent être analysés. |
| Start: allgemein | Die Analyse konnte nicht gestartet werden. Später erneut versuchen. | The analysis could not be started. Try again later. | L'analyse n'a pas pu être lancée. Réessayez plus tard. |

### Fläche 2: Prüfseite

| Schlüssel | DE | EN | FR |
|-----------|----|----|----|
| h2 ohne Dateiname, Dokumenttitel | Prüfung | Review | Vérification |
| Dokumenttitel mit Name | Prüfung: %s | Review: %s | Vérification : %s |
| Metazeile | Gestartet am %s | Started on %s | Lancée le %s |
| Warteschlange, Titel | In der Warteschlange | In the queue | En file d'attente |
| Warteschlange, als Nächstes | Der Auftrag ist als Nächstes dran. | It is next in line. | Elle est la prochaine. |
| Warteschlange, n davor (Singular) | %n Auftrag ist vorher dran. | %n job is ahead of it. | %n analyse la précède. |
| Warteschlange, n davor (Plural) | %n Aufträge sind vorher dran. | %n jobs are ahead of it. | %n analyses la précèdent. |
| Stufe `waiting`, Titel | Analyse startet | Analysis is starting | L'analyse démarre |
| Stufe `waiting`, Satz | Der Auftrag wird vorbereitet. | The job is being prepared. | La tâche est en préparation. |
| Stufe `fetching`, Titel | Datei wird geladen | Loading the file | Chargement du fichier |
| Stufe `fetching`, Satz | Die Datei wird innerhalb dieses Servers an die Analyse übergeben. | The file is handed to the analysis within this server. | Le fichier est transmis à l'analyse au sein de ce serveur. |
| Stufe `converting`, Titel | Datei wird in PDF umgewandelt | Converting the file to PDF | Conversion du fichier en PDF |
| Stufe `converting`, Satz | Das dauert bei großen Dokumenten etwas länger. | This takes a little longer for large documents. | Cela prend un peu plus de temps pour les documents volumineux. |
| Stufe `rendering`, Titel | Seitenbild wird erstellt | Creating the page image | Création de l'image de la page |
| Stufe `rendering`, Satz | Seite 1 wird für die Prüfung vorbereitet. | Page 1 is being prepared for review. | La page 1 est préparée pour la vérification. |
| Seitenzähler | %1$s von %2$s Seiten | %1$s of %2$s pages | %1$s sur %2$s pages |
| Platzhalter, Titel | Vorschau ohne Erkennung | Preview without detection | Aperçu sans détection |
| Platzhalter, Satz | Diese Version zeigt nur Seite 1 und sucht noch keine personenbezogenen Daten. Die Platzhalter-Kopie enthält nichts aus dem Original. | This version only shows page 1 and does not look for personal data yet. The placeholder copy contains nothing from the original. | Cette version n'affiche que la page 1 et ne recherche pas encore de données personnelles. La copie provisoire ne contient rien de l'original. |
| Knopf Hauptaktion | Platzhalter-Kopie anlegen | Create placeholder copy | Créer une copie provisoire |
| Knopf während POST | Wird angelegt… | Creating… | Création… |
| Link Datei | In Dateien anzeigen | Show in Files | Afficher dans Fichiers |
| Link Dateien allgemein | Zu Dateien | Go to Files | Aller à Fichiers |
| Bild `alt` | Seite 1 von %s (Seitenzahl, nie Dateiname) | Page 1 of %s | Page 1 sur %s |
| Bildunterschrift bekannt | Seite 1 von %s | Page 1 of %s | Page 1 sur %s |
| Bildunterschrift unbekannt | Seite 1 | Page 1 | Page 1 |
| Seite nicht abrufbar, Titel | Seite 1 ist gerade nicht abrufbar | Page 1 cannot be loaded right now | La page 1 n'est pas disponible pour le moment |
| Seite nicht abrufbar, Satz | Erneut laden. Bleibt der Fehler, die Verwaltung dieser Instanz informieren. | Load it again. If the error stays, tell the administrators of this instance. | Rechargez-la. Si l'erreur persiste, prévenez l'administration de cette instance. |
| Knopf Erneut laden | Erneut laden | Load again | Recharger |
| Kopie wird angelegt, Titel | Kopie wird angelegt | Creating the copy | Création de la copie |
| Kopie wird angelegt, Satz | Die Kopie entsteht im selben Ordner wie das Original. Das Original bleibt unverändert. | The copy is created in the same folder as the original. The original stays unchanged. | La copie est créée dans le même dossier que l'original. L'original reste inchangé. |
| Kopie angelegt, Titel | Kopie angelegt | Copy created | Copie créée |
| Kopie angelegt, Satz | Die Kopie „%s“ liegt neben dem Original. Die Zwischendaten dieser Prüfung sind gelöscht. | The copy "%s" is next to the original. The intermediate data of this review has been deleted. | La copie « %s » se trouve à côté de l'original. Les données intermédiaires de cette vérification ont été supprimées. |
| Link Kopie | Kopie in Dateien anzeigen | Show copy in Files | Afficher la copie dans Fichiers |
| Geändert, Titel | Die Datei wurde geändert | The file has changed | Le fichier a été modifié |
| Geändert, Satz | Nach dem Start wurde die Datei geändert oder neu eingelesen. Die Analyse galt dem alten Stand und wurde beendet. Die Datei in Dateien neu analysieren. | The file was changed or rescanned after the start. The analysis was for the old version and has been stopped. Analyse the file again in Files. | Le fichier a été modifié ou réanalysé après le lancement. L'analyse portait sur l'ancienne version et a été arrêtée. Relancez l'analyse dans Fichiers. |
| Gelöscht, Titel | Die Datei wurde gelöscht | The file was deleted | Le fichier a été supprimé |
| Gelöscht, Satz | Die Analyse wurde deshalb beendet, ihre Zwischendaten sind gelöscht. | The analysis was therefore stopped and its intermediate data deleted. | L'analyse a donc été arrêtée et ses données intermédiaires supprimées. |
| Download gesperrt, Titel | Für diese Freigabe ist die Prüfung gesperrt | Review is blocked for this share | La vérification est bloquée pour ce partage |
| Download gesperrt, Satz | Die Freigabe erlaubt inzwischen kein Herunterladen mehr, deshalb zeigt diese Seite die Datei nicht. Wer die Datei freigegeben hat, kann das Herunterladen erlauben. | The share no longer allows downloads, so this page does not show the file. The person who shared the file can allow downloads. | Le partage n'autorise plus le téléchargement, cette page n'affiche donc pas le fichier. La personne qui a partagé le fichier peut autoriser le téléchargement. |
| Nicht verfügbar, Titel | Diese Prüfung ist nicht verfügbar | This review is not available | Cette vérification n'est pas disponible |
| Nicht verfügbar, Satz | Sie wurde beendet, oder für die Datei besteht keine Berechtigung mehr. Die Datei in Dateien neu analysieren. | It has ended, or there is no longer permission for the file. Analyse the file again in Files. | Elle est terminée, ou l'autorisation pour le fichier n'existe plus. Relancez l'analyse dans Fichiers. |
| Abgelaufen, Titel | Diese Prüfung ist abgelaufen | This review has expired | Cette vérification a expiré |
| Abgelaufen, Satz | Prüfungen werden nach 14 Tagen gelöscht. Die Datei in Dateien neu analysieren. | Reviews are deleted after 14 days. Analyse the file again in Files. | Les vérifications sont supprimées après 14 jours. Relancez l'analyse dans Fichiers. |
| Backend nicht bereit, Titel | PII Redaction ist gerade nicht bereit | PII Redaction is not ready right now | PII Redaction n'est pas prêt pour le moment |
| Backend nicht bereit, Satz | Der Auftrag bleibt erhalten und läuft weiter, sobald das Backend wieder bereit ist. Bleibt der Zustand, die Verwaltung dieser Instanz informieren. | The job is kept and continues as soon as the backend is ready again. If this persists, tell the administrators of this instance. | La tâche est conservée et reprend dès que le backend est de nouveau prêt. Si cela persiste, prévenez l'administration de cette instance. |
| Stand nicht aktualisiert | Der Stand konnte nicht aktualisiert werden. Es wird weiter versucht. | The status could not be updated. Trying again. | L'état n'a pas pu être mis à jour. Nouvelle tentative en cours. |
| Sitzung abgelaufen | Die Sitzung ist abgelaufen. Die Seite neu laden und erneut anmelden. | The session has expired. Reload the page and log in again. | La session a expiré. Rechargez la page et reconnectez-vous. |
| Knopf Seite neu laden | Seite neu laden | Reload page | Recharger la page |
| Kopie nicht angefordert (POST-Fehler) | Die Kopie konnte nicht angefordert werden. Erneut versuchen. | The copy could not be requested. Try again. | La copie n'a pas pu être demandée. Réessayez. |

Fehlgeschlagen je Grund (Fehlerkarte, Titel / Satz):

| Grund | DE | EN | FR |
|-------|----|----|----|
| `render_failed` | Die Datei ließ sich nicht darstellen / Sie ist vielleicht beschädigt oder nutzt Funktionen, die die Umwandlung nicht kennt. Die Datei in ihrem Programm als PDF speichern und diese PDF analysieren. | The file could not be displayed / It may be damaged or use features the conversion does not know. Save the file as PDF in its program and analyse that PDF. | Le fichier n'a pas pu être affiché / Il est peut-être endommagé ou utilise des fonctions que la conversion ne connaît pas. Enregistrez le fichier en PDF dans son programme et analysez ce PDF. |
| `out_of_memory` | Der Server hatte nicht genug Arbeitsspeicher / Die Analyse wurde abgebrochen. Später neu starten. Bleibt der Fehler, die Verwaltung dieser Instanz informieren. | The server did not have enough memory / The analysis was stopped. Start it again later. If the error stays, tell the administrators of this instance. | Le serveur n'avait pas assez de mémoire / L'analyse a été interrompue. Relancez-la plus tard. Si l'erreur persiste, prévenez l'administration de cette instance. |
| `repeatedly_stuck` | Die Analyse kam mehrmals nicht voran / Sie wurde nach drei Versuchen beendet. Die Verwaltung dieser Instanz informieren. | The analysis got stuck several times / It was stopped after three attempts. Tell the administrators of this instance. | L'analyse s'est bloquée plusieurs fois / Elle a été arrêtée après trois tentatives. Prévenez l'administration de cette instance. |
| `backend_state_lost` | Die Zwischendaten der Analyse fehlen / Das Backend wurde vermutlich neu installiert oder zurückgesetzt. Die Datei in Dateien neu analysieren. | The intermediate data of the analysis is missing / The backend was probably reinstalled or reset. Analyse the file again in Files. | Les données intermédiaires de l'analyse sont manquantes / Le backend a probablement été réinstallé ou réinitialisé. Relancez l'analyse dans Fichiers. |
| `target_not_writable` | Die Kopie konnte nicht angelegt werden / Im Ordner des Originals fehlt die Berechtigung zum Anlegen von Dateien. Die Datei neu analysieren, sobald die Berechtigung besteht. | The copy could not be created / The folder of the original does not allow creating files. Analyse the file again once permission is granted. | La copie n'a pas pu être créée / Le dossier de l'original n'autorise pas la création de fichiers. Relancez l'analyse une fois l'autorisation accordée. |
| `unsupported_format` | Dieses Format wird nicht unterstützt / Analysiert werden nur PDF-, DOCX- und ODT-Dateien. | This format is not supported / Only PDF, DOCX and ODT files can be analysed. | Ce format n'est pas pris en charge / Seuls les fichiers PDF, DOCX et ODT peuvent être analysés. |
| jeder andere Grund | Die Analyse ist fehlgeschlagen / Die Datei in Dateien neu analysieren. Bleibt der Fehler, die Verwaltung dieser Instanz informieren. | The analysis failed / Analyse the file again in Files. If the error stays, tell the administrators of this instance. | L'analyse a échoué / Relancez l'analyse dans Fichiers. Si l'erreur persiste, prévenez l'administration de cette instance. |

Hinweis: Titel und Satz sind getrennte Katalogeinträge; der Schrägstrich trennt hier nur die Spalten.

### Fläche 3: Benachrichtigung

| Betreff | DE Betreff / Nachricht | EN | FR |
|---------|------------------------|----|----|
| `review_ready` | Eine Prüfung ist bereit / Die Prüfseite zeigt die Datei. | A review is ready / The review page shows the file. | Une vérification est prête / La page de vérification affiche le fichier. |
| `job_failed` | Eine Analyse ist fehlgeschlagen / Den Grund zeigt die Prüfseite. | An analysis failed / The review page shows the reason. | Une analyse a échoué / La page de vérification en indique la raison. |
| `job_stale` | Eine Analyse wurde beendet, weil die Datei geändert wurde / Die Datei in Dateien neu analysieren. | An analysis was stopped because the file changed / Analyse the file again in Files. | Une analyse a été arrêtée car le fichier a été modifié / Relancez l'analyse dans Fichiers. |
| `copy_created` | Eine Kopie liegt neben dem Original / Die Prüfseite verlinkt die Kopie. | A copy is next to the original / The review page links to the copy. | Une copie se trouve à côté de l'original / La page de vérification renvoie vers la copie. |

### Fläche 5: Admin-Statusbereich

| Schlüssel | DE | EN | FR |
|-----------|----|----|----|
| Sektionsname | PII Redaction | PII Redaction | PII Redaction |
| h2 | Verbindung zum Backend | Connection to the backend | Connexion au backend |
| `ok` | Beide Apps sind verbunden und haben die Version %s. | Both apps are connected and run version %s. | Les deux applications sont connectées et en version %s. |
| `version_patch_differs` | Beide Apps sind verbunden. Die Versionen unterscheiden sich nur in der letzten Stelle: diese App %1$s, Backend %2$s. Analysen laufen normal. Beim nächsten Update beide Apps auf dieselbe Version bringen. | Both apps are connected. Their versions differ only in the last part: this app %1$s, backend %2$s. Analyses run normally. Bring both apps to the same version at the next update. | Les deux applications sont connectées. Leurs versions ne diffèrent que par le dernier chiffre : cette application %1$s, backend %2$s. Les analyses fonctionnent normalement. Mettez les deux applications à la même version lors de la prochaine mise à jour. |
| `version_drift` | Die beiden Apps haben unterschiedliche Versionen: diese App %1$s, Backend %2$s. Solange sie nicht zusammenpassen, startet keine Analyse, und wartende Aufträge warten. Beide Apps auf dieselbe Version bringen. | The two apps run different versions: this app %1$s, backend %2$s. As long as they do not match, no analysis starts and queued jobs wait. Bring both apps to the same version. | Les deux applications ont des versions différentes : cette application %1$s, backend %2$s. Tant qu'elles ne correspondent pas, aucune analyse ne démarre et les tâches en attente patientent. Mettez les deux applications à la même version. |
| `backend_missing` | Die App „PII Redaction Backend“ ist nicht installiert. Ohne sie startet keine Analyse. Die App unter Apps installieren. | The app "PII Redaction Backend" is not installed. Without it, no analysis starts. Install the app under Apps. | L'application « PII Redaction Backend » n'est pas installée. Sans elle, aucune analyse ne démarre. Installez l'application dans Applications. |
| `backend_disabled` | Die App „PII Redaction Backend“ ist installiert, aber deaktiviert. Solange startet keine Analyse. Die App unter Apps aktivieren. | The app "PII Redaction Backend" is installed but disabled. Until it is enabled, no analysis starts. Enable the app under Apps. | L'application « PII Redaction Backend » est installée mais désactivée. En attendant, aucune analyse ne démarre. Activez l'application dans Applications. |
| `backend_unreachable` | Das Backend antwortet nicht. Solange startet keine Analyse. Unter Apps prüfen, ob „PII Redaction Backend“ läuft, und in den AppAPI-Einstellungen, ob der Deploy-Daemon erreichbar ist. | The backend does not answer. Until it does, no analysis starts. Check under Apps that "PII Redaction Backend" is running, and in the AppAPI settings that the deploy daemon can be reached. | Le backend ne répond pas. En attendant, aucune analyse ne démarre. Vérifiez dans Applications que « PII Redaction Backend » fonctionne, et dans les paramètres AppAPI que le démon de déploiement est joignable. |
| `no_app_api` | Die App AppAPI ist nicht aktiviert. Das Backend dieser App läuft nur über AppAPI. AppAPI unter Apps aktivieren und einen Deploy-Daemon einrichten. | The AppAPI app is not enabled. The backend of this app only runs through AppAPI. Enable AppAPI under Apps and set up a deploy daemon. | L'application AppAPI n'est pas activée. Le backend de cette application ne fonctionne qu'avec AppAPI. Activez AppAPI dans Applications et configurez un démon de déploiement. |
| Neuprüfung gescheitert | Der Zustand konnte nicht neu geprüft werden. Angezeigt ist der Stand beim Laden der Seite. | The state could not be checked again. Shown is the state from when the page was loaded. | L'état n'a pas pu être vérifié de nouveau. L'affichage correspond à l'état au chargement de la page. |
| Banner-Aktion | Apps öffnen | Open Apps | Ouvrir Applications |
| Versionszeile | Diese App: %1$s · Backend: %2$s | This app: %1$s · Backend: %2$s | Cette application : %1$s · Backend : %2$s |
| Version unbekannt | nicht bekannt | unknown | inconnue |
| Zuletzt geprüft | Zuletzt geprüft: %s | Last checked: %s | Dernière vérification : %s |
| Knopf Prüfen | Erneut prüfen | Check again | Vérifier à nouveau |
| Knopf während Prüfung | Wird geprüft… | Checking… | Vérification… |
| Backend-Beschreibung (ExApp-Einstellungen) | Diese App ist das Backend von PII Redaction und braucht die App „PII Redaction“. Der Zustand beider Apps steht unter Verwaltung, PII Redaction. | This app is the backend of PII Redaction and needs the app "PII Redaction". The state of both apps is shown under Administration, PII Redaction. | Cette application est le backend de PII Redaction et nécessite l'application « PII Redaction ». L'état des deux applications figure dans Administration, PII Redaction. |

Anführungszeichen: DE „…“ (U+201E, U+201C), EN "…", FR « … » mit U+00A0 innen.

Hinweis für den Planer: PHP-Texte in `php/l10n/{de,de_DE,en,fr}.json/.js`, Vue-Texte in denselben Katalogen (App-ID `pii_redaction`, `addInitScript` lädt sie vor der Dateiaktion), Backend-Beschreibung in `backend/l10n/`. Der Dreisprachigkeits-Test (AVS `tests/test_trilingual.py`) prüft alle Kataloge und zusätzlich `php/src/**/*.{ts,vue}` auf hart codierte Texte; er lehnt U+2013/U+2014 und Emojis in allen Sprachen ab und verlangt in `fr` U+00A0 vor `:` `;` `?` `!` und innerhalb `« »` (Platzhalter und URLs ausgenommen). Umlaut-Audit (keine ASCII-Ersatzschreibung wie "ae", "oe", "ue", "ss" für ß in DE-Texten) gehört in denselben Test.

---

## Barrierefreiheit (WCAG 2.1 AA, BITV 2.0)

- **Tastatur:** Jede Aktion per Tab erreichbar; Reihenfolge = DOM-Reihenfolge oben. Dateiaktion über das Aktionsmenü der Zeile (Server-Komponente, tastaturbedienbar). Keine eigenen Tastenkürzel (kein `hotkey` an der Dateiaktion, Konflikt mit Dateien-Kürzeln).
- **Fokus:** Server-Fokusring sichtbar, nie entfernt. Beim Seitenaufruf wird der Fokus nirgends verschoben. Festgelegte Fokuspunkte: nach "Platzhalter-Kopie anlegen" die neue Statuszeile bzw. Ergebniskarte; im Admin nach "Erneut prüfen" `#pii-backend-state`. Abfrage-getriebene Wechsel (ohne Nutzeraktion) verschieben den Fokus nicht, sie werden nur angesagt.
- **Ansagen:** Statusbereich `role="status"`/`aria-live="polite"` (nur Wechsel von Status oder Stufe); Fehlerkarten der Prüfseite mit `show-alert` nur bei nutzerausgelösten Fehlern (POST), sonst polite; Ladezustand über `aria-busy`.
- **Toast (2.2.1 Timing):** Erfolg 10 s mit Schließen-Knopf, Fehler bleibt bis zum Schließen; gleichwertige Wege zur Prüfseite (erneuter Klick, Benachrichtigung).
- **Bild (1.1.1):** `alt` "Seite 1 von {Seitenzahl}" wie in der Copy-Tabelle, ohne Dateinamen; der Inhalt der Seite ist in Phase 1 nicht als Text verfügbar, das sagt die Hinweiskarte "Vorschau ohne Erkennung" aus. Ab Phase 9 bekommt die Prüfseite eine Textliste der Funde als gleichwertigen Weg.
- **Kontrast (1.4.3, 1.4.11):** nur Server-Variablen; Text in Statusflächen nie in `--color-text-maxcontrast`; 1-px-Rahmen des Seitenbilds `--color-border` ist Schmuck, nicht Bedeutungsträger. Hoher-Kontrast-Theme muss lesbar bleiben.
- **Fortschritt:** `NcProgressBar` mit `aria-label`; Seitenzähler als Text daneben.
- **Seitentitel (2.4.2):** siehe Fläche 2.
- **Zoom und Umbruch (1.4.4, 1.4.10):** bei 320 px Breite (400 % Zoom) kein waagrechtes Scrollen außer im Bild selbst; Bild skaliert auf Spaltenbreite.
- **Sprache (3.1.1):** Seite folgt der Nutzersprache des Servers (`lang` am `html`).
- Icons dekorativ (`aria-hidden`), Bedeutung immer im Text. Keine Knöpfe ohne sichtbaren Text in Phase 1.

---

## Prüfvertrag für die Abnahme (Playwright)

Grundlage: AVS `ci/playwright/` (Projekte je Breite und Theme, Sprache über eigene Nutzer, `helpers.ts`), `@playwright/test` 1.65.0, gegen NC 33, 34, 35 im Workflow `deploy-harp.yml`.

### Raster

- **EN (Nutzer alice, Admin dora):** 375, 768, 1280 px, jeweils hell und dunkel, zusätzlich hoher Kontrast bei 1280 px: 7 Projekte.
- **DE (Nutzer elke, `lang de_DE`, `locale de_DE`) und FR (Nutzer fleur, `lang fr`, `locale fr_FR`):** je `w375-light` und `w1280-dark`. Sprache wird vor dem ersten Login per `occ user:setting` gesetzt (AVS 1fb003d). Zusätzlich je ein Projekt mit `lang de` (du-Katalog) für `w375-light`, damit `de` und `de_DE` beide sichtbar abgenommen werden.
- **Jede Fläche und jeder Zustand unten hat in jedem dieser Projekte einen Screenshot** (nicht nur EN), damit Umlaute, ß, „…“, « … » und die geschützten Leerzeichen des Französischen sichtbar abgenommen werden. Sprache, Breite und Theme stehen im Dateinamen.

### Bereitschaft vor jedem Screenshot (keine Spinner, keine halben Bilder)

1. `await page.evaluate(() => document.fonts.ready)`.
2. Für jedes `img` im Prüfbereich: `img.complete && img.naturalWidth > 0` und `await img.decode()`; `figure` ohne `aria-busy`.
3. Kein sichtbares `NcLoadingIcon` innerhalb `#pii-review` außer in Zuständen, deren Vertrag es zeigt (Warteschlange, Lauf, Kopie wird angelegt); dort ist der Spinner im Screenshot maskiert (`mask`) und die Animation über `animations: 'disabled'` angehalten.
4. Toasts: Screenshot erst, wenn der Toast vollständig eingeblendet ist; danach schließen, damit er nicht in den nächsten Screenshot ragt.
5. Abfrage steht still: in Endzuständen von selbst; in Lauf-Zuständen wird die Status-Route per `page.route` mit Werten **aus der geschlossenen Liste** beantwortet (nur für das Bild; der echte Durchlauf wird getrennt im Integrationsschritt belegt).

### Screenshots (Pflicht, je Projekt)

| Fläche | Zustand | Herstellung |
|--------|---------|-------------|
| Dateien | Aktionsmenü einer PDF-Zeile offen, Eintrag "Schwärzen / Pseudonymisieren" sichtbar | Seed-Datei, Menü über `data-cy-files-list-row-actions` |
| Dateien | Toast "als Nächstes" | erster Start |
| Dateien | Toast "n davor" (Plural) | Backend per `app_api:app:disable` angehalten, zwei Aufträge vorher |
| Dateien | Toast "läuft schon" | zweiter Klick |
| Dateien | Toast Backend nicht bereit | Backend deaktiviert |
| Dateien | Toast Download gesperrt | per API ausgelöst (Aktion ist dort ausgeblendet): `POST /jobs` aus der Seite heraus mit Freigabe-Datei, Toast-Funktion des Moduls; dazu Screenshot, dass die Aktion im Menü fehlt |
| Dateien | Toast nicht verfügbar, Format, allgemein | per `page.route` erzwungene Antwort |
| Dateien | Platzhalter-Kopie neben dem Original in der Liste (`Name_geschwärzt.pdf` bzw. `_redacted`, `_caviardé` je Sprache) und Kollisionsfall `(2)` | nach zwei Durchläufen |
| Prüfseite | Warteschlange (als Nächstes und n davor), Warteschlange mit Backend nicht bereit | Backend angehalten |
| Prüfseite | Lauf: `waiting`, `fetching`, `converting`, `rendering` mit Balken | `page.route` |
| Prüfseite | Bereit mit Seite 1 für **PDF, DOCX und ODT** | echter Durchlauf |
| Prüfseite | Seite nicht abrufbar | Bild-Route per `page.route` 502 |
| Prüfseite | Kopie wird angelegt, Kopie angelegt | echter Durchlauf |
| Prüfseite | Ungültig, Original geändert | WebDAV-`PUT` nach `review` |
| Prüfseite | Original gelöscht | WebDAV-`DELETE` |
| Prüfseite | Download gesperrt | Freigabe nachträglich ohne Download |
| Prüfseite | Fehlgeschlagen: `render_failed`, `out_of_memory`, `repeatedly_stuck`, `backend_state_lost`, `target_not_writable`, sonstiger Grund | `page.route` bzw. Initialzustand per Test-Saat in der DB (nur Werte der Liste) |
| Prüfseite | Abgelaufen | Saat in der DB |
| Prüfseite | Nicht verfügbar als fremder Nutzer (bob), als carol mit ACL `-read` im Gruppenordner, nach entzogener Freigabe | echte Rechte |
| Prüfseite | Stand nicht aktualisiert, Sitzung abgelaufen | `page.route` 503 bzw. 401 |
| Benachrichtigung | Popover mit `review_ready`, `job_failed`, `job_stale`, `copy_created` | echter Durchlauf bzw. Saat; Notifications-App ausgecheckt (Pitfall A) |
| Platzhalter-Kopie | erste Seite der Kopie als Bild | Kopie per WebDAV holen, im Container rendern oder im Browser über die Server-Vorschau öffnen |
| Admin | `ok`, `version_patch_differs`, `version_drift`, `backend_missing`, `backend_disabled`, `backend_unreachable`, `no_app_api`, Neuprüfung gescheitert, Knopf während Prüfung | Drift-Schritte 1 bis 4 wie AVS; `no_app_api` über `app:disable app_api` |

### Pflicht-Assertions (zusätzlich zu den Bildern)

- **"Apps öffnen"** existiert in `version_drift`, `backend_missing`, `backend_disabled`, `backend_unreachable`, `no_app_api`; `href` enthält auf NC 33 die Route von `settings.AppSettings.viewApps`, ab NC 34 die von `appstore.page.viewApps`; Aufruf als Admin liefert 200; Link per Tab erreichbar.
- **Bannertextfarbe:** In jedem Admin-Banner ist `getComputedStyle(title).color` und `getComputedStyle(text).color` gleich dem berechneten Wert von `var(--color-<status>-text)` und ungleich `var(--color-text-maxcontrast)`. Auf der Prüfseite ist der Kartentext gleich `var(--color-main-text)`.
- **Abstand:** Abstand von Banner-Unterkante bis Versionszeile-Oberkante im Admin = 16 px; Statuskarte bis nächster Block auf der Prüfseite = 16 px (Toleranz 1 px).
- **Datenschutz im DOM:** Im Zustand "Nicht verfügbar" und "Original gelöscht" kommt der Dateiname weder im DOM noch im Dokumenttitel noch im Initialzustand vor. Benachrichtigungen (OCS `notifications/api/v2`) enthalten weder Dateiname noch Kanarie.
- **Header:** Seitenbild und Status-Antwort tragen `Cache-Control: private, no-store`; Bild `X-Content-Type-Options: nosniff`.
- **Dateiaktion:** sichtbar für PDF, DOCX, ODT; nicht für TXT, Ordner, Mehrfachauswahl, Papierkorb, Datei aus Freigabe mit Download-Sperre, öffentliche Freigabeseite.
- **Kopie:** Name je Sprache exakt (`_geschwärzt`, `_redacted`, `_caviardé`, NFC), zweiter Durchlauf ergibt `(2)`; Original unverändert (Etag und sha256 gleich).
- **Fokus:** nach "Platzhalter-Kopie anlegen" steht der Fokus in `#pii-review-state`; nach "Erneut prüfen" auf `#pii-backend-state`.
- **Kein Inhalt außer Bild:** kein Text aus dem Dokument im DOM der Prüfseite (Kanarie nicht im DOM).

Danach `impeccable critique` und `impeccable audit`, dann Owner-Abnahme gemeinsam per Playwright. In dieser Recherche wurden kein Browser und kein Docker-Stack gestartet (RAM-Vorgabe).

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | keine (shadcn nicht verwendet) | not applicable |
| Drittanbieter | keine | not applicable |

npm-Pakete nur aus der Research-Liste (`@nextcloud/files` 4.1.1, `@nextcloud/vue` 9.14.1, `@nextcloud/dialogs` 8.0.0, `@nextcloud/axios` 2.6.0, `@nextcloud/router` 3.2.0, `@nextcloud/l10n` 3.4.1, `@nextcloud/initial-state` 3.0.0, `vue` 3.5.45, dev `@nextcloud/vite-config` 2.5.4, `vite` 7.3.7), alle exakt gepinnt und wortgleich Abhängigkeiten von `nextcloud/server`; `vue-material-design-icons` kommt als Abhängigkeit von `@nextcloud/vue` mit und wird bei direktem Import exakt in der dort verlangten Version gepinnt. Kein `postinstall` (Research). Sammel-Checkpoint vor dem ersten `npm install` wie in der Research empfohlen.

---

## Offene Owner-Fragen (mit Empfehlung)

Die Vorgaben oben folgen jeweils der Empfehlung; ändert der Owner etwas, passt der Planer nur die betroffene Zeile an.

1. **Nach dem Start in Dateien bleiben (Toast mit Link) statt direkt auf die Prüfseite zu springen?** Empfehlung: in Dateien bleiben. Die Analyse läuft im Hintergrund, die Benachrichtigung holt den Nutzer zurück; ein Sprung unterbräche die Arbeit in Dateien.
2. **Icon `eye-off-outline` für die Dateiaktion?** Empfehlung: ja, allgemein verstandenes Zeichen für "verbergen", passt zu Schwärzen und Pseudonymisieren; Alternative `shield-account-outline`.
3. **`de` und `de_DE` mit demselben unpersönlichen Text?** Empfehlung: ja (AVS- und Findling-Muster). Keine Anrede, also in der du- und in der Sie-Fassung korrekt, und ein Text für beide Kataloge.
4. **Text des Platzhalters "Vorschau ohne Erkennung" auf der Prüfseite** (statt das Fehlen der Erkennung zu verschweigen)? Empfehlung: ja, ehrliche Zustände; Phase 1 geht nicht in den Store.
5. **Kopie bei DOCX/ODT in Phase 1 als `.pdf`?** Empfehlung: ja, die Platzhalter-Kopie ist eine PDF; die DOCX/ODT-Ausgabe mit gleicher Endung kommt mit der echten Schwärzung (Phase 7), die zusätzliche PDF-Ausgabe bleibt dann `.pdf`.
6. **Fehler-Toasts bleiben bis zum Schließen stehen?** Empfehlung: ja (BITV, Fehlertexte sind zwei Sätze lang).

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: FLAG (34 px als Server-Vorgabe erklärt)
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-11-07 (gsd-ui-checker, 4 Empfehlungen: alt ohne Dateinamen und FR vereinheitlicht, 34 px erklärt; Aktionstexte und U+00A0-Nachweis gehen in den Plan)
