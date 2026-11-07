---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 09
subsystem: php-frontend
tags: [vite, vue3, file-action, toast, review-page, admin-script, ui-gate]
requires: [01-03, 01-07, 01-08]
provides:
  - "php/package.json + package-lock.json mit exakten, Owner-freigegebenen Pins"
  - "Build js/pii_redaction-{init,review,admin}.mjs über @nextcloud/vite-config 2.5.4, CSS der Bibliotheken je Einstieg im Skript"
  - "Dateiaktion pii_redaction-start mit Start-Toast"
  - "ReviewPlaceholder.vue (alle Zustände der UI-SPEC Fläche 2) und css/review.css"
  - "admin.ts mit DOM-Vertrag für das Template aus Plan 11"
  - "backend/tests/test_ui_assets.py"
affects: [01-11, 01-13, 01-14, 01-16]
tech-stack:
  added: ["@nextcloud/files 4.1.1", "@nextcloud/vue 9.14.1", "@nextcloud/dialogs 8.0.0", "@nextcloud/axios 2.6.0", "@nextcloud/router 3.2.0", "@nextcloud/l10n 3.4.1", "@nextcloud/initial-state 3.0.0", "@nextcloud/auth 2.6.0", "vue 3.5.44", "@nextcloud/vite-config 2.5.4 (dev)", "vite 7.3.7 (dev)"]
  patterns:
    - "npm install/ci immer mit --ignore-scripts; Lockdatei hält alle transitiven Pakete"
    - "Texte nur über t('pii_redaction', '<Katalogschlüssel>'); %s/%1$s werden nach t() ersetzt (l10n kennt nur {name})"
    - "Admin: Server rendert alle Banner, Skript schaltet nur hidden und Text"
key-files:
  created:
    - php/package.json
    - php/package-lock.json
    - php/vite.config.ts
    - php/tsconfig.json
    - php/src/init.ts
    - php/src/startToast.ts
    - php/src/icon.svg
    - php/src/review.ts
    - php/src/ReviewPlaceholder.vue
    - php/src/admin.ts
    - php/css/review.css
    - backend/tests/test_ui_assets.py
  modified:
    - .github/workflows/php.yml
    - .gitignore
    - backend/tests/test_php_gates.py
key-decisions:
  - "typescript nicht als direkte devDependency (nicht in der Owner-Freigabe); Build läuft über esbuild ohne tsc, typescript 6.0.3 liegt nur transitiv im Lock"
  - "vue 3.5.44 statt 3.5.45 aus dem Plan (Owner-Pin 01-01)"
  - "inlineCSS mit relativeCSSInjection: Bibliotheksstile reisen je Einstieg im Skript, php/css enthält nur handgeschriebene Blätter"
  - "Admin-Banner nach AVS-Muster: alle sieben Zustände serverseitig, admin.ts schaltet data-state"
requirements-completed: []  # JOB-01/JOB-02 erst mit Playwright in der Dateien-App (Plan 16)
metrics:
  duration: "ca. 55 min"
  completed: 2026-11-07
  tasks: 3
  files: 15
---

# Phase 1 Plan 09: Browserseite Summary

Die PHP-App hat jetzt ihren Vite-Build mit drei Einstiegen: die Dateiaktion "Schwärzen / Pseudonymisieren" mit Start-Toast, die Platzhalter-Prüfseite als Vue-3-Komponente mit allen Zuständen der UI-SPEC und das Skript für "Erneut prüfen" im Admin-Bereich. `npm run build` läuft lokal, `php.yml` baut das Bundle in CI.

## Ergebnis

