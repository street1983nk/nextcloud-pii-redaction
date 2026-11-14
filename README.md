Deutsch | [English](README.en.md) | [Français](README.fr.md)

# PII Redaction

[![Python gates](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml)
[![Security scans](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml)
[![Nextcloud App Store](https://img.shields.io/badge/App_Store-pii__redaction-0082c9)](https://apps.nextcloud.com/apps/pii_redaction)
[![Lizenz](https://img.shields.io/badge/Lizenz-AGPL--3.0--or--later-blue)](LICENSE)

PII Redaction soll personenbezogene Daten in PDF-, DOCX- und ODT-Dateien in Nextcloud finden und nach menschlicher Prüfung schwärzen. Alles läuft lokal auf dem eigenen Server.

**Status:** in Entwicklung, noch nicht im App Store. Stand 0.1.0: Gerüst aus zwei Apps mit Prüfseite und Platzhalter-Kopie. Eine Erkennung personenbezogener Daten und eine Schwärzung gibt es noch nicht.

## Was PII Redaction 0.1.0 kann

- Dateiaktion „Schwärzen / Pseudonymisieren“ in der Dateien-App, für genau eine PDF-, DOCX- oder ODT-Datei
- Ein Auftrag zur Zeit; weitere warten in einer Warteschlange, die Startmeldung nennt die Zahl der Aufträge davor
- DOCX und ODT wandelt das Backend mit LibreOffice in PDF um
- Prüfseite mit Fortschritt und Seite 1 als Bild, gekennzeichnet als „Vorschau ohne Erkennung“
- „Platzhalter-Kopie anlegen“ legt neben dem Original eine einseitige PDF an, die nichts aus dem Original enthält, zum Beispiel `Bescheid_geschwärzt.pdf` (englisch `_redacted`, französisch `_caviardé`); ein belegter Name bekommt ` (2)`
- Das Original bleibt unverändert
- Benachrichtigungen, wenn eine Prüfung bereit ist, eine Analyse fehlschlägt, die Datei geändert wurde oder die Kopie angelegt ist
- Statusbereich für Admins mit dem Zustand beider Apps
- Texte auf Deutsch, Englisch und Französisch
- Geplant, noch nicht gebaut: Erkennung personenbezogener Daten, Schwärzung und Pseudonymisierung, Nachprüfung der Kopie auf Reste

## Zwei Apps, beide nötig

| App | ID | Aufgabe |
|---|---|---|
| PII Redaction | `pii_redaction` | PHP-App: Dateiaktion, Prüfseite, Rechteprüfung, Benachrichtigungen, Ablage der Kopie, Statusbereich |
| PII Redaction Backend | `pii_redaction_backend` | External App (Python-Container): Umwandlung in PDF, Seitenbild, Platzhalter-PDF |

Beide Apps müssen installiert sein und dieselbe Version haben. Unterscheiden sich die Versionen nur in der letzten Stelle, laufen Analysen weiter; sonst startet keine neue Analyse, bis beide Apps wieder zusammenpassen.

## Anforderungen

- Nextcloud 33 bis 35, PHP 8.2 oder neuer
- AppAPI mit dem Deploy-Daemon HaRP
- CPU: amd64 oder arm64, keine GPU nötig
- Hintergrundjobs im Modus Cron empfohlen: die Kopie legt ein Hintergrundjob an
- App Notifications für die Benachrichtigungen

## Installation

Kurz: AppAPI mit HaRP, dann die External App `pii_redaction_backend`, dann die PHP-App `pii_redaction` in derselben Version. Der Zustand beider Apps steht danach unter Verwaltungseinstellungen, PII Redaction. Alle Schritte und die Bedeutung jeder Meldung im Statusbereich: [docs/install.md](docs/install.md).

## Architektur

Die PHP-App prüft bei jedem Schritt die Rechte des Nutzers und liefert die Datei über eine Schnittstelle per Datei-ID an das Backend. Das Backend ist eine External App: ein Python-Container (FastAPI), den AppAPI über HaRP startet. Der Container hat keine Routen für den Browser; jede Anfrage an ihn trägt die Signatur von AppAPI, ohne sie antwortet er mit 401. Die Kopie schreibt die PHP-App als der Nutzer, der die Analyse gestartet hat; der Container hat keinen Schreibzugriff auf Nutzerdateien.

## Datenschutz

- Alles läuft lokal auf dem eigenen Server, kein Inhalt verlässt den Server, keine Telemetrie
- Benachrichtigungen nennen keinen Dateinamen, sie verlinken nur auf die Prüfseite
- Die Tabellen der App in der Nextcloud-Datenbank speichern keine Dateinamen, nur Datei-ID, Nutzer und Stand des Auftrags
- Zwischendaten (Datei, PDF, Seitenbild) liegen im Datenvolumen des Containers; das Backend löscht sie, sobald die Kopie angelegt ist oder der Auftrag endet
- Version 0.1.0 löscht offene Prüfungen noch nicht nach einer Frist

## Lizenz

AGPL-3.0-or-later. Siehe [LICENSE](LICENSE).

Bestandteile Dritter im Image des Backends:

- PyMuPDF (AGPL-3.0) erstellt das Seitenbild und die Platzhalter-PDF
- LibreOffice (Debian-Paket `libreoffice-writer-nogui`) wandelt DOCX und ODT in PDF um, dazu die Schriftpakete `fonts-liberation2`, `fonts-dejavu-core`, `fonts-crosextra-carlito` und `fonts-crosextra-caladea`; die Lizenztexte der Debian-Pakete stehen im Image unter `/usr/share/doc/<Paket>/copyright`

Symbole der PHP-App: Material Design Icons von Pictogrammers, Apache-2.0.
