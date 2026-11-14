[Deutsch](install.md) | English | [Français](install.fr.md)

# Installing PII Redaction

PII Redaction consists of two apps. Both are required and have to carry the same version:

- `pii_redaction_backend`: External App (Python container), converts DOCX and ODT to PDF, renders the page image and writes the placeholder PDF
- `pii_redaction`: PHP app, brings the file action, review page, permission checks, notifications, placing of the copy and the status section

As of 0.1.0: the review page shows a preview without detection, the copy is a placeholder. Personal data is neither searched for nor redacted yet.

## Order

1. Enable AppAPI and set up the HaRP deploy daemon.
2. Install the External App "PII Redaction Backend" (`pii_redaction_backend`) and wait until it is enabled.
3. Install and enable the app "PII Redaction" (`pii_redaction`) in the same version.
4. Keep the Notifications app enabled, otherwise no notifications appear.
5. Under Administration settings, Basic settings, set background jobs to Cron (see the section Background jobs).
6. Check the state under Administration settings, PII Redaction: expected is "Both apps are connected."

## Same version (lockstep)

- Both apps always carry the same version number. After an update, bring both apps to the same version.
- If the versions differ only in the last digit (for example 0.1.0 and 0.1.1), analyses keep running.
- If they differ in the first or second digit, no new analysis starts and no copy can be created on the review page until both apps match.
- While the PHP app is disabled, the backend takes no jobs.

## States in the status section

The status section under Administration settings, PII Redaction shows exactly one state, below it the versions of both apps, the time of the last check and the button "Check again":

- **Success, "Both apps are connected."** All is well, nothing to do.
- **Info, "Minor version difference."** The versions differ in the last digit. Analyses run; align both apps at the next update.
- **Error, "The versions do not match."** The versions differ in the first or second digit. Bring both apps to the same version.
- **Error, "The backend is not installed."** `pii_redaction_backend` is missing. Install the External App.
- **Error, "The backend is disabled."** `pii_redaction_backend` is installed but off. Enable it under Apps.
- **Error, "The backend does not respond."** The container is not running or HaRP cannot be reached. Check under Apps and in the AppAPI settings.
- **Error, "AppAPI is not enabled."** Without AppAPI the backend does not run. Enable AppAPI and set up HaRP.
- **Warning, "The state could not be checked again."** "Check again" did not get through; shown stays the state from when the page was loaded. Check again later.

With every error the link "Open Apps" leads to the app management. As long as an error lasts, no analysis starts and no copy can be created on the review page. Users see "PII Redaction is not ready. Tell your administrators." when they start one.

## Background jobs

A Nextcloud background job places the copy next to the original. In AJAX mode it only runs when someone opens a page, so the copy shows up late. Cron mode is recommended.

## Notes

- PDF, DOCX and ODT are analysed, always exactly one file. The file action is missing for a multiple selection, in the trash bin, on public share pages and for folders.
- Only one job runs at a time. Further jobs wait in the queue.
- **Changed file:** At the start the app records the state of the file (etag). If it changes afterwards, the review is out of date: the review page reports "The file has changed", the file has to be analysed again. External storages can set a new etag without a change of content, for example when they are scanned again. The app then asks for a new analysis as well. This is on purpose: better one analysis more than a copy made from a different state.
- **Download blocked:** If a share does not allow downloads, no analysis starts, without exception. If the block is set later, the review page shows no page image any more and no copy is created.
- **Deleted original:** The analysis ends, no notification follows.
- The copy is always a PDF and never overwrites an existing file. If the name is taken, ` (2)` is appended.
