---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 19
subsystem: docs
tags: [readme, install, design, product, changelog, l10n-audit, umlaute, french-spacing]
requires: [01-15, 01-16, 01-17, 01-18]
provides: [README DE/EN/FR für 0.1.0, Installationsanleitung DE/EN/FR, DESIGN.md und PRODUCT.md ohne Vorlagenreste, CHANGELOG 0.1.0, Text-Audit mit Positivkontrolle, Gate für französische Leerzeichen in Doku und Store-Texten]
affects: [01-20]
tech-stack:
  added: []
  patterns: ["Doku nennt nur Fakten mit Beleg im Code; Geplantes ist als „geplant, noch nicht gebaut“ markiert", "Französische Doku mit U+00A0 vor : ; ? ! und in Guillemets, gehalten durch test_public_texts.py"]
key-files:
  created: []
  modified: [README.md, README.en.md, README.fr.md, docs/install.md, docs/install.en.md, docs/install.fr.md, DESIGN.md, PRODUCT.md, CHANGELOG.md, CONTRIBUTING.md, backend/tests/test_public_texts.py, .planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/deferred-items.md]
decisions:
  - "README beschreibt 0.1.0 ehrlich: Vorschau ohne Erkennung, Platzhalter-Kopie, keine Erkennung und keine Schwärzung; die alte Liste (erkennt Namen, schwärzt echt) ist entfernt"
  - "Version-Drift: Doku sagt nur, was der Code belegt (keine neue Analyse, keine Kopie auf der Prüfseite); kein Satz über wartende Aufträge, weil claim() den Zustand nicht prüft"
  - "Store-Texte (info.xml) nicht geändert: Produkttext, Owner-Entscheid nötig"
metrics:
  duration: "ca. 75 min"
  completed: 2026-11-14
  tasks: 2
  files: 12
---

# Phase 1 Plan 19: Doku dreisprachig und Text-Audit Summary

