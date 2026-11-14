# Changelog

All notable changes are listed here, newest first. The entry of a release is
written before its tag; the GitHub release carries the same facts in English.

## 0.1.0

- Two apps in lockstep: PHP app `pii_redaction` and External App `pii_redaction_backend`, same version; a difference in the last digit only shows a notice, any other difference stops new analyses
- File action "Redact / pseudonymize" in the Files app for one PDF, DOCX or ODT file; not offered for multiple selections, in the trash bin, on public share pages or on shares without download
- Every start is checked again on the server: read permission, download block without exception, file type
- One job at a time with a queue; the start message names the number of jobs ahead
- The backend converts DOCX and ODT to PDF with LibreOffice and renders page 1 as an image
- Review page `/apps/pii_redaction/review/{jobId}` with progress, page 1 and the notice "Preview without detection"
- "Create placeholder copy" places a one-page PDF next to the original with nothing from the original; name suffix `_geschwärzt`, `_redacted` or `_caviardé`, never overwrites a file
- The copy is placed by a Nextcloud background job; Cron mode recommended
- A job is bound to the etag of the file; a changed or deleted original ends it
- Notifications for review ready, analysis failed, file changed and copy created, without file names
- Admin section "PII Redaction" with the state of the backend, both versions and "Check again"
- The container has no browser routes; every request to it is signed by AppAPI
- No detection of personal data and no redaction yet
- Texts in German, English and French
