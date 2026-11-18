---
quick_id: 261118-ng9
status: complete
date: 2026-11-18
---

# Summary

- `ci/playwright/review.spec.ts`: the 502 test no longer goes through `openReview`;
  it waits for the final state (button "Load again", no image) and then calls
  `expectReadableFrame`.
- Product code untouched.
- Local check: `tsc --noEmit` in ci/playwright.
- CI proof pending (next push to phase-02).
