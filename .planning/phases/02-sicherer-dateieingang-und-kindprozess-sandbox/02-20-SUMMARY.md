---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 20
subsystem: php-admin
tags: [safe-01, d-02-11, admin, l10n, sandbox, tdd]
requires: [02-01, 02-14, 02-18, 02-19]
provides: [ExAppService status sandbox, ExAppService::degradedLayers, backendState sandboxDegraded, admin/state sandboxDegraded, Admin-Hinweisbereich pii-sandbox-state]
affects: [02-24, 02-25]
tech-stack:
  added: []
  patterns: [Container-Feld nur als feste Wörter, sonst null; Hinweiszeilen serverseitig, JS schaltet nur hidden]
key-files:
  created: []
  modified:
    - php/lib/Service/ExAppService.php
    - php/lib/Controller/SettingsController.php
    - php/lib/Settings/Admin.php
    - php/templates/admin.php
    - php/src/admin.ts
    - php/css/admin.css
    - php/l10n/de.json
    - php/l10n/de_DE.json
    - php/l10n/en.json
    - php/l10n/fr.json
    - php/l10n/de.js
    - php/l10n/de_DE.js
    - php/l10n/en.js
    - php/l10n/fr.js
    - php/tests/Unit/ExAppServiceTest.php
    - php/tests/Unit/SettingsControllerTest.php
    - php/tests/Unit/AdminSettingsTest.php
decisions:
  - "sandboxDegraded wird bei jeder Bestimmung neu aus /status gelesen; der gemerkte Befund (60 s) trägt die Liste mit, aber nur aus den drei festen Wörtern, sonst null"
  - "Zwei Banner im Hinweisbereich: Warnung für seccomp/Landlock mit gemeinsamer Abhilfe (einmal statt doppelt), Fehler für die Schutzschicht mit eigener Abhilfe, weil dann jede Analyse fehlschlägt"
  - "Unbekannter Schutzzustand (null) zeigt keinen Hinweis; die Zustandsbanner nennen dann ohnehin, dass der Container nicht antwortet"
  - "Kataloge vor der UI committet wie in 02-18, damit jeder Commit die Text-Gates besteht"
metrics:
  completed: 2026-11-18
  tasks: "3/3"
---

# Phase 2 Plan 20: Admin-Hinweis zum geminderten Schutz Summary

Der Admin-Bereich zeigt jetzt, wenn der Container seccomp oder Landlock nicht hat oder die Schutzschicht für Hilfsprozesse nicht lädt, je Schicht eine Zeile im freigegebenen Wortlaut samt Abhilfe (D-02-11). PHP übernimmt das Feld `sandbox` aus `/status` nur mit den festen Wörtern und gibt die fehlenden Schichten als `sandboxDegraded` (Liste aus `seccomp`, `landlock`, `jail`) an Template und `admin/state` weiter. Ein im Betrieb gesetztes `jail failed` (Exit 71, `mark_jail_failed()` aus 02-14/02-19) erscheint beim nächsten "Erneut prüfen" ohne Neuladen.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Task 1 RED | 50b4b4b | test(02-20): status keeps the sandbox as fixed words and the admin state names missing layers |
| Task 1 GREEN | c81108d | feat(02-20): the admin state knows the protection layers only as fixed words |
| Task 3 Kataloge | b4b5078 | feat(02-20): catalogues de, de_DE, en and fr carry the approved notice on reduced protection |
| Task 2 Template und Skript | 70406d3 | feat(02-20): the admin section shows reduced protection with its remedy |

## Umsetzung

- `ExAppService`: Konstanten `SANDBOX_LAYER_VALUES`, `SANDBOX_JAIL_VALUES`, `SANDBOX_LAYERS`; `CHILD_KINDS` um `precheck` und `sanitize`. `sandbox(mixed)` prüft alle vier Felder (Wörter strikt, `landlockAbi` echtes int 0 bis 64, kein bool, kein String), sonst null. `degradedLayers(?array)` liefert `[]` bei voller Isolation, null bei unbekanntem Zustand. `determineState` setzt `sandboxDegraded` aus dem frischen `status()`; `rememberedState` übernimmt die Liste nur aus den festen Wörtern ohne Doppelte.
- `SettingsController::state` gibt `sandboxDegraded` mit aus (immer `backendState(true)`, also frisch). `Admin::getForm` übergibt die Liste, im Fehlerfall null.
- `admin.php`: `<div id="pii-sandbox-state">` innerhalb des Zustandsbereichs (role status, aria-live polite), darin Banner `data-sandbox="layers"` (Warnung, Zeilen `data-layer="seccomp"` und `"landlock"`, gemeinsame Abhilfe) und `data-sandbox="jail"` (Fehler, Zeile `data-layer="jail"`, eigene Abhilfe). Alle Texte über `$l->t()` und `p()`, MDI-Pfade wie die übrigen Banner. Das Template filtert die Liste selbst nochmals auf die drei Wörter.
- `admin.ts`: `showSandbox()` setzt bei jeder Antwort von `admin/state` nur `hidden` an Zeilen, Bannern und Bereich; kein Markup, kein innerHTML.
- `admin.css`: Stapelregel `.pii-admin__sandbox` mit Server-Variablen; `#pii-admin [hidden]` greift weiter.

## Wortlaute (02-TEXTS.md Gruppe 6, wörtlich)

de_DE ist wortgleich zu de. Abgleich per eigenem Skript, das die Tabelle direkt aus 02-TEXTS.md liest: 5 Zeilen, 20 Werte, 0 Abweichungen.

