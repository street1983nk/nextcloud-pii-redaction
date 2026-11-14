---
name: PII Redaction
description: Dateiaktion, Prüfseite, Benachrichtigung und Admin-Statusbereich zum lokalen Finden und Schwärzen personenbezogener Daten. Gestaltet als Teil der Nextcloud-Oberfläche ohne eigene Marke.
colors:
  color-primary-element: "#00679e"
  color-primary-element-text: "#ffffff"
  color-main-background: "#ffffff"
  color-main-text: "#222222"
  color-text-maxcontrast: "#6b6b6b"
  color-background-hover: "#f5f5f5"
  color-border: "#ededed"
  color-error: "#ffe7e7"
  color-error-text: "#8a0000"
  color-warning: "#ffeec5"
  color-warning-text: "#664700"
  color-success: "#d8f3da"
  color-success-text: "#005416"
  color-info: "#d5f1fa"
  color-info-text: "#0066ac"
typography:
  headline:
    fontFamily: "var(--font-face)"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "var(--font-face)"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "var(--font-face)"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  small: "4px"
  element: "8px"
  container: "12px"
spacing:
  baseline: "4px"
  2x: "8px"
  4x: "16px"
  6x: "24px"
  clickable-area: "34px"
  coarse-pointer: "44px"
components:
  button-primary:
    backgroundColor: "{colors.color-primary-element}"
    textColor: "{colors.color-primary-element-text}"
    rounded: "{rounded.element}"
    height: "{spacing.clickable-area}"
  note-card-error:
    backgroundColor: "{colors.color-error}"
    textColor: "{colors.color-error-text}"
    rounded: "{rounded.container}"
    padding: "16px"
---

# Design System: PII Redaction

Folgt der Skill nextcloud-ui; diese Datei hat bei UI-Arbeit Vorrang vor der Skill. Der verbindliche Vertrag für Phase 1 mit allen Zuständen und Texten steht in `.planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-UI-SPEC.md`.

## Overview

Die App hat kein eigenes Erscheinungsbild und soll keins bekommen. Jede Oberfläche soll aussehen, als käme sie aus dem Nextcloud-Server selbst, und jedes Theming mitmachen: Akzentfarbe des Admins, hell, dunkel, hoher Kontrast. Die Hex-Werte im Frontmatter sind nur Referenzwerte des Standard-Themes und gehören nie in den Code.

Stufen der Oberfläche, in dieser Reihenfolge prüfen:

1. **Deklarative Einstellungen** (`backend/src/pii_redaction_backend/settings.py`): AppAPI rendert das Formular mit Nextcloud-Komponenten. Kein eigenes CSS, kein Build-Schritt.
2. **Eigene Seite mit Vue** nur wenn Stufe 1 nicht reicht: `@nextcloud/vue` 9, Komponenten statt Eigenbau, hier mit Vite in der PHP-App gebaut (`php/src/` nach `php/js/`).
3. **PHP-Templates** nur in der PHP-App `pii_redaction`.

PII Redaction nutzt Stufe 2 und 3 in der PHP-App `pii_redaction`: Vue 3 mit `@nextcloud/vue` 9 für Dateiaktion und Prüfseite, weil `@nextcloud/files` 4 ohnehin einen Build braucht und die Prüfseite später Liste, Kästchen und Tastaturbedienung trägt; ein PHP-Template für den Admin-Statusbereich, damit er ohne JavaScript lesbar bleibt (Muster aus Audio & Video Search). Die ExApp `pii_redaction_backend` hat nur deklarative Einstellungen und keine Routen für den Browser.

Flächen in Version 0.1.0, sonst keine:

1. Dateiaktion „Schwärzen / Pseudonymisieren“ in der Dateien-App mit Start-Rückmeldung als Toast
2. Prüfseite `/apps/pii_redaction/review/{jobId}` mit Status, Fortschritt, Warteschlange und Seite 1 als Bild
3. Benachrichtigung ohne Dateinamen, Link auf die Prüfseite
4. Platzhalter-Kopie neben dem Original (Name und Inhalt der einseitigen PDF)
5. Admin-Statusbereich unter Verwaltungseinstellungen, PII Redaction

**Key Characteristics:**
- Nur Nextcloud-CSS-Variablen, kein Farbliteral im Code.
- Abstände als Vielfache von `var(--default-grid-baseline)`.
- Schrift des Servers, zwei Gewichte (400, 700), keine Webfonts.
- Flach: keine Schatten, Zustände über Flächenwechsel.
- Icons aus Material Design Icons als Inline-SVG mit `fill="currentColor"` (Dateiaktion, Admin-Banner), Größe 20, keine Emojis; Statuskarten der Prüfseite nutzen die Icons von `NcNoteCard`.

## Colors

Die Palette ist die des Servers: neutrale Flächen, eine Akzentfarbe und vier Statuspaare.

### Primary
- **Theming-Akzent** (`--color-primary-element` mit `--color-primary-element-text`): nur für die eine Hauptaktion pro Bereich.
- **Heller Akzent** (`--color-primary-element-light` mit `--color-primary-element-light-text`): Zustände, keine Aufforderungen.

### Neutral
- **Seitengrund** (`--color-main-background`), **Haupttext** (`--color-main-text`), **gedämpfter Text** (`--color-text-maxcontrast`), **Hover-Fläche** (`--color-background-hover`), **Trennlinie** (`--color-border`).