- **Task 1 (`d6843e1`):** `npm install --save-exact --ignore-scripts` nur mit den freigegebenen Paketen und Versionen; `@nextcloud/auth` 2.6.0 ist die Version aus `@nextcloud/files@4.1.1`, die 01-01 freigegeben hat. vue-Integrity im Lock gleich dem freigegebenen Wert (`sha512-dvvmaOCG...`). `init.ts` registriert `pii_redaction-start` (Icon MDI `eye-off-outline` mit `currentColor`, Pfad gegen `@mdi/js` 7.4.47 geprüft, order 60). `enabled` prüft Anmeldung, nicht Papierkorb, genau ein Knoten, Datei, Mime-Dreierliste, Leserecht, nachgebautes `isDownloadable` (unklare Freigabe-Attribute gelten als gesperrt), nicht verschlüsselt. `startToast.ts` baut Satz plus Link per `createElement`, Satz nach `reason`, Erfolg/Hinweis 10 s, Warnung/Fehler bis zum Schließen, kein Dateiname. `php.yml`: Node 22 per SHA (`actions/setup-node` v7.1.0, SHA gegen das Tag geprüft), `npm ci --ignore-scripts`, Build und `test -s` im Lint- und im PHPUnit-Job.
- **Task 2 (`73e459c`):** `ReviewPlaceholder.vue` mit DOM-Reihenfolge der UI-SPEC: h2 (Name oder "Prüfung"), Metazeile mit `<time datetime>` und `Intl.DateTimeFormat(getCanonicalLocale())`, `#pii-review-state` (`role="status"`, `aria-live="polite"`, `tabindex="-1"`), Balken und Seitenzähler außerhalb der Live-Region, Warnkarte Backend, Hinweiskarte, Aktionszeile mit `#pii-placeholder` und "In Dateien anzeigen", Figur mit Bild über `/review/{jobId}/page/1`, Platzhalterfläche und `aria-busy`. Abfrage alle 3 s in offenen Zuständen, Pause bei verdecktem Tab, Rückoff 3/6/12/30 s, 404 ergibt "nicht verfügbar", 401 "Sitzung abgelaufen" und Stopp. Bildfehler fragt sofort den Status. Fokus nach dem POST auf die Statuszeile. `review.css` nur mit Server-Variablen, Bild nie invertiert.
- **Task 3 (`e22b504`):** `admin.ts` (siehe DOM-Vertrag in der Datei) und `test_ui_assets.py` mit 14 Regeln und 7 Selbsttests, darunter "jedes `pii_redaction-<name>`-Skript ist ein Vite-Einstieg".

Gates in `backend/` vor jedem Commit: ruff, ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 382 passed / 3 skipped. Alle 71 `t()`/`n()`-Texte der Quellen stehen im Katalog (geprüft mit `used_texts`), kein Katalog-Nachtrag nötig.

## Deviations from Plan

### Auto-fixed Issues

**1. [Owner-Regel] vue 3.5.44 statt 3.5.45**
- Der Plan nennt 3.5.45; freigegeben ist 3.5.44 (01-01-SUMMARY).

**2. [Owner-Regel] keine direkte `typescript`-devDependency**
- **Issue:** Der Plan verlangt `--save-dev typescript`; typescript stand nicht in der Freigabeliste.
- **Fix:** Nicht installiert. Vite übersetzt TS und `<script setup lang="ts">` über esbuild, Props sind Laufzeit-Deklarationen. `tsconfig.json` liegt für Editoren bei. typescript 6.0.3 kommt transitiv über `@nextcloud/vite-config` (vite-plugin-dts) in den Lock. Ein Typprüf-Schritt (`tsc --noEmit`) braucht vorher eine Owner-Freigabe.

**3. [Rule 3] Gate-Regel 8 scannte das Build-Ergebnis `php/js/`**
- **Issue:** Gebündelte Bibliotheken enthalten U+2013/U+2014; `php/js/` ist git-ignoriert.
- **Fix:** `js` in `SKIPPED_DIRECTORIES` von `test_php_gates.py` (Quellen in `php/src` werden weiter geprüft).
- **Commit:** d6843e1

**4. [Rule 3] Bibliotheks-CSS landete in `php/css/`**
- **Fix:** `inlineCSS: { relativeCSSInjection: true }` (je Einstieg im Skript); `.gitignore` deckt `php/css/pii_redaction-*.css` und `*.chunk.css` zusätzlich ab, `test_ui_assets.py` übergeht solche Dateien.
- **Commit:** d6843e1, e22b504

**5. [Rule 1] review.css gegen das eigene Asset-Gate**
- `!important` an `[hidden]` und `outline: none` an `:focus` entfernt (nur `:focus-visible` bleibt).
- **Commit:** e22b504

