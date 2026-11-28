---
quick_id: 261128-ene
status: complete
date: 2026-11-28
---

# Summary

- RED `d7e3a43`: test_jail_profiles.py, 2 failed (every profile refuses connect(); the
  comment names run 46123496042).
- GREEN: `profiles.py` detect and ocr `deny_connect=True`; adjusted tests in
  test_jail.py (CONNECT_REFUSED all six, negative control via a profile with the flag
  off), test_soffice_risks.py (variant equals product, jails_for product only,
  DENY_GATED empty), test_container_soffice.py (CONNECT_REFUSED all six, gate
  `== set(PROFILES)`, DENY_GATED empty, docstrings).
- Local: pytest 1478 passed, 70 skipped; ruff, ruff format, pyright, vulture green.
- CI proof pending (sandbox.yml: SOCKET-CONNECT detect/ocr refused EACCES, PROFILE-WORK
  detect product_ok=ja on both architectures). Push only after owner approval.
