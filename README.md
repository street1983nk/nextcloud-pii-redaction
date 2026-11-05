Deutsch | [English](README.en.md) | [Français](README.fr.md)

# PII Redaction

[![Python gates](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml)
[![Security scans](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml)
[![Nextcloud App Store](https://img.shields.io/badge/App_Store-pii__redaction-0082c9)](https://apps.nextcloud.com/apps/pii_redaction)
[![Lizenz](https://img.shields.io/badge/Lizenz-AGPL--3.0--or--later-blue)](LICENSE)

PII Redaction findet personenbezogene Daten in Dokumenten in Nextcloud und schwärzt sie. Erkennung und Schwärzung laufen lokal auf dem eigenen Server, für Texte auf Deutsch, Englisch und Französisch.

**Status:** in Entwicklung, noch nicht im App Store.

## Was PII Redaction kann

- Erkennt Namen, Adressen, Telefonnummern, E-Mail-Adressen, IBAN und ähnliche Angaben
- Schwärzt echt: der Text wird entfernt, nicht nur überdeckt
- Vorschau zum Prüfen vor dem Schwärzen, das Original bleibt erhalten
- Läuft komplett in Ihrer eigenen Instanz, keine Telemetrie
- Verändert nie Ihre Dateien

## Anforderungen

- Nextcloud 33 bis 35 mit AppAPI und einem eingerichteten Deploy-Daemon (HaRP empfohlen)
- CPU: amd64 oder arm64

## Installation

Im App Store unter External Apps die App PII Redaction installieren. Die
Einstellungen stehen danach unter Verwaltungseinstellungen, Weitere
Einstellungen.

## Architektur

PII Redaction ist eine External App: ein Python-Container (FastAPI), den AppAPI
über den Deploy-Daemon startet und nur über AppAPI/HaRP erreicht. Jede Anfrage
an den Container trägt die Signatur von AppAPI; ohne sie antwortet er mit 401.

## Datenschutz

Alles läuft lokal im Container, nichts verlässt den Server.
Die App speichert nur ihre Einstellungen und schreibt die geschwärzte Fassung als neue Datei, kein Dokument verlässt den Server.

## Lizenz

AGPL-3.0-or-later. Siehe [LICENSE](LICENSE).
