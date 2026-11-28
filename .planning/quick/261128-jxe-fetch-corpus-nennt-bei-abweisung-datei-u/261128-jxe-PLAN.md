---
quick_id: 261128-jxe
phase: quick-261128-jxe
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - backend/tests/test_ci_fetch_corpus.py
  - ci/fetch_corpus.py
autonomous: true
requirements: [QUICK-261128-jxe]
date: 2026-11-28
must_haves:
  truths:
    - "A refused corpus file is named on stderr together with its reason (checksum, size N of M bytes, larger than M bytes, host H, redirect to host H)"
    - "A network error names the file and the exception type only"
    - "No path or query of a foreign URL reaches stderr, only its host"
    - "Only the affected file is named; a clean run writes nothing to stderr"
    - "Accept/refuse behaviour is unchanged: allowlist, size cap, sha256, exit 2, no retries"
  artifacts:
    - path: "ci/fetch_corpus.py"
      provides: "Refused with reason text, host_of(url), per-file stderr message"
      contains: "def host_of"
    - path: "backend/tests/test_ci_fetch_corpus.py"
      provides: "Tests 'the refusal names the file and the reason'"
      contains: "test_a_refused_body_names_the_file_and_the_reason"
  key_links:
    - from: "ci/fetch_corpus.py main()"
      to: "Refused raised in fetch/copy_limited/AllowlistRedirects.redirect_request"
      via: "except Refused as refusal -> '{current} was refused ({refusal})'"
      pattern: "was refused \\("
---

# Plan

CI run 46141427114 ("Sandbox and network proof", job "Container suite amd64") stopped after
5 s in "Fetch the real corpus with fixed hashes" with only "a corpus file was refused (host,
size or checksum)", exit 2. arm64 in the same run fetched all ten files (13 s); a local curl
on 28.11. got all ten with the fixed size and sha256. Which file and which reason failed on
amd64 is unknown because the message hides both. That is the defect. Fix: name the file and
the reason, change nothing about what is accepted or refused.

## Interfaces (from ci/fetch_corpus.py, current state)

- `class Refused(Exception)`, raised bare today in `AllowlistRedirects.redirect_request`,
  `copy_limited` (size > limit), `fetch` (table URL not allowed, final URL not allowed,
  size or digest mismatch).
- `host_allowed(url) -> bool` (https, port 443, no userinfo, allowlist/suffix).
- `main(argv, opener=None) -> int` loops `for document in DOCUMENTS: fetch(document, outdir, opener)`
  then `write_manifest`; catches `Refused` and `OSError`, writes one generic line, returns 2.
- Test helpers already present: `FakeOpener(files, final_url=...)`, `BrokenOpener`,
  `_doc(name, data, host=...)`, `_table(monkeypatch, *docs)`.

## Tasks

<tasks>

