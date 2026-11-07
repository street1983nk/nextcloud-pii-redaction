# PII Redaction Backend

The External App (ExApp) half of PII Redaction: a FastAPI service that AppAPI
deploys as a container. It reads documents, finds personal data and writes the
redacted or pseudonymised copy, all locally on the server. On its own it does
nothing; the PHP app `pii_redaction` (in `../php`) adds the file action, the
review page and the permission checks.

Both halves always carry the same version. The user documentation is in
[../README.en.md](../README.en.md) (German: `../README.md`, French: `../README.fr.md`).
