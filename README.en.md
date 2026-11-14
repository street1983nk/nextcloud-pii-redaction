[Deutsch](README.md) | English | [Français](README.fr.md)

# PII Redaction

[![Python gates](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml)
[![Security scans](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml)
[![Nextcloud App Store](https://img.shields.io/badge/App_Store-pii__redaction-0082c9)](https://apps.nextcloud.com/apps/pii_redaction)
[![License](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue)](LICENSE)

PII Redaction is meant to find personal data in PDF, DOCX and ODT files in Nextcloud and to redact it after a human review. Everything runs locally on your own server.

**Status:** in development, not yet in the App Store. As of 0.1.0: a framework of two apps with a review page and a placeholder copy. There is no detection of personal data and no redaction yet.

## What PII Redaction 0.1.0 does

- File action "Redact / pseudonymize" in the Files app, for exactly one PDF, DOCX or ODT file
- One job at a time; further jobs wait in a queue, the start message names the number of jobs ahead
- The backend converts DOCX and ODT to PDF with LibreOffice
- Review page with progress and page 1 as an image, marked as "Preview without detection"
- "Create placeholder copy" places a one-page PDF next to the original that contains nothing from the original, for example `Bescheid_redacted.pdf` (German `_geschwärzt`, French `_caviardé`); a name already taken gets ` (2)`
- The original stays unchanged
- Notifications when a review is ready, an analysis fails, the file was changed or the copy was created
- Status section for admins with the state of both apps
- Texts in German, English and French
- Planned, not built yet: detection of personal data, redaction and pseudonymization, a check of the copy for leftovers

## Two apps, both required

| App | ID | Role |
|---|---|---|
| PII Redaction | `pii_redaction` | PHP app: file action, review page, permission checks, notifications, placing the copy, status section |
| PII Redaction Backend | `pii_redaction_backend` | External App (Python container): conversion to PDF, page image, placeholder PDF |

Both apps have to be installed and carry the same version. If the versions differ only in the last digit, analyses keep running; otherwise no new analysis starts until both apps match again.

## Requirements

- Nextcloud 33 to 35, PHP 8.2 or newer
- AppAPI with the HaRP deploy daemon
- CPU: amd64 or arm64, no GPU needed
- Background jobs in Cron mode recommended: a background job places the copy
- Notifications app for the notifications

## Installation

In short: AppAPI with HaRP, then the External App `pii_redaction_backend`, then the PHP app `pii_redaction` in the same version. The state of both apps is then shown under Administration settings, PII Redaction. All steps and the meaning of every message in the status section: [docs/install.en.md](docs/install.en.md).

## Architecture

The PHP app checks the user's permissions at every step and hands the file to the backend through an interface by file ID. The backend is an External App: a Python container (FastAPI) that AppAPI starts through HaRP. The container has no routes for the browser; every request to it carries the AppAPI signature, without it the answer is 401. The PHP app writes the copy as the user who started the analysis; the container has no write access to user files.

## Privacy

- Everything runs locally on your own server, no content leaves the server, no telemetry
- Notifications name no file, they only link to the review page
- The app's tables in the Nextcloud database store no file names, only file ID, user and state of the job
- Intermediate data (file, PDF, page image) is kept in the container's data volume; the backend deletes it as soon as the copy is created or the job ends
- Version 0.1.0 does not yet delete open reviews after a period

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

Third party components in the backend image:

- PyMuPDF (AGPL-3.0) renders the page image and writes the placeholder PDF
- LibreOffice (Debian package `libreoffice-writer-nogui`) converts DOCX and ODT to PDF, together with the font packages `fonts-liberation2`, `fonts-dejavu-core`, `fonts-crosextra-carlito` and `fonts-crosextra-caladea`; the license texts of the Debian packages are in the image under `/usr/share/doc/<package>/copyright`

Icons of the PHP app: Material Design Icons by Pictogrammers, Apache-2.0.
