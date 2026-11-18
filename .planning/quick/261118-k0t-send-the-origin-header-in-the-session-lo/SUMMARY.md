---
quick_id: 261118-k0t
status: complete
---

# Summary

CI run "Deploy through HaRP" 44310663659 on d93bf13: 10 of 12 proofs of `ci/refusals.sh` green on all seven deploy-harp legs, the two proofs with a browser session red everywhere with the same line. The fault was in the script, not in the product. The login now sends the header a browser sends, and the two proofs are stricter than before. No product code changed. Nothing pushed.

## Cause

    FAIL: the login form sent alice back to /index.php/login (HTTP 303): the login was refused

The line shows that the login page answered 200 and carried a request token; the form itself was refused.

Nextcloud Server, `core/Controller/LoginController.php`, `tryLogin`, lines 307 to 314 (read on stable33, stable34 and stable35; the section is identical on all three, https://raw.githubusercontent.com/nextcloud/server/stable33/core/Controller/LoginController.php):

    $origin = $this->request->getHeader('Origin');
    $throttle = true;
    if ($origin === '' || !$trustedDomainHelper->isTrustedUrl($origin)) {
        ...
        $error = self::LOGIN_MSG_INVALID_ORIGIN;
        $throttle = false;
    } elseif (!$this->request->passesCSRFCheck()) {

A form without the header `Origin` is refused as `invalidOrigin` before the server looks at the request token or the password, and it redirects (303) to the login page with `user` and `direct` in the query. curl sends no `Origin` with a POST, a browser does; that is why `ci/playwright` logs in and the script did not. This is read from the source, and it fits the log; the run itself did not name the reason (the old message cut the query and did not ask the server).

Ruled out by the same reading:

- Field names: `user`, `password`, `requesttoken` are enough (`rememberme`, `redirect_url`, `timezone`, `timezone_offset` have defaults).
- Request token: `data-requesttoken` in the head of the login page, accepted as POST field (`Request::passesCSRFCheck`, `lib/private/AppFramework/Http/Request.php` stable33 438 to 464: GET field, POST field or header `requesttoken`).
- Cookies: the first request without cookies gets `nc_sameSiteCookielax` and `nc_sameSiteCookiestrict` (`lib/base.php` stable33 518 to 545 and 603 to 605, `lib/OC.php` on stable35). The prefix `__Host-` applies only to secure cookies with path `/`, so not over http. `passesStrictCookieCheck` (stable33 514 to 525) wants both with the value `true` once a session cookie is sent.
- Brute force: the refusal by origin sets `throttle = false`, so the earlier attempts left no delay behind. Every leg is a fresh instance anyway.
- Trusted origin: `TrustedDomainHelper::isTrustedUrl` takes host and port of the URL, `isTrustedDomain` always allows localhost.

How the server decides on the confirm route (`SecurityMiddleware::beforeController`, stable33 188 to 207, 227 to 237; stable35 191 to 240): a route without `NoCSRFRequired` needs the strict cookie check and `passesCSRFCheck`. `passesCSRFCheck` answers true when the header `OCS-APIRequest` is set (after the cookie check, which that header also switches off), otherwise only with a valid token. Without a session cookie and without `nc_token` no cookie check takes place. A failed check throws `CrossSiteRequestForgeryException`: `CSRF check failed`, 412 (`Exceptions/CrossSiteRequestForgeryException.php`, stable33 line 20). With `Accept: application/json` the answer is JSON with `message`. A session that is not logged in is stopped earlier with 401.

`ReviewController::confirmSignature` carries `NoAdminRequired` and no `NoCSRFRequired`: the route is protected. No product fault found.

## Commits

- b772bdd fix: `ci/refusals.sh` and the gates in `backend/tests/test_workflows.py`
- bd19a57 docs: plan and state
- this summary in a commit of its own

## Changes in ci/refusals.sh

1. `session_login` sends `Origin` (scheme, host and port of `NC_URL`) with the form. The rest of the way stays: login page for the session cookie, the same-site cookies and the token, then the form. No basic auth, no `OCS-APIRequest`.
2. `csrf_refused`: the confirmation in the session of alice without a request token and with a made-up one (two base64 parts that decode to zero bytes) has to answer exactly 412 with the message `CSRF check failed`. Before, everything but 2xx passed, which a session that is not logged in (401) would have passed as well.
3. The review page is opened in the session before and after the two refused attempts (200, `data-user` alice): the session sees the job, and the refusals did not end it.
4. `signed_confirms` confirms in that same session with its token when `signed_refuses` got that far (handed over as `session` in the state folder), and logs in anew otherwise. The only difference to the refused attempts is the token. The output line says which session it was.
5. A refused login names: the code of the login page, that a token was found, the Origin sent, the names of the cookies before and after the form, the code of the form, the `Location` without its query, and the reason word of the server. The word is read from the start state `core-loginErrors` of the next login page and printed only when it is one of `invalidOrigin`, `csrfCheckFailed`, `invalidpassword`, `userdisabled`. Never a password, a token or the value of a cookie.

## What the two proofs show now, and what no longer

`signed_refuses`: bob (basic auth, as the other scripts) gets 404. A logged-in browser session of alice that can open the review page of the job gets 412 `CSRF check failed` without a token and with a made-up token. After that the session is still alice's, the job is still in `confirm`, and there is no event `signature_confirmed`.

`signed_confirms`: the same session with its own token gets 202 `queued` with `no-store`; the job reaches `review`, `signatureConfirmed` is true, `signature_notice` stands before exactly one `signature_confirmed`.

Deviations, none of them weaker:

- The refusal is accepted only as 412 with that message. Should a later server version answer a forged request differently, the proof turns red and has to be read again.
- The confirmation no longer always logs in anew. If `signed_refuses` fails before its hand-over, `signed_confirms` logs in itself, as before.

Not shown, as before: a forged request from a foreign site in a real browser (SameSite handling of the browser). The UI click on "confirm" is in `ci/playwright/review.spec.ts`.

## Gates

`backend/tests/test_workflows.py`: seven new needles (Origin header, 412, the message, the attempt without a token, the attempt with a made-up token, the hand-over of the session, the confirmation in it), one rule against a `fail` or `echo` that carries a token, a password or the cookie jar, and one new self test (`test_self_the_session_rules_fire`) that breaks each of them.

## Verification

Local, all green: ruff check and format (backend, scripts, ci), pyright basic with `PYRIGHT_PYTHON_FORCE_VERSION=latest` (0 errors), vulture, pytest -m "not container" 1476 passed (1475 plus the new self test), shellcheck 0.9.0 with `-x` over `ci/*.sh`, `bash -n` over `ci/*.sh`, `npx tsc --noEmit` in `ci/playwright`.

The session helpers and the two proofs, cut out of the script as they stand, ran against a stand-in for curl (scratch folder, not in the repository) with faults built in: login refused by origin, wrong password, login page without a token, login that leaves no session, confirm accepted without a token, confirm accepted with the made-up token, 401 in place of 412, 412 with another message, a refusal that ends the session. Each ended red at the right place with the values named, the clean run ended green with one login, and no password, token or cookie value appeared in the output. This proves the control flow in bash, nothing about Nextcloud.

Proof only in CI. No Docker and no PHP on this machine.

## Blind risks for the next run

Read from the source, never run on a real instance:

1. After the Origin check the login passes: the cookies of the jar satisfy the strict cookie check, the token of the login page is valid for the form, the answer is 303 to a page other than the login.
2. The review page of a job in `confirm` answers 200 with `data-user` and `data-requesttoken` in its head.
3. The made-up token is refused with 412 and not with an error of the server (read: `CsrfToken::getDecryptedValue`, `CsrfTokenManager::isTokenValid` with `hash_equals`).
4. The reason word in `core-loginErrors` is found on the next login page (only matters when the login fails again; otherwise the message says "not told").
5. Everything after the confirmation (the signed PDF reaches `review`, the order of the events) has not run on a real instance yet.

## Open for the owner

- Push of b772bdd, bd19a57 and the summary commit, then the CI run.
