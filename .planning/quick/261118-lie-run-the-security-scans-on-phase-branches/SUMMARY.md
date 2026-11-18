---
quick_id: 261118-lie
status: complete
---

# Summary

`security.yml` now also runs on a push to `phase-*`. `test_the_security_scans_run_on_main_and_on_the_phase_branches` holds the trigger; with the old inline `branches: [main]` it is red.

Local: tests/test_workflows.py 39 passed, ruff check and format clean, pyright 0 errors.

pip-audit run locally the way the workflow runs it (export of the locked runtime set without dev, torch under its upstream version, `--strict --disable-pip`): 95 packages, no known vulnerabilities.

Proof only in CI: CodeQL and the REUSE lint have never seen the tree of `phase-02`. Their first run after the push can be red for reasons that are older than this change.
