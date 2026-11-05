[Deutsch](README.md) | English | [Français](README.fr.md)

# PII Redaction

[![Python gates](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml)
[![Security scans](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml)
[![Nextcloud App Store](https://img.shields.io/badge/App_Store-pii__redaction-0082c9)](https://apps.nextcloud.com/apps/pii_redaction)
[![License](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue)](LICENSE)

PII Redaction finds personal data in documents in Nextcloud and redacts it. Detection and redaction run locally on your own server, for texts in German, English and French.

**Status:** in development, not yet in the App Store.

## What PII Redaction does

- Detects names, addresses, phone numbers, email addresses, IBANs and similar data
- Real redaction: the text is removed, not just covered
- Preview to review before redacting, the original is kept
- Runs entirely inside your own instance, no telemetry
- Never modifies your files

## Requirements

- Nextcloud 33 to 35 with AppAPI and a configured deploy daemon (HaRP recommended)
- CPU: amd64 or arm64

## Installation

Install PII Redaction from the External Apps section of the App Store. Its
settings are under Administration settings, Additional settings.

## Architecture

PII Redaction is an External App: a Python container (FastAPI) that AppAPI
starts through the deploy daemon and reaches only through AppAPI/HaRP. Every
request to the container carries the AppAPI signature; without it the answer
is 401.

## Privacy

Everything runs locally in the container, nothing leaves your server.
The app only stores its settings and writes the redacted version as a new file; no document leaves the server.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
