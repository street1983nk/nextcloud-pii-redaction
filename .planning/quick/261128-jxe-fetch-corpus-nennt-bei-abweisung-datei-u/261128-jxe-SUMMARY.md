---
quick_id: 261128-jxe
status: complete
date: 2026-11-28
---

# Summary

- Defect: run 46141427114 (job "Container suite amd64") stopped in "Fetch the real corpus
  with fixed hashes" with only "a corpus file was refused (host, size or checksum)", exit 2;
  which file and which reason stayed hidden (arm64 in the same run fetched all ten).
- RED `44056a9`: test_ci_fetch_corpus.py, 7 failed (3 body cases, foreign final host, table
  URL off the allowlist, redirect host, network error), control "clean run writes nothing
  to stderr" and the 35 older tests passed.
- GREEN `cd24964`: ci/fetch_corpus.py. `Refused` carries a reason, new `host_of(url)` prints
  only the hostname (never path, query or userinfo). Reasons: `checksum`,
  `size N of M bytes`, `larger than M bytes`, `host H`, `final host H`,
  `redirect to host H`. main() names the current file (`manifest.json` for the manifest,
  `outdir` for mkdir): `<file> was refused (<reason>)` or
  `<file> could not be fetched (<ExceptionType>)`, exit 2. Allowlist, size cap, sha256,
  .tmp handling, cache and manifest unchanged; no retries; no digest printed.
- Local: pytest test_ci_fetch_corpus.py + test_workflows.py 83 passed; ruff check and
  ruff format --check (138 files) green; pyright (latest) 0 errors; vulture green.
- Next step for the owner: push only after approval. The sandbox.yml cache key
  hashFiles('ci/fetch_corpus.py') changed, so the next run downloads the corpus fresh;
  if amd64 refuses again, the log names the file and the reason.
