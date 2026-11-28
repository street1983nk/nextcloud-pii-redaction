---
quick_id: 261128-c7m
date: 2026-11-28
---

# Plan

Problem: on SQLite the Nextcloud core sometimes answers POST /index.php/login with 500
("database is locked" in nextcloud.log, PublicKeyTokenMapper::invalidate). The page then
shows the core error page and the Playwright login fails, although the app is not
involved (debug ci-erster-lauf-phase01.md, run 44346938238 attempt 1: 2 of 11 legs red,
green after the rerun).

Change in `ci/playwright/helpers.ts` only:

- `submitLogin` sends the form, then waits until either the login is left or the core
  error page (heading "Interner Serverfehler", "Internal Server Error", "Erreur interne
  du serveur") shows.
- Exactly one new attempt, and only in the second case; a wrong password or any other
  reason fails as before.
- The attempt is written as a test annotation `login-retry` and as a line in the CI log.

Checks: `npx tsc --noEmit` in ci/playwright, `backend/tests/test_playwright_contract.py`.
