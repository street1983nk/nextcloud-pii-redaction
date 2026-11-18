---
quick_id: 261118-lie
date: 2026-11-18
---

# Run the security scans on phase branches

Found on 2026-11-18: `security.yml` (CodeQL, REUSE lint, pip-audit) started on a push to main, on pull requests and on the weekly schedule only. The work of phase 02 lives on `phase-02` without a pull request, so none of the three scans ever saw it.

1. `.github/workflows/security.yml`: the push trigger names `main` and `phase-*`.
2. `backend/tests/test_workflows.py`: a gate that keeps both names in the push trigger.
