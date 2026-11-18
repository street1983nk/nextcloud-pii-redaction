---
quick_id: 261118-io7
status: complete
---

# Summary

CI run "Deploy through HaRP" 44300061301 on c025b96 was red on all seven deploy-harp legs in the step of `ci/refusals.sh`. The fault was in the script, not in the product. The script is corrected and every proof now runs on its own. No product code changed. Nothing pushed.

## Cause

All seven legs (stable33, 34, 35 on amd64 and arm64 with SQLite, stable35 amd64 with MariaDB) stopped at the same line, 30 to 36 seconds into the step, with the same two lines:

    job 13 has 1 notifications (A review is ready), expected one review_ready
    FAIL: positive control failed: the API shows no review_ready for job 13

- `ci/refusals.sh:135` (old) printed the field `subject` of the OCS notifications API, and `ci/refusals.sh:150` (old) compared it with the word `review_ready`.
- `php/lib/Service/NotificationSender.php:44` stores the word with `setSubject($subject->value)`; it lands in `oc_notifications.subject`.
- `php/lib/Notification/Notifier.php:53` and `:58` render the title from the catalog (`A review is ready`) with `setParsedSubject`. The API of the notifications app hands out this rendered title as `subject`; the script found no field with the word in it (read from the answer of the run and from `ci/stale.sh`, not from the source of the notifications app).
- `ci/stale.sh:33` to `:37` already said so and reads the word from the table.

The product did what it should: exactly one notification for the job, the right one. No other error is in the log; what comes after the first stop was never run.

## Commits

- 4c364e7 fix: `ci/refusals.sh` and the gates in `backend/tests/test_workflows.py`
- 9597ac4 docs: plan and state

## Changes in ci/refusals.sh

1. `seen_notification` asks two witnesses. The API: exactly one notification of the job that the user sees, with a title and the link to `/apps/pii_redaction/review/<job>`. The table: exactly the subject word. The title is printed (ASCII only) and never compared, so the language of the account plays no part. The positive control checks more than before, not less.
2. Every proof runs in a process of its own (`proof`): control, second control, four refusals, E2E refusal, E2E control, signed PDF waits, confirm refused, confirm accepted, the judgement on D-02-02. A failed proof is named, the others run, and the script ends red when one failed or was not run. A proof that failed after 180 s or more stops the rest (they count as not run), so a stuck queue does not cost half an hour.
3. The judgement on D-02-02 refuses to judge when the positive control did not pass, and reports when fewer than four refusals happened.

Corrected ahead of the next run, each read against the product code:

- A race in the count: `before_refusals` was taken right after the second control reached review. `JobService::finish` (`php/lib/Service/JobService.php:425`) stores the state before it sends the notification, so a `review_ready` arriving a moment later would have looked like a notification of a refusal. The second control now waits for its notification.
- A race at the signed PDF: `JobService::toConfirm` (`:294` to `:302`) stores the state `confirm` first and records `signature_notice` after it. The script asked for the event at once; it now waits up to 10 s.
- `has_event` took a failed database query for "no such event". In the two checks that expect no event (`signature_confirmed` before the confirmation) that would have passed silently. A failed query now stops the proof.
- The job in `confirm` is checked for no notification in the table as well, not only over the API.
- The E2E flag is taken back also when the proof before it failed half way.
- The login over the form: the redirect of a refused login also answers 303. The script now reads the target and stops when it leads back to the login page.
- Failure messages carry the real values: HTTP code, answer cut to 300 characters with request tokens blanked, events of the job, the `Location` without its query, the `Cache-Control` value. An answer that is no JSON no longer ends in a Python traceback.

Read and left as it was (fits the product): the routes and codes of `JobController` and `ReviewController` (start 201, refused start 404 with `reason`, confirm 404 for a stranger, 202 with `status: queued`, `Cache-Control: private, no-store`), the field `signatureConfirmed`, the event names of `JobEventMapper`, the tables and columns of the migration, the SQL for both databases, the order `recordAckFlags` before `toReview`.

## Gates

`backend/tests/test_workflows.py`: the refusal calls are now `proof refused <file> <reason>`; five new needles (subject word from the table, comparison of the word, the API as witness, no judgement without the control, red end) and a rule against a proof behind `if`, `!`, `||` or `&&` (bash would switch errexit off inside it). One new self test, the old ones follow.

## Verification

Local, all green: ruff check and format (backend, scripts, ci), pyright basic with `PYRIGHT_PYTHON_FORCE_VERSION=latest` (0 errors), vulture, pytest -m "not container" 1475 passed (1474 plus the new self test), shellcheck 0.9.0 over `ci/*.sh`, `bash -n` over `ci/*.sh`, `npx tsc --noEmit` in `ci/playwright`.

In addition the script ran against a stand-in for `ci/lib.sh` (no network, no database, in the scratch folder, not in the repository) with faults built in: wrong subject word, no notification, wrong reason, start below the E2E folder not refused, login refused, confirm accepted without the token, notification for a refusal, a wait that runs out. Each ended red with the right proofs named, the clean run ended green. This proves the control flow of the script in bash, nothing about Nextcloud.

Proof only in CI: the whole script on the seven legs. No Docker and no PHP on this machine.

## Blind risks for the next run

Nothing after the positive control has ever run on a real instance. Read from code only:

1. `Folder::isEncrypted()` answers true after the script sets `oc_filecache.encrypted = 1` directly in the database (no cache in between, on 33, 34 and 35).
2. The login over the form with curl: request token in `data-requesttoken` of the login page, the same-site cookies in the jar, 303 on success, `data-user` in the head of the review page.
3. A POST without the request token is refused by the server (expected 412; the script accepts everything but 2xx and checks that the job stays in `confirm`).
4. The container: `ext_image.docx` reports removed links, `pdf_signed.pdf` goes to `confirm`, the four files fail with their four reasons.
5. The link of a notification ends with `/apps/pii_redaction/review/<job>` (`notification.spec.ts` expects the same).
6. The direct UPDATE on the SQLite file while the server is idle.

If one of them fails, the run now names it with the real values and still shows the others.

## Open for the owner

1. Push of 4c364e7, 9597ac4 and the commit of this summary, to get the CI proof.
2. `JobService::toConfirm` records `signature_notice` after the state is stored, and `finish` sends the notification after the state is stored. A reader can see the new state a moment before the event or the notification. Harmless for the user as far as read; the script now waits. Not changed (product code).
3. STATE.md still says in two places that the commits of 02-19 to 02-23 are unpushed; only the row of this task and `last_activity` were touched.
