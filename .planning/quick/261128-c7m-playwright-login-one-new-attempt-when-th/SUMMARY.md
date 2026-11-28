---
quick_id: 261128-c7m
status: complete
date: 2026-11-28
---

# Summary

- `ci/playwright/helpers.ts`: `submitLogin` gives exactly one new attempt when the core
  answers the login with its own error page; annotation `login-retry` plus a log line.
  No retry for a wrong password or any other reason.
- Product code untouched.
- Local checks: `tsc --noEmit` in ci/playwright exit 0,
  `backend/tests/test_playwright_contract.py` 15 passed.
- CI proof pending (next push to phase-02, owner approval first).
