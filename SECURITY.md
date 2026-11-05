# Security Policy

## Supported versions

Only the latest release of `pii_redaction` in the
[Nextcloud App Store](https://apps.nextcloud.com/apps/pii_redaction) is
supported; please update before reporting.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

- Preferred: GitHub private vulnerability reporting, via "Report a
  vulnerability" under the Security tab of this repository
- Alternative: mail to admin@infranode.dev

You will get a first answer within 7 days. Please include the app version, your
Nextcloud version, and steps to reproduce.

## Scope

The app is an External App: a Python container reachable only through AppAPI
and HaRP. The promises worth attacking: every request without a valid AppAPI
signature is refused, routes marked ADMIN are not reachable for other users,
the container runs without root, and nothing leaves your server.
