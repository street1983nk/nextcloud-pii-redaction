---
quick_id: 261128-ene
date: 2026-11-28
---

# Plan

Owner 28.11.2026 ("Ja" to: detect refuses connect() now, ocr after its measurement).
The sandbox run 46123496042 of 4fd4b05 measured PROFILE-DENY-CONNECT detect/detect ok
with presidio, spaCy and GLiNER2 loaded on amd64 and arm64. The image has no tesseract
yet (phase 12), so ocr cannot be measured; it is closed now and its first real run must
work under the refusal (product gate in test_container_soffice.py).

- `sandbox/profiles.py`: `deny_connect=True` for detect and ocr; comment names the run.
- Tests that encoded "detect and ocr keep connect()" now encode "every profile refuses
  connect()", each with a negative control built from a profile with the flag off.
- TDD: RED commit first (test_jail_profiles.py).
