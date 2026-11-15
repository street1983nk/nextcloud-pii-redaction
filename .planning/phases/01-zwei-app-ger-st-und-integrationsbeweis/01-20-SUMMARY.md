---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 20
subsystem: ci-abnahme
tags: [push, deploy-harp, korrekturschleife, ui-abnahme, kontrast, fixtures, messwerte]
requires: [01-16, 01-17, 01-18, 01-19]
provides: [gruene CI auf phase-01 ueber alle Workflows und Beine, Owner-UI-Abnahme aller Flaechen, Messwerte beider Architekturen, Status Zertifikat-PR 1419]
affects: [phase-02]
tech-stack:
  added: []
  patterns: ["Korrekturschleife: jeder Push einzeln vom Owner freigegeben, jede rote Runde mit Logzeile belegt", "Kontrast wird in CI pixel-unabhaengig gemessen (textContrast verweigert Theme-Bild ohne Seitengrund)", "Testdokumente sehen aus wie echte Verwaltungspost (Briefkopf, Az., Rechtsbehelfsbelehrung), Kanarie nur im Flaechentext"]
key-files:
  created: []
  modified: [ci/playwright/helpers.ts, ci/playwright/review.spec.ts, ci/make_fixtures.py, php/css/review.css, php/src/ReviewPlaceholder.vue, backend/src/pii_redaction_backend/settings.py, .github/workflows/store-submit.yml, .github/workflows/deploy-harp.yml]
decisions:
  - "Owner 15.11.: Kontrast-Befund sofort fixen (Seitengrund --color-main-background plus WCAG-Gate in CI)"
  - "Owner 15.11.: Testdokumente realistisch statt einfacher Textzeilen (Bescheid, IFG-Antrag, Aktenvermerk)"
  - "Owner 15.11.: Store-Texte Option A, Texte bleiben; erste Einreichung erst mit fertiger Erkennung, vorher Faktencheck-Gate"
  - "Owner 15.11.: UI-Abnahme aller Flaechen mit den Push-13-Screenshots erteilt"
metrics:
  duration: "14.11. abends bis 15.11. nachmittags, 13 Pushes"
  completed: 2026-11-15
  tasks: 4
  files: 30
---

# Phase 1 Plan 20: Push, CI-Korrekturschleife und gemeinsame UI-Abnahme Summary

Der Stand der Phase 1 lief ueber 13 einzeln freigegebene Pushes auf `phase-01`
durch alle Workflows (PHP gates, Python gates, Deploy through HaRP mit 7
Beinen, upgrade mit 4). Jeder rote Lauf wurde mit Logzeile belegt, als
Produkt- oder Testfehler eingeordnet und vor dem naechsten Push vom Owner
freigegeben. Endstand: alle Workflows gruen auf `7f71f9e` (Python
43714004362, Deploy through HaRP 43714004376, 1h10m; PHP gates zuletzt gruen
auf 43706708368, der Folge-Push aenderte nur `ci/playwright/`).

## Korrekturschleife (Belege je Runde)

| Runde | Befund | Einordnung | Fix |
|---|---|---|---|
| Erster Lauf | shellcheck 0.9.0; notifications braucht composer install ab stable34; stable33 sqlite-Standard owncloud.db | CI-Aufbau | 604d4e7, 8147c20, 0cedff1 |
| Push 3/4 | deploy 7/7 cancelled nach 120 min (17 Haenger a 240 s, kein actionTimeout); Toast faellt bei 375 px aus dem Bild (dialogs 8.0.0 kennt NC-34-Klasse --close nicht) | Test-Fristen; echter UI-Fehler | 3e1f300; d099b2d (Upstream-Entwurf nextcloud-dialogs liegt beim Owner) |
| Push 5/6 | page.route vom Files-Service-Worker umgangen; Kanarie-Namenspruefung zaehlte Sabre-NotFound der eigenen Testhelfer; SC2015; Drift-7-Timing; log_rotate | Testfehler | 1b773f6, f1df648, 2c21e04, 3fd42de, 7df11e2 |
| Push 7/8 | JobService::start 500 auf arm-sqlite: SELECT+INSERT in deferred Transaktion, Lese-Schreib-Upgrade kollidiert mit Backend-claim/ack, NC setzt kein busy_timeout | Produktfehler (trifft echte sqlite-Selfhoster) | 8dd8d64 RetriedTransaction (3 Anlaeufe, nur Lock-Gruende), 3ceaed8 Logzeile mit at= |
| Push 8 Nebenbefund | fclose-TypeError in PublishService:82: newFile() schliesst den Stream selbst | Produktfehler (nur Log-Laerm) | db5b6c0 is_resource-Guard |
| Push 9 | MKCOL 503 "database is locked" in Core-webdav: invalidateToken macht Read-Write-Upgrade in deferred WAL-Transaktion, busy handler wird nicht gefragt | Core-Bug, nicht unsere App; Owner hat nextcloud/server#66627 gepostet | Harness entlastet: 3faf51e teilt eine DAV-Sitzung je Nutzer statt Login je Aufruf |
| Push 10 | alle 7 Beine gruen; Positivkontrolle: 0x "database is locked" in den vorher roten Beinen | Schleife zu | - |
| Push 11 | Abgelaufen-Karte ohne 14-Tage-Satz; ExApp-Einstellungsseite entfernt (enabled-Handler raeumt alte Registrierung ab, deploy-harp prueft Abwesenheit) | Owner-Entscheide | 89cb4df, 1552e09 |
| Push 12 | Owner-Befund Kontrast: Pruefseite ohne Seitengrund (hell 1,08-3,47:1, hc 3,65:1, pixel-gemessen); Owner-Wunsch realistische Testdokumente; store-submit.yml reichte nur eine Haelfte ein und prueft das falsche Image | Produktfehler; Testdaten; Release-Kette | 864c8e8 (review.css Seitengrund + textContrast-Gate, verweigert Theme-Bild), ce08dfd (Bescheid/Antrag/Vermerk mit Briefkopf, Kanarie unveraendert), 823bb1a (Paar-Einreichung, Image pii_redaction_backend) |
| Push 13 | Kontrast-Selbsttest flattrig: page.evaluate direkt nach login(), document.body noch null | Testfehler | 7f71f9e (erst /apps/files/ fertig laden) |

