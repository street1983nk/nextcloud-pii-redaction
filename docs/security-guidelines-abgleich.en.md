# Cross-check against the Nextcloud security guidelines (PII Redaction)

Appendix to the security dossier. As of 2026-11-16, checked against the
security guidelines of the Nextcloud 35 developer manual
(developer_manual/prologue/security.html) and the app store rules
(app_publishing_maintenance/publishing.html). Method: a code sweep over
php/ and backend/src on 2026-11-16 (shell_exec, proc_open, passthru,
eval, raw SQL, print_unescaped, innerHTML, os.system: 0 hits) plus
the phase 1 security audit (01-SECURITY.md, 103 threats, 0 open).

## Developer guidelines

| Rule | Status | Evidence |
|---|---|---|
| SQL injection: prepared statements only | met | IQueryBuilder in all mappers; no raw SQL in the sweep; backend store with parameterised sqlite queries |
| XSS: sanitise templates and the DOM | met | Review page as a Vue app with template escaping, CSP without inline scripts; no innerHTML with user data (sweep) |
| Clickjacking | met | Default headers left untouched |
| Code execution / file inclusion | met | Sweep 0 hits; documents only in the ExApp volume, never in the webroot |
| Directory traversal: Files API | met | File access through IRootFolder after the permission check; PHP writes the output as the user through the Files API, the container has no write access to user files |
| Shell injection | met | PHP calls no shell (sweep); LibreOffice/Tesseract as child processes with an argument list and no shell (phase 2 plans: jail with an emptied environment) |
| Auth bypass / privilege escalation | met | File action, review page and log check permissions in PHP; phase 1 audit verified |
| Sensitive data exposure | met | Logging hardening (no exception text, LOG_CONTEXT_KEYS gate with self-test, no path or name in the log); ways for the container to read secrets are covered by the phase 2 plans (prctl DUMPABLE=0, Landlock, frpc 0711) |
| CSRF | met | App framework default; POSTs carry the requesttoken |
| Unvalidated redirects | n/a | No redirects |
| CORS | n/a | No CORS permissions |

## App store rules (excerpt)

| Rule | Status | Evidence |
|---|---|---|
| AGPL-3.0-or-later | met | LICENSE, info.xml; PyMuPDF AGPL fits; fr_core_news_lg LGPL-LR review documented (CLAUDE.md) |
| No "Nextcloud" in the name | met | pii_redaction / pii_redaction_backend |
| Timely response to security reports | met | SECURITY.md (GitHub private reporting plus mail, 7 days); in practice: pip-audit gate on main plus CVE fix process |
| Clean install, uninstall, upgrade and downgrade | met | Migrations with tests, the enabled handler clears old states (push 11) |
| No data to third parties, privacy | met | No document content, finding or telemetry leaves the server; model downloads with a fixed sha256; switching off the network use of the libraries (tldextract/Presidio/GLiNER2) is a phase 2 criterion with a --network-none proof on the real image |
| Contact | met | GitHub issues, SECURITY.md |

## Beyond the guidelines

- Threat audit per phase (01-SECURITY.md verified, 103 threats); phase 2 IS the hardening phase (child process sandbox, fail-closed pre-check, corpus in CI)
- Workflow pins, pip-audit over the lock, composer.lock enforced
- Fail-closed as the baseline: refusal is the safe path

## Open points

- This cross-check will be extended with the sandbox evidence after the phase 2 security audit (02-SECURITY.md) (seccomp/Landlock probe, frpc 0711 measurement A1, network proof).