<task type="auto">
  <name>Task 1: RED commit of the existing refusal tests</name>
  <files>backend/tests/test_ci_fetch_corpus.py</files>
  <action>
  The tests are already in the working tree (section "the refusal names the file and the
  reason", end of the file); do not change them. From backend/ run the file and confirm the
  expected RED state: 7 failing (3 parametrized body cases, foreign final host, table URL
  outside allowlist, redirect names host, network error names file), the control
  "clean run writes nothing to stderr" passing, all older tests passing. Run ruff check and
  ruff format --check on tests/test_ci_fetch_corpus.py (fix formatting only if ruff asks).
  Stage only backend/tests/test_ci_fetch_corpus.py (leave .planning/debug/ untracked) and
  commit as street1983nk with message
  "test(quick-261128-jxe): refusal names the file and the reason (RED)". Body: one or two
  lines naming run 46141427114. No "closes/fixes #N", no Claude-Session line, no
  Co-Authored-By. Use git -c user.name=street1983nk -c user.email=k.cherif@outlook.de commit.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_ci_fetch_corpus.py -q 2>&1 | tail -3  (expect "7 failed", rest passed)</automated>
  </verify>
  <done>One commit touching only the test file; 7 red, control and old tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN, fetch_corpus.py names file and reason</name>
  <files>ci/fetch_corpus.py</files>
  <behavior>
    - checksum mismatch at right size: stderr contains "a.pdf was refused (checksum)"
    - short body: "(size 5 of 10 bytes)"; body over the cap: "(larger than 10 bytes)"
    - foreign final URL https://evil.example/secret/path?q=1: "(final host evil.example)", no "secret"
    - table URL off the allowlist: "(host evil.example)"
    - redirect_request to a foreign host raises Refused whose str ends with "redirect to host evil.example"
    - OSError: "a.pdf could not be fetched (OSError)"; only the current file is named; clean run: empty stderr
  </behavior>
  <action>
  1. Add host_of(url) -> str returning only urllib.parse.urlsplit(url).hostname lowercased
     ("" if none, or a fixed marker like "?" if parsing raises ValueError); docstring says why:
     path and query can carry tokens of a login page, so only the host is ever printed.
  2. Refused keeps subclassing Exception; it is now raised with a reason string
     (str(refusal) is the reason). Update its docstring.
  3. AllowlistRedirects.redirect_request: raise Refused(f"redirect to host {host_of(newurl)}").
  4. copy_limited: raise Refused(f"larger than {limit} bytes").
  5. fetch: table URL not allowed -> Refused(f"host {host_of(document.url)}"); final URL not
     allowed -> Refused(f"final host {host_of(response.geturl())}"); split the old combined
     check: size != document.size -> Refused(f"size {size} of {document.size} bytes"), then
     digest != document.sha256 -> Refused("checksum"). Never print the digest or URL path.
  6. main: track current = "manifest.json" / document.name before each fetch (set current to
     MANIFEST before write_manifest so a manifest OSError is attributable); on Refused write
     f"{current} was refused ({refusal})\n", on OSError f"{current} could not be fetched
     ({type(error).__name__})\n"; both still return 2. Initialise current before mkdir
     (e.g. the outdir name or "outdir") so an mkdir error has a label; keep it simple.
  7. Module docstring: replace "Errors go to stderr, exit 2." with a sentence saying a refusal
     or error names the file and the reason (host only, never path or query) on stderr, exit 2.
  No retries, no change to allowlist, size cap, hashing, cache, .tmp handling or manifest.
  The sandbox.yml cache key hashFiles('ci/fetch_corpus.py') changes with this edit and forces
  a fresh download on the next run; that is intended, do not touch sandbox.yml.
  Then run all gates (see verify) until green and commit only ci/fetch_corpus.py as
  street1983nk: "fix(quick-261128-jxe): fetch_corpus names the refused file and the reason".
  Same commit rules as Task 1. Do not push.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_ci_fetch_corpus.py tests/test_workflows.py -q && uv run ruff check . ../scripts ../ci && uv run ruff format --check . ../scripts ../ci && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright && uv run vulture</automated>
  </verify>
  <done>All tests green incl. the 7 new ones; ruff, ruff format, pyright basic, vulture green; one fix commit touching only ci/fetch_corpus.py; nothing pushed.</done>
</task>

<task type="auto">
  <name>Task 3: SUMMARY</name>
  <files>.planning/quick/261128-jxe-fetch-corpus-nennt-bei-abweisung-datei-u/261128-jxe-SUMMARY.md</files>
  <action>
  Write a short English SUMMARY in the form of
  .planning/quick/261128-ene-sandbox-refuse-connect-for-detect-measur/SUMMARY.md: defect,
  change, the two commit hashes, gate results, and the next step for the owner (push only
  after owner approval; the next sandbox.yml run re-downloads the corpus because the cache
  key changed and will name the refused file on amd64 if it fails again). Commit it with the
  plan as street1983nk: "docs(quick-261128-jxe): plan and summary". Do not push.
  </action>
  <verify>
    <automated>git -C C:/Users/Student/nextcloud-pii-redaction log -3 --format="%an <%ae> %s" && git -C C:/Users/Student/nextcloud-pii-redaction log -3 --format=%B | grep -ciE "claude-session|co-authored|closes|fixes #" ; test $? -eq 1</automated>
  </verify>
  <done>SUMMARY committed; three commits by street1983nk without forbidden lines; nothing pushed.</done>
</task>

</tasks>

<threat_model>

| Boundary | Description |
|----------|-------------|
| remote hosts -> CI runner | Bodies and redirect targets are untrusted; stderr ends up in public CI logs |

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-jxe-01 | Information disclosure | stderr message for foreign host/redirect | mitigate | host_of prints only the hostname; path, query and userinfo never printed (test: "secret" not in stderr) |
| T-jxe-02 | Tampering | accept/refuse logic | mitigate | Allowlist, size cap and sha256 checks unchanged; all existing refusal tests stay green |
| T-jxe-03 | Information disclosure | hash values in logs | accept | No digest printed; reason is the word "checksum" only |

</threat_model>

## Verification

- From backend/: `uv run pytest tests/test_ci_fetch_corpus.py tests/test_workflows.py` green.
- ruff check + ruff format --check (., ../scripts, ../ci), pyright basic, vulture green.
- git log: RED commit before fix commit, author street1983nk <k.cherif@outlook.de>.

## Success criteria

The next failing corpus fetch on any runner prints which file failed and why, without leaking
URL paths, while accepting and refusing exactly what it did before.
