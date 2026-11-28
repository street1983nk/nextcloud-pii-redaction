---
quick_id: 261128-omr
phase: quick-261128-omr
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - backend/tests/test_ci_convert_corpus.py
  - ci/convert_corpus.py
  - .planning/STATE.md
  - .planning/quick/261128-omr-convert-corpus-zeitgrenze-1800-s-fuer-ar/PLAN.md
  - .planning/quick/261128-omr-convert-corpus-zeitgrenze-1800-s-fuer-ar/SUMMARY.md
autonomous: true
requirements: [QUICK-261128-omr]
date: 2026-11-28
must_haves:
  truths:
    - "Each LibreOffice conversion of ci/convert_corpus.py gets 1800 s instead of 600 s, so the arm64 BuFI conversion (451 pages, about 10 to 11 min per format) finishes instead of timing out"
    - "The reasoning for 1800 s is a short English comment at TIMEOUT_S: run 46150036977 (commit bddb6a1, 28.11.2026), amd64 190 s docx / 226 s odt, arm64 factor about 3, realistic worst case about 95 min under timeout-minutes 120"
    - "Nothing else changes: process group kill, fresh profile, manifest, result words, exit codes, sandbox.yml (timeout-minutes stays 120)"
    - "A test pins TIMEOUT_S == 1800.0 and was red before the change"
  artifacts:
    - path: "ci/convert_corpus.py"
      provides: "TIMEOUT_S: Final = 1800.0 with the budget comment"
      contains: "TIMEOUT_S: Final = 1800.0"
    - path: "backend/tests/test_ci_convert_corpus.py"
      provides: "Test pinning the time limit"
      contains: "def test_the_time_limit_fits_the_arm64_bufi_conversion"
  key_links:
    - from: "ci/convert_corpus.py convert loop"
      to: "run_group(argv, timeout_s)"
      via: "run(command(pdf, work, profile, export), TIMEOUT_S)"
      pattern: "TIMEOUT_S\\)"
---

# Plan

Befund A. CI run 46150036977 (commit bddb6a1, branch phase-02): on arm64 the BuFI PDF
(BMBF_BuFI-2024_Hauptband.pdf, 451 pages) hit the 600 s limit of ci/convert_corpus.py for
DOCX and for ODT. amd64 needed 190 s (docx) and 226 s (odt). Step "Convert the PDFs": 14.5 min
on amd64, 43 min on arm64 (including the two 600 s timeouts, so about 23 min for the other four
conversions; arm64/amd64 factor about 3; BuFI on arm64 estimated 10 to 11 min per format).
Fix: TIMEOUT_S 600.0 -> 1800.0. Job budget timeout-minutes 120 stays: all six conversions at
1800 s would be too long in theory, the realistic worst case (only the two BuFI conversions at
1800 s) is about 23 + 60 + 3 build + 8 tests = about 95 min.

Decision on the budget test: test_workflows.py has the SANDBOX path and a _steps() splitter,
but no reusable parser for timeout-minutes. Per task brief: only pin the value, no budget
arithmetic test.

## Interfaces (current state)

- ci/convert_corpus.py line 47: `TIMEOUT_S: Final = 600.0`; used once in the loop:
  `run(command(pdf, work, profile, export), TIMEOUT_S)`; `run_group(argv, timeout_s)` unchanged.
- backend/tests/test_ci_convert_corpus.py: `cc()` returns the module via
  `tests.conftest.ci_module("convert_corpus")`; `FakeSoffice.__call__` asserts
  `timeout_s == cc().TIMEOUT_S` (keeps passing after the change, do not touch it).
- sandbox.yml: job `container-suite`, `timeout-minutes: 120`; convert_corpus.py is mounted
  read only, no cache keyed on its hash. Do not edit sandbox.yml.

<tasks>