## Messwerte (Schwellen nicht festgeschrieben, Eingabe fuer Phase 2/8)

| Wert | amd64 (stable35 sqlite) | arm64 (stable35 sqlite) |
|---|---|---|
| Image roh | 850 010 516 B (811 MiB) | 869 789 678 B (829 MiB) |
| Image gzip | 337 498 443 B (322 MiB) | 329 049 452 B (314 MiB) |
| Kaltstart bis ready / register | 16,55 s / 16,29 s | 16,84 s / 16,50 s |
| Leerlauf memory.current / anon / peak | 89,9 / 61,0 / 247,4 MB | 90,0 / 61,7 / 247,0 MB |
| Kind render (Seite 1) | 323 ms, RSS 223,8 MB | 406 ms, RSS 218,5 MB |
| Kind soffice / placeholder | im Messfenster nicht angefallen (null) | im Messfenster nicht angefallen (null) |

Quelle: `measurements-stable35-{amd64,arm64}-sqlite.json` aus Lauf 43714004376.

## UI-Abnahme (Owner, 15.11.2026)

- Ablauf: CI-Screenshots statt lokalem Playwright (Owner-Wahl); Push-10-Stand
  gesichtet, zwei Befunde, beide behoben, Nachabnahme mit den
  Push-13-Screenshots (3 Beine x 607 Bilder: 51 Zustaende x 12 Projekte
  en 375/768/1280 hell+dunkel, en-w1280-contrast, de/de-du/fr 375-hell und
  1280-dunkel).
- Owner-Befund Kontrast: behoben (siehe oben); unabhaengige Pixel-Gegenprobe
  auf den Push-13-Bildern: Meta-Zeile 5,33:1 (vorher 1,08:1), h2 15,91:1
  (vorher 2,73:1), 375 px 5,33:1, Seitengrund weiss.
- Owner-Wunsch realistische Dokumente: umgesetzt, Bescheid mit Briefkopf,
  Adressfeld, Az., Rechtsbehelfsbelehrung auf der Pruefseite sichtbar.
- Textlaengen-Liste (Schritt 7): 94 Katalogtexte DE/EN/FR, alle hoechstens 2
  Saetze, laengster 97 Zeichen, 0 ueber der Richtschnur
  (Scratchpad textlaengen_0120.txt).
- Admin-Seite und Benachrichtigungs-Popover (ohne Dateinamen) in Ordnung.
- Ergebnis: alle Flaechen abgenommen ("Abgenommen", 15.11.); keine offenen
  Luecken fuer plan-phase --gaps.

## Status Zertifikat-PR

- nextcloud/app-certificate-requests#1419 (pii_redaction_backend): MERGED am
  2026-11-12 (nur lesend erhoben, kein Kommentar).

## Offene Punkte ausserhalb dieses Plans

- Merge phase-01 nach main: getrennte Owner-Frage nach dieser Abnahme (Plan,
  Task 4); ohne ausdrueckliche Antwort kein Merge.
- Store-Einreichung: erst mit fertiger Erkennung; vorher Faktencheck der
  info.xml-Texte (Owner-Entscheid Option A, 15.11.).
- Upstream: nextcloud/server#66627 wartet auf Antworten (nur Owner
  antwortet); Upstream-Entwurf nextcloud-dialogs (Toast bei 375 px) liegt
  beim Owner.