### Statuspaare
- Fehler, Warnung, Erfolg, Hinweis jeweils als Paar `--color-<status>` und `--color-<status>-text`, Icon in `--color-element-<status>`. In Vue über `NcNoteCard`.

### Named Rules
**The Pair Rule.** Fläche und Text eines Status immer als Server-Paar, nie gemischt.

**The Never Color Alone Rule.** Farbe ist nie der einzige Träger: Icon und Satz gehören dazu.

## Typography

Schrift des Servers über `--font-face`. Rang über Gewicht, nicht über zusätzliche Größen: Headline 20 px, Body `--default-font-size`, Label `--font-size-small`.

## Layout

Eine Lesespalte, Abstände als `calc(var(--default-grid-baseline) * n)`. Klickflächen mindestens `--default-clickable-area`, bei `pointer: coarse` 44 px. Prüfbreiten 375, 768 und 1280 px.

## Elevation & Depth

**The Flat Rule.** Keine Schatten, keine Verläufe, kein Glas. Ein Zustandswechsel ist ein Flächenwechsel.

## Shapes

Radien nur über `--border-radius-small`, `--border-radius-element`, `--border-radius-container`. Keine Karten in Karten.

## Components

| Zweck | Komponente |
|---|---|
| Aktion | `NcButton` (variant primary nur für die Hauptaktion) |
| Hinweis, Warnung, Fehler, Erfolg | `NcNoteCard` |
| Laden | `NcLoadingIcon` |
| Leerer Zustand | `NcEmptyContent` |
| Schalter, Auswahl | `NcCheckboxRadioSwitch`, `NcSelect` |
| Dialog | `NcDialog` |
| Einstellungsblock | `NcSettingsSection` |

Jede Ansicht braucht die Zustände Laden, leer, Fehler, Erfolg und keine Berechtigung.

## Texte

- Begriffe: **Analyse** ist der Maschinenlauf, **Prüfung** die Seite für den Menschen, **Kopie** die Ergebnisdatei. Englisch analysis, review, copy; Französisch analyse, vérification, copie. „PII Redaction“, „PII Redaction Backend“ und „AppAPI“ werden nicht übersetzt.
- Kürze: zwei kurze Sätze nach dem Muster „Zustand. Folge oder Handlung.“, höchstens drei Sätze und 240 Zeichen je Katalogwert (Gate in `backend/tests/test_trilingual.py`). Kein Wert, der daneben schon steht, wird wiederholt; Versionen nur in der Versionszeile, nie im Banner.
- Deutsch unpersönlich im Infinitiv („Die Seite neu laden.“), damit `de` und `de_DE` denselben Text tragen. Französisch mit U+00A0 vor `:` `;` `?` `!` und innerhalb von « ».
- Kein Dateiname in Benachrichtigungen, Toasts, Fehlerkarten für fremde oder gelöschte Dateien und im Dokumenttitel solcher Seiten.
- Jeder sichtbare Text dreisprachig (Deutsch, Englisch, Französisch) über `l10n/` bzw. `t('pii_redaction', ...)`, nie hart codiert.
- Deutsch mit echten Umlauten, Satzanfang groß, kein Ausrufezeichen, keine Gedankenstriche, keine Emojis.
- Fehlertexte sagen, was passiert ist und was der Nutzer tun kann.

## Barrierefreiheit

Ziel WCAG 2.1 AA und BITV 2.0:

- Jede Aktion per Tab erreichbar, Reihenfolge gleich DOM-Reihenfolge, keine eigenen Tastenkürzel.
- Fokusring des Servers bleibt sichtbar. Fokus wandert nur nach einer Nutzeraktion: nach „Platzhalter-Kopie anlegen“ auf die neue Statuszeile, im Admin nach „Erneut prüfen“ auf `#pii-backend-state`.
- Statusbereiche mit `role="status"` und `aria-live="polite"`, angesagt wird nur ein Wechsel von Status oder Stufe; Ladezustand über `aria-busy`.
- Erfolgs-Toast 10 s mit Schließen-Knopf, Fehler-Toast bleibt bis zum Schließen; die Prüfseite ist auch über die Benachrichtigung und einen erneuten Klick erreichbar.
- Seitenbild mit `alt` „Seite 1 von {n}“ ohne Dateinamen; im Dunkelmodus nicht invertiert.
- Text in Statusflächen nie in `--color-text-maxcontrast`; Kontrast allein über Server-Variablen, auch im Theme mit hohem Kontrast.
- Bei 320 px Breite kein waagrechtes Scrollen außer im Bild.

## Do's and Don'ts

### Do:
- **Do** zuerst eine deklarative Einstellung oder eine Nc-Komponente suchen, bevor eigenes Markup entsteht.
- **Do** jede Ansicht hell, dunkel und mit hohem Kontrast bei 375, 768 und 1280 px per Playwright prüfen, danach `impeccable critique` und `impeccable audit`.
- **Do** Icon-Knöpfe mit `aria-label` versehen und den Fokusring sichtbar lassen.

### Don't:
- **Don't** Hex-, RGB- oder benannte Farben, eigene Schriften oder eigene Schatten.
- **Don't** Verläufe, Glassmorphism, zentrierte Hero-Blöcke, Karten in Karten.
- **Don't** `!important` gegen Server-Styles oder `outline: none`.