README, Installationsanleitung, DESIGN, PRODUCT und CHANGELOG beschreiben den Stand 0.1.0 nur mit Fakten aus dem Code, in DE (zuerst), EN und FR mit gleicher Gliederung. Ein eigenes Audit-Skript (unabhängig vom Gate aus Plan 03) prüfte 28 Dateien mit nutzersichtbaren Texten auf sechs Klassen; jede Klasse schlug in der Positivkontrolle genau einmal an, im Repo blieb kein echter Befund offen. Neu im Gate: französische Leerzeichen in README.fr, docs/*.fr.md und den französischen Store-Texten.

## Tasks

| Task | Name | Commit | Dateien |
|---|---|---|---|
| 1 | README, Installationsanleitung, DESIGN, PRODUCT, CHANGELOG | c02523c | README.md, README.en.md, README.fr.md, docs/install*.md, DESIGN.md, PRODUCT.md, CHANGELOG.md |
| 2 | Audit, neue Gate-Regel | 728e61c | backend/tests/test_public_texts.py |
| 2 (Abweichung) | CONTRIBUTING-Pfade aus deferred-items | 3301f8e | CONTRIBUTING.md |

## Inhalt der Doku (je Aussage mit Beleg)

- Dateiaktion nur für genau eine PDF/DOCX/ODT, nicht Mehrfachauswahl, Papierkorb, öffentliche Freigabe, Ordner, gesperrter Download: `php/src/init.ts` (`enabled`), `JobService::ALLOWED_MIMES`.
- Ein Auftrag zur Zeit, Zahl davor im Toast: `oc_pii_slot`, Plural-Katalogeinträge `_Analysis started. %n job is ahead._`.
- DOCX/ODT per LibreOffice: `runner.py` (Stufe `converting`), `Dockerfile` (`libreoffice-writer-nogui` plus vier Schriftpakete).
- Kopie: `Suffix.php` (`_geschwärzt`/`_redacted`/`_caviardé`, immer `.pdf`, NFC), `PublishService` (`getNonExistingName`, als Auftraggeber, Etag- und Sperrprüfung), `PublishJob` als `QueuedJob` (daher Cron empfohlen).
- Benachrichtigungen ohne Dateinamen: `Notifier.php`, `Subject.php` (vier Betreffe).
- Statusbereich: sieben Zustände aus `ExAppService::STATES` plus „Neuprüfung gescheitert“, Texte aus `php/l10n/*.json`.
- Drift: `startAllowed()` sperrt Start (`JobService`) und Platzhalter-Kopie (`ReviewController` Zeile 186). PHP-App aus: Container zieht keine Arbeit (01-18, `companion.may_work`).
- Datenschutz: `pii_jobs`/`pii_job_events` ohne Namensspalte (Migration), Zwischendaten im Volume `work/<job>` und Purge bei published/failed/stale/cancelled (`JobService`). „0.1.0 löscht offene Prüfungen noch nicht nach einer Frist“: `JobMapper` Zeile 82.
- Container ohne Browser-Routen, 401 ohne Signatur: `backend/appinfo/info.xml` `<routes/>`, `tests/test_main.py`, `tests/test_api_routes.py`.

## Gleichstand der Sprachen

| Datei | Zeilen | `## ` | Aufzählungen | nummeriert | Tabellenzeilen |
|---|---|---|---|---|---|
| README.md / .en / .fr | 69 / 69 / 69 | 7 / 7 / 7 | 22 / 22 / 22 | 0 | 4 / 4 / 4 |
| docs/install.md / .en / .fr | 54 / 54 / 54 | 5 / 5 / 5 | 20 / 20 / 20 | 6 / 6 / 6 | 0 |

Akzeptanz Task 1: `pii_redaction_backend` je Anleitung 4, `## 0.1.0` in CHANGELOG 1, `TODO|TBD|platzhaltertext|lorem` in DESIGN.md und PRODUCT.md je 0, verify (`test_public_texts`, `test_trilingual`, `test_public_artifacts`) 34 passed.

## Audit (Task 2)

Skript im Scratchpad, eigenes Muster: Wörterbuch aus allen Wörtern mit ä/ö/ü/ß der deutschen Texte plus fester Liste, daraus die Umschriften, gesucht in allen Sprachen; Emojis über Unicode-Kategorie `So` plus U+FE0F/U+200D; Striche U+2012 bis U+2015 im Rohtext; eigene Regeln für Französisch, gerade Anführungszeichen und `...`. Geprüft 28 Dateien: 4 PHP-Kataloge (`.json`; die `.js` hält `l10n_js.py --check` gleich), 3 Backend-Kataloge, beide info.xml, `php/src/*.ts|*.vue`, `php/templates/*.php`, `Notifier.php`, `placeholder.py`, drei README, drei Anleitungen, CHANGELOG, DESIGN, PRODUCT.

Positivkontrolle auf einer Kopie im Scratchpad, je Klasse ein eingeschleuster Fehler: a `Pruefseite` in de.json, b U+2014 in README.md, c U+1F600 in fr.json, d `Statut :` in README.fr.md, e `"Auftrag"` in docs/install.md, f `Wird angelegt...` in de.json. Ergebnis: je Klasse genau 1 Treffer.

| Klasse | Datei | Befund | Entscheidung | Offen |
|---|---|---|---|---|
| a Umschrift statt Umlaut | alle 28 | 0 Treffer; Gegenliste aller deutschen Wörter mit ae/oe/ue/ss von Hand gesichtet (31 Wörter, z. B. Adressen, dass, muss, Quelle, neue): alle korrekt | keine Änderung | 0 |
| b U+2012 bis U+2015 | alle 28 | 0 | keine | 0 |
| c Emoji, Piktogramm | alle 28 | 0 | keine | 0 |
| d Französisch U+00A0 | README.fr.md (Stand vor Task 1) | 6 normale Leerzeichen vor `:` | in c02523c behoben, neue Gate-Regel | 0 |
| d | README.fr.md | 4 Treffer `![`: Markdown-Bildsyntax | Fehlalarm, Skript nimmt `![` aus | 0 |
| d | placeholder.py | `{NBSP}:` im Quelltext | Fehlalarm: `SENTENCES["fr"]` enthält zur Laufzeit U+00A0 vor `:` (per Import geprüft) | 0 |
| d | beide info.xml (fr) | 0 normale Leerzeichen, 5 bzw. 6 U+00A0 vor `:`, Guillemets mit U+00A0 | keine | 0 |
| e gerade Anführungszeichen (de) | DESIGN.md | 32 Werte im YAML-Kopf (`"#00679e"` usw.) | Fehlalarm: Daten, keine Prosa; Skript nimmt den Kopf aus | 0 |
| e | Kataloge, README, Anleitung, info.xml (de) | 0; deutsche Texte nutzen „…“ | keine | 0 |
| f `...` statt U+2026 | alle 28 | 0; Kataloge nutzen `…` (`Wird angelegt…`, `Wird geprüft…`) | keine | 0 |

Kataloge unverändert, daher keine Playwright-Spec angepasst und `.js` nicht neu erzeugt (`l10n_js.py --check` Exit 0).

Neue Gate-Regeln in `test_public_texts.py` (Gate aus Plan 03 fing beides nicht):
- `test_french_documents_and_store_texts_carry_the_narrow_spacing`: README.fr.md, docs/*.fr.md, französische Store-Texte beider Apps; Positivkontrolle „mindestens ein U+00A0“; Gegenprobe gegen die alte README.fr.md (vor c02523c): 6 Treffer.
- `test_self_the_french_rule_fires_on_plain_and_missing_spaces`: 6 Treffer im Fehlersatz, 1 bei `Statut: x`, 0 im sauberen Satz mit Bildsyntax, URL, Code und Uhrzeit.
- Umlaut-Gate liest jetzt auch die deutschen Store-Texte von `php/appinfo/info.xml` (vorher nur Backend), Selbsttest `test_self_the_german_texts_include_both_store_files`.

## Gates (lokal, 14.11.2026)

- `l10n_js.py --root ../php/l10n --check`: Exit 0.
- `pytest -q`: 493 passed, 3 skipped (vorher 490 passed, 3 skipped; plus 3 neue Tests).
- ruff check „All checks passed!“, ruff format --check „61 files already formatted“, pyright „0 errors, 0 warnings, 0 informations“, vulture ohne Fund.
- `grep -rlP "[\x{2013}\x{2014}]" php/l10n php/src php/templates backend/l10n README*.md docs CHANGELOG.md`: keine Treffer (Exit 1); breiter mit U+2012 bis U+2015 über php/lib, beide appinfo, DESIGN, PRODUCT: keine Treffer; Positivkontrolle `printf 'a\xe2\x80\x94b'` ergibt 1.
- Commits: Autor und Committer `street1983nk <k.cherif@outlook.de>`; Treffer für claude/co-authored/closes/fixes # in den drei Commit-Texten: 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] README versprach nicht gebaute Funktionen**
- Alte README (alle drei Sprachen) nannte Erkennung von Namen, IBAN usw., echte Schwärzung und Installation „im App Store“. Ersetzt durch den belegten Stand 0.1.0 und eine als geplant markierte Zeile. Commit c02523c.

**2. [Rule 1 - Bug] DESIGN.md nannte falsche Pfade und Pakete**
- `src/pii_redaction/settings.py`, `SKELETON.md` (gibt es nicht), `vue-material-design-icons` (nicht in `php/package.json`), Auslieferung über `nc.ui.resources`. Korrigiert auf die echten Pfade und Inline-SVG. Commit c02523c.

**3. [Rule 2 - Missing] CONTRIBUTING.md mit Skelett-Pfaden**
- Offener Punkt aus deferred-items (01-01), dort dem Doku-Plan zugewiesen. Pfade beider Apps und Gates wie in CI. Nicht in `files_modified`. Commit 3301f8e.

**4. Audit über DESIGN.md und PRODUCT.md** zusätzlich zur Dateiliste des Plans, weil beide in diesem Plan neu geschrieben wurden.

## Offene Punkte (Owner)

1. **Store-Texte beider info.xml** (DE/EN/FR) versprechen weiter Erkennung, echte Schwärzung und Vorschau vor dem Schwärzen. Produkttext: Owner entscheidet, ob vor einem Release auf den Stand 0.1.0 gekürzt wird; Entwurf zeigen. Nicht geändert.
2. **Formular der ExApp** unter Weitere Einstellungen: „Neue Dateien automatisch verarbeiten“ und „Größte Datei in MB“ werden von keinem Code gelesen. Entfernen oder behalten: Owner-Entscheid.
3. **Satz „Prüfungen werden nach 14 Tagen gelöscht.“** (Karte „Diese Prüfung ist abgelaufen“): Phase 1 setzt keine Frist durch. Der Zustand ist im echten Lauf nicht erreichbar, nur in der Playwright-Suite gefälscht. Text bis Phase 10 so lassen oder ändern: Owner-Entscheid.
4. **Material Design Icons** (Apache-2.0) ohne Lizenztext in `LICENSES/` und ohne REUSE-Eintrag. README nennt die Lizenz; Datei und Eintrag fehlen noch.
5. Beobachtung: Bei Versions-Drift prüft `QueueController::claim()` den Zustand nicht; ein laufender Container mit abweichender Version kann wartende Aufträge weiter abarbeiten. Die Karte „Der Auftrag wartet und läuft danach weiter.“ trifft dann nicht genau zu. Doku sagt dazu nichts. In Plan 20 im Drift-Schritt beobachten.
6. README und Anleitung beschreiben Verhalten, das lokal nur mit Unit-Tests belegt ist; der Lauf auf echten Instanzen kommt in Plan 20.

Alle vier Funde stehen zusätzlich in `deferred-items.md`.

## Known Stubs

Keine im Sinne des Plans. Die Doku benennt den Platzhalter-Stand ausdrücklich.

## Threat Flags

Keine neue Fläche. T-01-19-01: `test_public_artifacts.py` grün (keine Schlüssel, keine Tokens). T-01-19-02: README nennt den Stand 0.1.0 ehrlich (Vorschau ohne Erkennung, keine Schwärzung).

## Self-Check: PASSED

- Dateien vorhanden: README.md, README.en.md, README.fr.md, docs/install.md, docs/install.en.md, docs/install.fr.md, DESIGN.md, PRODUCT.md, CHANGELOG.md, CONTRIBUTING.md, backend/tests/test_public_texts.py.
- Commits c02523c, 728e61c, 3301f8e in `git log`.
- Nicht gepusht, kein PR, kein Workflow gestartet, kein Docker. STATE.md, ROADMAP.md, REQUIREMENTS.md nicht angefasst.
