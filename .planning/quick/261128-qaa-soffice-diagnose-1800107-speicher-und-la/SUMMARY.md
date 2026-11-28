---
quick_id: 261128-qaa
phase: quick-261128-qaa
plan: 01
type: tdd
date: 2026-11-28
key-files:
  created:
    - ci/soffice_diag.py
    - backend/tests/test_ci_soffice_diag.py
    - backend/tests/test_container_soffice_diag.py
  modified:
    - backend/tests/test_workflows.py
    - .github/workflows/sandbox.yml
    - .planning/STATE.md
commits:
  red: 59ed926
  green: [2de7726, a08474e]
  docs: 142c3e7
status: done, push pending
---

# Quick 261128-qaa: soffice diagnosis of the 1800107 conversions

Diagnosis only, no product change (`git diff 625eec7 -- backend/src` is empty). Owner decision 28.11.2026: measure the causes before the soffice address_space cap of plan 02-24 task 3 is set.

## Questions

- Q1: does 1800107_pdf.odt (21.7 MB, 144 images, 112 pages) need its 4.4 GB VmHWM for decoded image pixels?
- Q2: how long does 1800107_pdf.docx really take, and what stops it in the product (about 125 s, render_failed)?

## What was added

- `ci/soffice_diag.py` (standard library): image inventory of every derived file (count, stored bytes, pixels, decoded_bytes = pixels * 4, largest image; PNG/JPEG/GIF headers bounds checked) and copies 1800107_pdf_tiny.odt/.docx in which every PNG/JPEG/GIF is a 1x1 image of the same name and format, all other members byte identical. Log lines SOFFICE-DIAG-IMAGES and SOFFICE-DIAG-STRIP.
- `sandbox.yml`: step after the conversion, throwaway container with `--network none`, uid 10001, derived folder read only, output in RUNNER_TEMP/real-diag (read only in the server container). Both arches. Nothing uploaded, no measurements.json entry.
- `tests/test_container_soffice_diag.py`, amd64 only (arm64 skips with the job budget as reason). Five runs with one SOFFICE-DIAG-RUN line each: ODT original (positive control), ODT tiny (causal control), DOCX original and DOCX tiny through the product path with a soffice wall of 900 s set only in the test, DOCX original unjailed with a wall of 900 s. Asserts only on the measurement (samples, VmPeak, as_limit, leftovers, zombies).

## Finding while planning

`sandbox/jail.py` sets RLIMIT_CPU soft and hard to wall_s + 5 = 125 s for soffice inside the jail process. A jailed run with a longer wall therefore still stops at about 125 CPU seconds; only the unjailed run shows the real duration.

## Gates

- RED: 27 failed, 41 passed (module missing, two new workflow rules).
- ruff check and format, pyright latest 0 errors, vulture clean.
- Full suite: 1661 passed, 75 skipped (baseline 1633 / 74).

## Deviations

- MuPDF writes progressive JPEGs (SOF2): the unit test checks that case and patches it to SOF0 for the baseline case (fix in 2de7726).
- 1x1 JPEG constant made once with Pillow in a scratch script, so pymupdf stays an independent decoder in the test.
- The unjailed run reads a byte-identical copy of the derived DOCX, not the sanitized copy the product reads; the line says mode=unjailed_wall900.
- The executor was not allowed to write this file; the orchestrator wrote it from the hand-back.

## Open

- Push (owner decides), then read the next sandbox.yml run: Q1 from run 2 against run 1 and decoded_bytes, Q2 from cpu_s and end of run 3 against run 5.