<task type="auto">
  <name>Task 1: RED, a test pins the time limit at 1800 s</name>
  <files>backend/tests/test_ci_convert_corpus.py</files>
  <action>
  Add after test_the_derived_names a test named
  test_the_time_limit_fits_the_arm64_bufi_conversion asserting cc().TIMEOUT_S == 1800.0, with a
  one-line docstring in English (arm64 needs about 10 to 11 min per format for the 451-page BuFI
  PDF, run 46150036977). No other change in the file. From backend/ run the file: exactly 1
  failed (the new test), all others passed. ruff check and ruff format --check on the file.
  Stage only this file (leave .planning/debug/ untracked, never touch it) and commit with
  git -c user.name=street1983nk -c user.email=k.cherif@outlook.de commit, message
  "test(quick-261128-omr): convert_corpus time limit 1800 s (RED)", body one line naming run
  46150036977. No "closes/fixes #N", no Claude-Session line, no Co-Authored-By. Never run
  `python -` or `python -c`.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_ci_convert_corpus.py -q 2>&1 | tail -3  (expect "1 failed")</automated>
  </verify>
  <done>One commit touching only the test file; the new test red, every other test green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN, TIMEOUT_S 1800 s with the budget comment, gates, docs</name>
  <files>ci/convert_corpus.py, .planning/STATE.md, .planning/quick/261128-omr-convert-corpus-zeitgrenze-1800-s-fuer-ar/SUMMARY.md</files>
  <behavior>
    - cc().TIMEOUT_S == 1800.0; FakeSoffice still sees timeout_s == TIMEOUT_S
    - timeout path, manifest and exit codes unchanged (existing tests stay green)
  </behavior>
  <action>
  1. ci/convert_corpus.py: set TIMEOUT_S: Final = 1800.0. Directly above it add a short English
     comment (4 to 7 lines, no em or en dashes) with: 28.11.2026, run 46150036977 (commit
     bddb6a1): arm64 timed out at 600 s on the 451-page BuFI PDF for docx and odt, amd64 took
     190 s / 226 s; arm64 is about 3 times slower, so about 10 to 11 min per format; realistic
     worst case only the two BuFI conversions at the limit: about 23 + 60 + 3 build + 8 tests =
     about 95 min, under timeout-minutes 120 of sandbox.yml. No other code change.
  2. Run all gates from backend/ (see verify) until green; full suite expects 1632 or more passed.
  3. Commit only ci/convert_corpus.py, same author and rules as Task 1, message
     "fix(quick-261128-omr): convert_corpus time limit 1800 s for the arm64 BuFI conversion".
  4. .planning/STATE.md: append to the end of the "Quick Tasks Completed" table the row
     | 261128-omr | 2026-11-28 | convert_corpus time limit 1800 s for the arm64 BuFI conversion (Befund A) | done, push pending |
  5. Write SUMMARY.md in this task dir (what changed, why with the numbers, both commit hashes,
     gate results with pytest count, push pending, next proof is the next CI run on both
     architectures). Commit PLAN.md, SUMMARY.md and STATE.md as
     "docs(quick-261128-omr): plan and summary", same rules. Never push.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_ci_convert_corpus.py tests/test_workflows.py -q && uv run ruff check . ../scripts ../ci && uv run ruff format --check . ../scripts ../ci && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright && uv run vulture && uv run pytest -q 2>&1 | tail -3</automated>
  </verify>
  <done>TIMEOUT_S is 1800.0 with the budget comment; all gates green, full suite 1632+ passed; three commits (RED, fix, docs) as street1983nk, nothing pushed, .planning/debug/ untouched.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-261128-omr-01 | Denial of Service | CI job container-suite | accept | A hanging soffice now holds up to 1800 s per conversion; the group kill stays, and timeout-minutes 120 caps the job. Realistic worst case about 95 min per comment |
| T-261128-omr-02 | Information Disclosure | real corpus | accept | Unchanged: conversion runs with --network none, outputs stay in RUNNER_TEMP, never uploaded |
</threat_model>

<verification>
grep -n "TIMEOUT_S: Final = 1800.0" ci/convert_corpus.py; git log -3 --format="%an <%ae> %s" shows three commits by street1983nk; git status shows only .planning/debug/ untracked.
</verification>

<success_criteria>
Next CI run on arm64 converts the BuFI PDF to docx and odt with result=ok, job under 120 min.
</success_criteria>
