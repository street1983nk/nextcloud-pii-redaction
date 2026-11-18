---
quick_id: 261118-ng9
date: 2026-11-18
---

# Review 502 test measures the frame in the final state

Run 44322550281 (6f1e7cf), leg deploy-harp stable35 amd64 sqlite: 1 of the Playwright
tests failed, `review.spec.ts` "Prüfseite: Seite 1 nicht abrufbar (Bild 502)" in
en-w1280-dark, `locator.evaluate` timeout on `.pii-review__caption:visible`.

Cause: `openReview` measures the frame right after the heading shows. In this test
the figure with its caption is on the page until the image answers 502, then
`ReviewPlaceholder.vue` swaps it for the warning card. `expectReadableFrame` counted
the caption and read it after the swap. The product is right; the harness raced.

Task: the test opens the page itself, waits for the "Load again" button and the
missing image, then measures the frame. No product change.

Proof: CI only (Playwright runs against the HaRP legs).
