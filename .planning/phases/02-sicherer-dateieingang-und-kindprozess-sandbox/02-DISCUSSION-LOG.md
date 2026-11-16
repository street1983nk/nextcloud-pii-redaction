# Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md , this log preserves the alternatives considered.

**Date:** 2026-11-16
**Phase:** 02-Sicherer Dateieingang und Kindprozess-Sandbox
**Areas discussed:** Ablehnungstexte, Signierte PDFs, Restrisiko Isolation, Grenzen

---

## Ablehnungstexte

| Option | Description | Selected |
|--------|-------------|----------|
| Verständlich + Abhilfe | Je Grund ein Alltagssatz plus Abhilfe-Satz, Behörden-Zielgruppe | ✓ |
| Technisch knapp | Kurzer technischer Grund ohne Abhilfe | |

| Option | Description | Selected |
|--------|-------------|----------|
| Dateikarte in der App | Am Eintrag der Datei in der Review-Oberfläche (Statusfläche Phase 1) | ✓ |
| Karte + Benachrichtigung | Zusätzlich Nextcloud-Benachrichtigung je Ablehnung | |

**User's choice:** Beide Empfehlungen übernommen.

---

## Signierte PDFs

| Option | Description | Selected |
|--------|-------------|----------|
| Bestätigung nötig | Analyse erst nach Bestätigung des Hinweises, Eintrag ins Protokoll | ✓ |
| Hinweis ohne Stopp | Analyse läuft durch, Hinweis auf Karte + Protokoll | |

**User's choice:** Bestätigung nötig.

---

## Restrisiko Isolation

| Option | Description | Selected |
|--------|-------------|----------|
| AR mit weicher Isolation | rlimits, Prozessgruppe, geleerte Umgebung, seccomp soweit möglich; Rest als Accepted Risk einzeln zum Owner | ✓ |
| Hartes Gate | Ohne Namespace-Isolation kein Release, ggf. Funktionsverzicht | |
| Research entscheidet | Erst Messung, dann erneut fragen | |

**User's choice:** AR mit weicher Isolation.

---

## Grenzen

| Option | Description | Selected |
|--------|-------------|----------|
| Fest in Phase 2 | Begründete Konstanten mit Tests, Admin-Einstellbarkeit später bei Nachfrage | ✓ |
| Admin-einstellbar ab jetzt | Sichere Defaults, per occ änderbar | |

| Option | Description | Selected |
|--------|-------------|----------|
| Überall gleich | Ein Deckel für jeden Analyse-Weg, auch spätere Auto-Verarbeitung | ✓ |
| Nur manuell relevant | Auto-Weg entscheidet seine Phase | |

**User's choice:** Beide Empfehlungen übernommen.

## Claude's Discretion

- Aufbau der Vorprüfung (Magic-Bytes, Prüfreihenfolge, Fehlerklassen)
- Korpus-Erzeugung per Skript in CI (keine Binärdateien im Repo)
- Netzabschaltung je Bibliothek nach Research-Befund
- Schnitt der Kindprozess-API (ein Runner-Modul für alle Parser)

## Deferred Ideas

- Admin-Einstellbarkeit der Grenzen (erst mit Admin-Oberfläche, bei Nachfrage)