| Schlüssel (EN) | DE / de_DE | FR |
|---|---|---|
| Network block for helper processes not available (seccomp). Analyses run with reduced protection. | Netzsperre für Hilfsprozesse nicht verfügbar (seccomp). Analysen laufen mit geminderter Schutzwirkung. | Blocage réseau des processus auxiliaires indisponible (seccomp). Les analyses fonctionnent avec une protection réduite. |
| File access restriction for helper processes not available (Landlock). Analyses run with reduced protection. | Dateizugriffssperre für Hilfsprozesse nicht verfügbar (Landlock). Analysen laufen mit geminderter Schutzwirkung. | Restriction d'accès aux fichiers des processus auxiliaires indisponible (Landlock). Les analyses fonctionnent avec une protection réduite. |
| The protection layer for helper processes could not be loaded. Analyses fail until this is fixed. | Die Schutzschicht für Hilfsprozesse ließ sich nicht laden. Bis zur Behebung schlagen Analysen fehl. | La couche de protection des processus auxiliaires n'a pas pu être chargée. Les analyses échouent jusqu'à la correction. |
| Run the container with seccomp and Landlock enabled (current Linux kernel, default security profile of the container runtime). | Den Container mit aktiviertem seccomp und Landlock betreiben (aktueller Linux-Kernel, Standard-Sicherheitsprofil der Container-Laufzeit). | Exécutez le conteneur avec seccomp et Landlock activés (noyau Linux récent, profil de sécurité par défaut de l'environnement de conteneurs). |
| Restart the backend container and check its log. | Den Backend-Container neu starten und sein Protokoll prüfen. | Redémarrez le conteneur du backend et consultez son journal. |

## Prüfung

- Lokale Gates grün vor jedem Commit: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture, ganze Suite `1434 passed, 44 skipped` (unverändert, keine neuen Python-Tests), `npm run typecheck`, `npm run build`, `scripts/l10n_js.py --check`.
- `test_trilingual.py`, `test_ui_assets.py`, `test_public_texts.py`: 56 passed. Positivkontrolle: Schlüssel "Network block ..." aus fr.json entfernt, `test_every_text_the_php_app_uses_is_in_every_catalogue` meldet genau diesen Text; danach Datei wiederhergestellt.
- Gedankenstriche in `php/l10n/*.json`: 0 je Datei.
- Akzeptanz: `'sanitize'` in ExAppService.php 1, `sandboxDegraded` in SettingsController.php und Admin.php je mindestens 1, `pii-sandbox-state` in admin.php 1, `innerHTML` in admin.ts 0, `data-layer="jail"` in admin.php 1.
- PHPUnit neu: ExAppServiceTest (Übernahme, 10 fremde Formen, ABI 64, Kindarten precheck/sanitize/rocket, 5 Ausfallkombinationen, unbekannt null, Laufzeitfall ok dann failed, gemerkter Befund mit fremdem Wort), SettingsControllerTest (Liste, leer, null, zwei Abrufe ok dann jail), AdminSettingsTest (Form übergibt Liste, Fehlerfall null, Template für volle Isolation, jede Schicht, unbekannt, fremde Wörter, Abhilfe je Banner). **Lokal nicht gelaufen**, PHP ist nicht installiert; RED und GREEN belegt erst php.yml.

## Deviations from Plan

**1. [Rule 2] `php/css/admin.css` ergänzt.** Nicht in files_modified. Die zwei Banner im Bereich brauchen denselben Abstand wie die Zustandsbanner; eine Regel mit Server-Variablen, `#pii-admin [hidden]` bleibt wirksam.

**2. Aufteilung der Abhilfe.** Der Plan nennt "Abhilfe-Zeilen". Statt die seccomp/Landlock-Abhilfe zweimal zu zeigen, wenn beide fehlen, stehen beide Zeilen in einem Warnbanner mit einer Abhilfe; die Schutzschicht hat ein eigenes Fehlerbanner mit ihrer Abhilfe.

**3. Commit-Reihenfolge.** Kataloge (Task 3) vor Template und Skript (Task 2), wie in 02-18, damit jeder Commit die Text-Gates besteht. Die Template-Tests in AdminSettingsTest kamen mit dem Template-Commit, weil sie dessen Markup prüfen.

**4. Gemerkter Befund trägt die Liste.** Der Plan sagt nur "kein Zwischenspeicher hält den alten Zustand fest". `admin/state` fragt immer frisch; die Seite selbst nutzt wie bisher den Befund von höchstens 60 s, der die Liste jetzt mitführt (nur feste Wörter, sonst null).

## Offen (nur mit CI, Docker oder Playwright belegbar)

- PHPUnit (RED/GREEN der neuen Fälle) und `php -l`: nur php.yml, PHP ist lokal nicht installiert. Syntax nur durch Lesen geprüft.
- Echter Durchstich Container `/status` mit `sandbox` bis Admin-Seite, auch der Exit-71-Fall: Container-Test, Plan 02-24.
- UI-Sichtprüfung des Hinweisbereichs in drei Breiten, hell und dunkel: gemeinsam mit dem Owner per Playwright.
- SAFE-01 nicht als erledigt markiert: Container- und CI-Belege (02-21, 02-24) und die AR-Vorlage (02-25) fehlen noch.

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche. T-02-26: jede fehlende Schicht hat eine Zeile, auch jail failed im Betrieb (frische Abfrage bei jedem Recheck, Test mit zwei Abrufen). T-02-50: nur feste Wörter aus dem Container, das Template filtert erneut, Texte nur serverseitig, JS setzt nur `hidden`. Keine neuen Logzeilen.

## Self-Check: PASSED
