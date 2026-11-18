---
quick_id: 261118-hs4
status: complete
---

# Summary

Owner decision A on D-02-02 (2026-11-18): a refusal of the pre-check sends no Nextcloud notification. Real errors notify as before.

## Commits

- a2a5d59 fix: no notification for a refusal of the pre-check (product and PHPUnit)
- bb328c5 test: job_failed from a real error, none for the broken PDF (notification.spec.ts)
- 59be7ad docs: plan, state and deferred items

## Reasons

Without a notification, decided in one place (`Reason::isPrecheckRefusal()` in `php/lib/Model/Reason.php`): encrypted_pdf, encrypted_document, wrong_type, damaged, too_large, too_many_pages, unsafe_content, unsupported_format. These are the eight verdicts other than `ok` of `backend/src/pii_redaction_backend/intake/verdict.py`.

With `job_failed`, unchanged: render_failed, check_error, not_readable, download_blocked, target_not_writable, backend_unavailable, backend_state_lost, out_of_memory, leak_detected, repeatedly_stuck.

Never through `toFailed`, unchanged: e2e_encrypted, signature_declined, original_deleted, original_changed.

## Changes

- `php/lib/Model/Reason.php`: `isPrecheckRefusal()`.
- `php/lib/Service/JobService.php`: `toFailed` passes no subject for a refusal and dismisses an older notification of the job; status, reason, purge, lease and the event `failed` are unchanged.
- `php/tests/Unit/JobServiceTest.php`, `ModelTest.php`, `QueueControllerTest.php`: both sets written out as words, eight refusals without and ten errors with exactly one notification.
- `ci/playwright/notification.spec.ts`: the broken PDF ends as `damaged` without an entry; `job_failed` now comes from `target_not_writable` (folder shared read-only).
- `ci/refusals.sh` step (g) and `backend/tests/test_workflows.py` fit without a change.

## Verification

Local: ruff check and format, pyright basic, vulture, pytest -m "not container" 1474 passed, shellcheck, tsc: all green.

Proof only in CI: PHPUnit (no PHP on this machine), refusals.sh on all legs, notification.spec.ts in twelve projects. Three assumptions are read from code only: the pre-check answers `damaged` for the broken PDF in the container; a folder shared read-only is not creatable for the recipient while the file in it can be started; the OCS API accepts the folder share with the download attribute.

## Open for the owner

1. `unsupported_format` is also reported when the PHP app names no format on fetch (file gone or type changed); that case is now silent too.
2. `damaged` and `too_large` also stand for a crash or a timeout of the pre-check child; a product fault there is now silent.
3. The dismiss on refusal goes one line beyond the task.
4. README line 22 (DE/EN/FR) does not say that refused files get no notification.
5. The container chooses the word of the failure; a refusal word now also suppresses the notification. Card, status and the event `failed` remain.
