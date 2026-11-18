---
quick_id: 261118-gbl
date: 2026-11-18
---

# Fix two broken assertions in ExAppServiceTest

CI run 44285891757 (PHP gates, eb46ef4): 322 tests, 2 failures, both in the test, not in the product.

1. `testTheHighestLandlockAbiIsStillAWord`: `['landlockAbi' => 64] + self::SANDBOX` moves the key to the front; `assertSame` on arrays compares the order. Build the expectation with `array_replace` in contract order.
2. `testTheCheckChildrenAreKindsAndARocketIsNot`: `?? 'not null'` turns the correct `null` into the fallback, so `assertNull` could never pass. Assert the status, the key and the null value separately.

`php/lib/Service/ExAppService.php` stays untouched. PHPUnit runs in CI only (no local PHP).