**6. Admin-Banner nach AVS-Form**
- Der Plan sagt "ersetzt Banner per textContent und Klassen". Umgesetzt wie AVS: der Server rendert jeden Zustand als eigenes Banner (`data-state`), das Skript schaltet nur `hidden`. Ergebnis gleich, aber keine Bannertexte im Skript. Plan 11 muss die Banner so rendern (DOM-Vertrag im Kopf von `admin.ts`).

## Hinweise für spätere Pläne

- **Plan 11:** Template braucht `#pii-admin`, `#pii-backend-state` (`role="status" aria-live="polite" tabindex="-1"`), je Zustand ein Banner mit `data-state`, `#pii-recheck-failed` (hidden), `.pii-version-own`, `.pii-version-backend`, `<time id="pii-checked-at">`, `#pii-recheck` mit `#pii-recheck-label`. Antwort von `admin/state`: `state`, `ownVersion`, `backendVersion`, `checkedAt`, optional `checkedAtText`. Skript per `Util::addScript('pii_redaction', 'pii_redaction-admin')`.
- **Plan 13:** Startzustand `review` mit `state` (`unavailable` für 404), `recheck` (`download_blocked` zeigt die Sperrkarte), `jobId`, `fileId`, `fileName`, `status`, `stage`, `reason`, `ahead`, `pagesDone`, `pagesTotal`, `createdAt`, `backendReady`, `outputFileId`, `outputName`, `image`. `Util::addScript('pii_redaction', 'pii_redaction-review')` und `Util::addStyle('pii_redaction', 'review')`. Die Status-Route meldet keine Download-Sperre; ein Bildfehler bei Sperre zeigt deshalb "Seite nicht abrufbar", erst ein Neuladen zeigt die Sperrkarte.
- **Plan 14:** `Util::addInitScript('pii_redaction', 'pii_redaction-init')` im Listener für `LoadAdditionalScriptsEvent`.
- `npm audit` meldet bekannte Hinweise in transitiven Paketen (`elliptic` über vite-plugin-node-polyfills, `minimatch`); nur Build-Zeit bzw. Polyfill, nicht behoben (kein Paketwechsel ohne Owner).

## Known Stubs

Keine. Die Prüfseite zeigt bewusst "Vorschau ohne Erkennung" (Owner-Entscheid Phase 1).

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-09-01 bis -04 mitigiert (nur Textbindung plus Gate, `@nextcloud/axios` mit Request-Token, Toast ohne Namen, exakte Pins plus Lock plus `npm ci --ignore-scripts`).

## Self-Check: PASSED

- Dateien vorhanden: php/package.json, php/package-lock.json, php/vite.config.ts, php/src/{init,startToast,review,admin}.ts, php/src/ReviewPlaceholder.vue, php/src/icon.svg, php/css/review.css, backend/tests/test_ui_assets.py
- Commits vorhanden: d6843e1, 73e459c, e22b504

## Nachtrag Owner-Freigabe typescript (2026-11-07)

Owner-Antwort im Claude-Code-Terminal, vom Koordinator übermittelt, auf die Frage nach `typescript` als direkter devDependency: "Freigeben (Empfohlen)".

Umsetzung (`9cd4891`): `typescript` 6.0.3 mit `--save-exact --save-dev --ignore-scripts` (Quelle github.com/microsoft/TypeScript, kein postinstall, Integrity `sha512-y2TvuxSZPDyQakkFRPZHKFm+KKVqIisdg9/CZwm9ftvKXLP8NRWj38/ODjNbr43SsoXqNuAisEf1GdCxqWcdBw==`, dieselbe Version, die vorher transitiv im Lock lag). Neues Skript `npm run typecheck` (`tsc --noEmit -p tsconfig.json`), in `php.yml` im Lint-Job vor dem Build. Damit tsc ohne `@types/node` (nicht freigegeben) prüft, nennt `vite.config.ts` die Einstiege als relative Pfade statt über `node:path`; `src/shims-vue.d.ts` deklariert `.vue`-Importe (die Skriptblöcke der Komponenten prüft weiter nur der Vite-Build, `vue-tsc` ist nicht freigegeben). Lokal: `tsc` ohne Fehler, Gegenprobe mit einer absichtlich falschen Zuweisung ergab einen TS-Fehler. `test_ui_assets.py` liest die Einstiege jetzt aus der neuen Form.
