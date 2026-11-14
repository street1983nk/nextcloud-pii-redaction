# Product

<!-- impeccable:product-schema 1 -->

> Quellen: `.planning/PROJECT.md` (Ziel, Nutzer, Grenzen), `.planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-UI-SPEC.md` (Oberfläche Phase 1, Owner-Entscheide 07.11.2026) und der Code von Version 0.1.0. Aussagen über später geplante Fähigkeiten sind als geplant markiert.

## Platform

web

## Users

- **Admins von Nextcloud-Instanzen** (Behörden, Kommunen, Schulen, kleine Organisationen, Selfhost), die beide Apps installieren und den Zustand unter Verwaltungseinstellungen, PII Redaction prüfen.
- **Sachbearbeitende**, die ein Dokument herausgeben müssen (IFG-Herausgaben, Veröffentlichung von Gerichtsentscheidungen) und fragen: Welche personenbezogenen Daten stehen darin, und wie entsteht eine Fassung, in der davon nachweislich nichts mehr steckt, ohne dass der Inhalt den Server verlässt? Quelle: PROJECT.md.

## Product Purpose

Eine Datei aus Nextcloud wird mit einem Klick lokal auf personenbezogene Daten geprüft; nach menschlicher Prüfung entsteht neben dem Original eine geschwärzte oder pseudonymisierte Kopie, in der nachweislich nichts Geschwärztes mehr steckt (Text, Metadaten, Altversionen, OCR-Ebene). Kein Inhalt verlässt den Server. Quelle: PROJECT.md, Core Value.

Stand 0.1.0: Der Weg von der Dateiaktion über die Prüfseite bis zur Kopie neben dem Original steht, mit Vorschau ohne Erkennung und einer Platzhalter-Kopie, die nichts aus dem Original enthält.

Erfolg heißt: Eine herausgegebene Kopie enthält keinen der geschwärzten Werte mehr, belegt durch eine automatische Nachprüfung; Leckrate je Kategorie und Dokumenttyp als Hauptkennzahl. Quelle: PROJECT.md (geplant, in 0.1.0 nicht gebaut).

## Positioning

- Läuft komplett in der eigenen Instanz, kein Inhalt verlässt den Server, keine Telemetrie.
- Zwei Apps: PHP-App `pii_redaction` und External App `pii_redaction_backend` (Python-Container über AppAPI und HaRP), gleiche Version, AGPL-3.0-or-later.
- Geplant: deutsche Erkenner und Rechtsgrundlagen, dokumentierte Leck-Nachprüfung, offene Qualitätszahlen, Pseudonymisierung. Nächster Wettbewerber: Conduction DocuDesk mit OpenAnonymiser (Fokus Niederlande, EUPL). Quelle: PROJECT.md, Context.

## Operating Context

- Nextcloud 33 bis 35, amd64 und arm64, nur CPU; noch nicht im App Store.
- Oberfläche: Dateiaktion in der Dateien-App, eigene Prüfseite (Vue), Benachrichtigungen über die App Notifications, Admin-Statusbereich (PHP-Template), siehe DESIGN.md.
- Die Kopie legt ein Nextcloud-Hintergrundjob an; Hintergrundjobs im Modus Cron empfohlen.
- Texte in Deutsch, Englisch und Französisch, Deutsch zuerst.

## Capabilities and Constraints

Version 0.1.0:

- Dateiaktion „Schwärzen / Pseudonymisieren“ für genau eine PDF-, DOCX- oder ODT-Datei; nicht bei Mehrfachauswahl, im Papierkorb, auf öffentlichen Freigabeseiten, bei gesperrtem Download.
- Ein Auftrag zur Zeit mit Warteschlange; DOCX und ODT werden mit LibreOffice in PDF umgewandelt.
- Prüfseite mit Fortschritt und Seite 1 als Bild, „Vorschau ohne Erkennung“.
- Platzhalter-Kopie neben dem Original: einseitige PDF ohne Originalinhalt, Name mit `_geschwärzt`, `_redacted` oder `_caviardé`.
- Benachrichtigungen ohne Dateinamen; Statusbereich mit sieben Zuständen der Gegen-App plus gescheiterter Neuprüfung.

Geplant, nicht gebaut (Quelle PROJECT.md): Erkennung personenbezogener Daten, Vorschlagsliste mit Annehmen und Ablehnen, echte Schwärzung und Pseudonymisierung, OCR für Scans, Vier-Augen-Freigabe, Schwärzungsprotokoll, automatische Leck-Nachprüfung, Löschung offener Prüfungen nach 14 Tagen.

Out of Scope:

- Inhalte an externe Dienste schicken (Owner-Regel Datenschutz zuerst).
- Vollautomatische Schwärzung ohne menschliche Prüfung.
- Texte nur über die l10n-Kataloge, drei Sprachen im Gleichstand (`backend/tests/test_trilingual.py`).

## Brand Commitments

- Keine eigene visuelle Marke: die Oberfläche folgt Nextcloud-Design und Theming (nextcloud-ui-Skill).
- Produkttexte sind kurze Faktenlisten, höchstens eine Zahl, Entwurf vor Release dem Owner zeigen.
- Deutsch mit echten Umlauten, keine Gedankenstriche, keine Emojis.

## Evidence on Hand

- Lokale Gates in `backend/` und `php/` (pytest, ruff, pyright, vulture, PHP-Unit-Tests); der Integrationsbeweis auf echten Instanzen (Workflow `deploy-harp.yml`, Playwright-Abnahme unter `ci/playwright/`) ist gebaut, aber noch nicht gelaufen.
- Messwerte zu Erkennung und Schwärzung stammen aus dem Spike vom 06.11.2026, nicht aus dieser App.
- Nicht vorhanden und nicht zu erfinden: Kundenstimmen, Nutzerzahlen, Preise, Screenshots für den Store.

## Product Principles

1. Null Konfiguration: der Werkzustand funktioniert ohne Einstellung.
2. Nichts verlässt den Server.
3. Ehrliche Zustände: Übersprungenes und Fehlgeschlagenes wird sichtbar benannt.
4. Sieht aus wie Nextcloud.

## Accessibility & Inclusion

Zielstandard WCAG 2.1 AA (BITV-relevant für öffentliche Einrichtungen): Fokus nie entfernt, Farbe nie alleiniger Träger, Icon-Knöpfe mit `aria-label`, hoher Kontrast über Server-Variablen. Einzelheiten in DESIGN.md, Abschnitt Barrierefreiheit.
