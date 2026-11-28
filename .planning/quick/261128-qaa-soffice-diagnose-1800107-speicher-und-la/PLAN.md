---
quick_id: 261128-qaa
phase: quick-261128-qaa
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - backend/tests/test_ci_soffice_diag.py
  - backend/tests/test_workflows.py
  - ci/soffice_diag.py
  - .github/workflows/sandbox.yml
  - backend/tests/test_container_soffice_diag.py
  - .planning/STATE.md
  - .planning/quick/261128-qaa-soffice-diagnose-1800107-speicher-und-la/PLAN.md
  - .planning/quick/261128-qaa-soffice-diagnose-1800107-speicher-und-la/SUMMARY.md
autonomous: true
requirements: [QUICK-261128-qaa]
date: 2026-11-28
must_haves:
  truths:
    - "Diagnosis only: sandbox/profiles.py, workers/soffice.py (DEFAULT_TIMEOUT_S 120), runner, reasons and every product file stay byte-identical; git diff of backend/src is empty"
    - "Q1: for every derived file with result ok the job log of BOTH arches has one SOFFICE-DIAG-IMAGES line with image count per format, stored image bytes, pixel sum, decoded bytes (pixels * 4) and the largest image; 1913500_pdf.odt and the BuFI odt are in it as comparison"
    - "Q1 causal control: a copy of 1800107_pdf.odt whose PNG/JPEG/GIF members are 1x1 images of the same format and name (every other zip member byte-identical) runs through the same product path as the unmodified ODT (positive control) in the same test, both with VmPeak/VmHWM from the existing Sampler"
    - "Q2: 1800107_pdf.docx runs (a) through the product path in the product jail with only the soffice wall raised to 900 s in test code, and (b) with the identical soffice command and hardened profile unjailed with a 900 s wall; each reports soffice end, soffice ms, CPU seconds, VmPeak, VmHWM, samples; the 1x1 DOCX copy runs as in (a) as control"
    - "The soffice runs happen on amd64 only (pytest.skip with a stated reason on other machines); the inventory step runs on both arches"
    - "A failing or timed out soffice never fails the job; a broken measurement does (missing diag manifest or file, zero samples where soffice ran, more or fewer than one ack, leftover profile/socket, zombie)"
    - "Corpus files and the tiny copies stay in RUNNER_TEMP and the container: no artifact, no measurements.json entry, nothing in the repo; only names and numbers in log lines"
    - "The unit tests of ci/soffice_diag.py and the workflow rules were committed red before the implementation"
  artifacts:
    - path: "ci/soffice_diag.py"
      provides: "stdlib image inventory (PNG/JPEG/GIF header parsing), tiny-image copies, manifest.json, SOFFICE-DIAG-IMAGES and SOFFICE-DIAG-STRIP lines"
      contains: "def strip("
    - path: "backend/tests/test_ci_soffice_diag.py"
      provides: "unit tests of the pure parts, pymupdf as the independent encoder and decoder"
      contains: "def test_strip_keeps_every_other_member_byte_identical"
    - path: "backend/tests/test_container_soffice_diag.py"
      provides: "the five soffice runs with SOFFICE-DIAG-RUN lines, amd64 only"
      contains: "DIAG_WALL_S: Final = 900.0"
    - path: ".github/workflows/sandbox.yml"
      provides: "inventory step in a throwaway container without network, read only mount and env of the diag folder"
      contains: "pii-sandbox:test -I /opt/soffice_diag.py /real-derived /real-diag"
  key_links:
    - from: "sandbox.yml inventory step"
      to: "ci/soffice_diag.py"
      via: "docker run --rm --network none ... -I /opt/soffice_diag.py /real-derived /real-diag"
      pattern: "soffice_diag.py /real-derived /real-diag"
    - from: "sandbox.yml Run the container tests"
      to: "tests/test_container_soffice_diag.py"
      via: "-e PII_REAL_DIAG=/real-diag in front of the existing REAL_ENV"
      pattern: "-e PII_REAL_DIAG=/real-diag -e PII_REAL_CORPUS=/real-corpus"
    - from: "tests/test_container_soffice_diag.py"
      to: "tests/test_container_corpus.py Sampler, WatchedConvert, leftovers; tests/product_path.run_product"
      via: "import, no new sampler"
      pattern: "from tests.test_container_corpus import"
---

# Plan

Owner decision 28.11.2026: before the soffice address_space cap of plan 02-24 task 3 is set, its
causes are measured. Diagnosis only, no product change.

Facts, CI run 46167327129 (commit 625eec7), product path through the jail, amd64 and arm64 nearly
identical: 1800107_pdf.odt (21.7 MB, 144 images, 112 pages) VmPeak 4.58 GB, VmHWM 4.41 GB, review,
73 to 98 s. 1800107_pdf.docx (11.7 MB, 144 images) soffice timeout at the product wall (about
125 s), VmPeak 0.65 to 0.79 GB at the kill, render_failed. sh-*.docx about 370 MB, 1913500_pdf.odt
0.79 GB, BuFI odt 1.43 GB (too_many_pages after render).

Q1: does 1800107_pdf.odt need 4.4 GB for the decoded image pixels? Q2: how long does
1800107_pdf.docx really need, and what stops it?

## Planner decisions

1. **Budget: soffice runs on amd64 only, inventory on both.** Memory is arch independent per the
   data. Worst case added on amd64: two ODT product runs about 2 x 1.5 min, the jailed DOCX at
   most 900 s but in practice bounded by RLIMIT_CPU (see 3), the unjailed DOCX at most 900 s, the
   tiny DOCX at most 900 s (expected well under 1 min): about 35 min worst, realistic about
   20 min, on an amd64 job of roughly 20 to 30 min, under timeout-minutes 120. On arm64 (job
   already 56 min, factor about 3 slower) the same runs could add up to about 100 min and break
   the 120 min budget. The inventory (zip reading, two small copies) takes seconds, so it runs
   on both arches and also checks the arch independence of the package contents.
2. **Inventory and copies in a throwaway container, like ci/convert_corpus.py.** The test image
   carries no ci/, so the script is mounted read only into `docker run --rm --network none --user
   10001:10001` with the venv python, reads the derived folder read only and writes a new
   RUNNER_TEMP/real-diag (sudo install -o 10001, 0755). The server container mounts it read only.
   No foreign package is parsed by the runner host interpreter.
3. **Q2 needs two DOCX runs, because the jail caps CPU, not only wall time.** sandbox/jail.py sets
   RLIMIT_CPU soft and hard to profile.cpu_s = wall_s + 5 = 125 s for soffice, and the jail reads
   its profile in its own process (tests/probes/as_cap.py docstring), so no test can raise it, and
   a probe can only lower a hard limit. Run (a) is the product path with soffice.convert called
   with timeout_s=900 (its existing parameter; the runner calls convert with three arguments,
   default 120): it shows whether the next wall after 120 s is RLIMIT_CPU (signal 9 or 24) or
   something else. Run (b) is the exact soffice.command with a fresh seeded and hardened job
   profile, started without the jail (no Landlock, seccomp, rlimits) in the server container,
   which itself runs with --network none: it shows the real duration and CPU seconds. Run (b)
   reads the derived file as is, the product reads the sanitized copy; written down in the line
   (mode=unjailed) and in SUMMARY.md.
4. **CPU seconds** come from resource.getrusage(RUSAGE_CHILDREN), delta around the soffice call
   only (the runner runs its children one after another; the test is subreaper, so an orphaned
   soffice.bin is counted when reaped). No new sampler: VmPeak, VmHWM, samples and as_limit come
   from Sampler of test_container_corpus.py.
5. **Tiny images: PNG, JPEG, GIF** (what the LibreOffice PDF import writes). Any other member
   below the media folder stays byte-identical and is counted as kept_other, so a contaminated
   control is visible in the log. The 1x1 images are module constants of ci/soffice_diag.py;
   the unit tests decode them with pymupdf (independent decoder, rule "Gegenprobe nie mit dem
   Muster der Umsetzung") and build the test images with pymupdf (PNG, JPEG) instead of the
   parser's own logic.
6. **Logs only.** No record_measurement call: measurements.json is uploaded as an artifact and is
   read by ci/soffice_cap.py; the diagnosis stays out of it.

## Interfaces (current state, executor greps before use)

- tests/test_container_corpus.py: `Sampler` (context manager; vmpeak_kb, vmhwm_kb, samples,
  as_limits), `WatchedConvert` (async __call__(src, outdir, job_id, *args) forwards *args to
  soffice.convert; fields end, pages, tail), `soffice_end(exc)`, `leftovers(job_id)`,
  `DASH`, `REAL_DERIVED_ENV`, `load_real_corpus(env)`. Import only these names, never a test_
  function. Its JOB_BASE 990_300, 990_390/391; other tests use 990_200, 990_210, 990_400,
  990_600. Use 990_700 to 990_704 here.
- tests/product_path.py: `run_product(source, job_id, root, convert) -> ProductRun(result,
  reason, pages, stages, ms, jail_marks)`; it raises AssertionError on anything but one ack.
- workers/soffice.py: `convert(src, outdir, job_id, timeout_s=DEFAULT_TIMEOUT_S)`,
  `command(src, outdir, job_id)`, `prepare_profile(job_id) -> (profile, env)`,
  `seed_profile(profile)`, `harden_profile(profile)`, `job_profile(job_id)`, `PROFILE_ROOT`,
  `IPC_SOCKET_GLOB`, `is_own_ipc_socket(name, info, uid)`.
- workers/child.py: `child_env(extra, *, profile=..., threads=None)`, `ChildTimeout`, `ChildFailed`;
  sandbox/reaper.py: `reap_group(pgid)`, `become_subreaper()`; tests/test_jail_container.py:
  `settled_zombies()`.
- ci/convert_corpus.py: `TARGETS` (fmt, export, media prefix: "word/media/", "Pictures/"),
  `derived_name(pdf_name, fmt)`, manifest entries name, source, format, result, bytes, images, ms.
- tests/conftest.py: `ci_module(name)`; container and linux markers skip off the container.
- tests/test_workflows.py: `SANDBOX`, `_steps(source)`, `REAL_CONVERT`, `REAL_MOUNTS`, `REAL_ENV`;
  `test_self_the_real_corpus_rules_fire` replaces `f" {REAL_ENV} sbx"`, so the new env goes in
  FRONT of REAL_ENV, and REAL_MOUNTS must still occur exactly once.

<tasks>

<task type="auto">
  <name>Task 1: RED, unit tests of ci/soffice_diag.py and the workflow rules</name>
  <files>backend/tests/test_ci_soffice_diag.py, backend/tests/test_workflows.py</files>
  <action>
  New backend/tests/test_ci_soffice_diag.py, module docstring in English, loads the script with
  `sd()` returning `ci_module("soffice_diag")` (pattern of test_ci_convert_corpus.py, zip packages
  built in memory with zipfile). Test images: PNG and JPEG of given width and height from
  pymupdf (Pixmap of csRGB with an IRect, tobytes("png") and tobytes("jpg")); GIF as a hand
  written 13 byte header plus trailer. Tests (names may vary, behavior may not):
  1. dimensions() reads width and height of PNG 3x2, JPEG 30x17 (SOF0), a JPEG with an APP1
     segment before the SOF and a JPEG with its C0 marker patched to C2 (progressive), GIF 5x7.
  2. dimensions() returns None, never raises, for empty bytes, a PNG cut after 20 bytes, a PNG
     with a wrong signature, SOI plus EOI only, a JPEG segment whose length runs past the end,
     and plain text. sniff() names png, jpeg, gif, other.
  3. Each TINY image (png, jpeg, gif) decodes with pymupdf.Pixmap(bytes) to width 1, height 1,
     and dimensions() of it is (1, 1).
  4. inventory() of a fake DOCX with two PNG (10x20, 30x40), one JPEG 8x8 and one junk .emf below
     word/media/ plus a PNG outside the prefix: images 4, png 2, jpeg 1, gif 0, other 1,
     unreadable 0, image_bytes = sum of the four member sizes, pixels 200 + 1200 + 64,
     decoded_bytes = pixels * 4, largest 30x40; the PNG outside the prefix is not counted. A
     truncated PNG below the prefix counts as png and unreadable, adds no pixels.
  5. test_strip_keeps_every_other_member_byte_identical: fake ODT with mimetype first and
     ZIP_STORED, content.xml, META-INF/manifest.xml, Pictures/a.png, Pictures/b.jpg, Pictures/c.svm:
     after strip() the copy has the same namelist in the same order, the same compress_type and
     date_time per member, mimetype still first and stored, every non-image member byte-identical
     after decompression, a.png and b.jpg equal TINY of their format, c.svm byte-identical;
     returned replaced 2, kept_other 1. Same for a fake DOCX with word/media/.
  6. strip() refuses with DiagError: a file that is not a zip, a package without image members,
     and a target that already exists (its bytes unchanged afterwards).
  7. The media prefixes of soffice_diag equal the third field of convert_corpus.TARGETS, and the
     sources of the stripped copies are exactly ("1800107.pdf",).
  8. main(): exit 2 for wrong argument count, a derived folder without manifest.json, a malformed
     manifest, a manifest where 1800107_pdf.odt or 1800107_pdf.docx is missing or has a result
     other than ok, and a named file that is absent. Exit 0 for a fake derived folder (manifest
     like convert_corpus writes it, with 1800107_pdf.docx/odt and 1913500_pdf.odt ok and one
     entry with result timeout): stdout has one SOFFICE-DIAG-IMAGES line per ok file and per tiny
     copy (the timeout entry is skipped), one SOFFICE-DIAG-STRIP line per tiny copy; outdir holds
     1800107_pdf_tiny.odt, 1800107_pdf_tiny.docx and manifest.json; the manifest holds names and
     numbers only (no value contains "/" or a drive letter).
  Use tmp_path, never `python -` or `python -c`.

  In backend/tests/test_workflows.py, below the real corpus block, add constants
  REAL_DIAG_RUN = "pii-sandbox:test -I /opt/soffice_diag.py /real-derived /real-diag",
  REAL_DIAG_MOUNT = '-v "${REAL_DIAG}:/real-diag:ro"', REAL_DIAG_ENV = "-e PII_REAL_DIAG=/real-diag",
  a function real_diag_problems(source) and two tests. Findings, one fixed string each: the
  inventory does not run exactly once in a container without network (exactly one step with
  REAL_DIAG_RUN, and that step contains "docker run --rm --network none" and
  '-v "${REAL_DERIVED}:/real-derived:ro"'); the inventory step is skipped on some runs (an
  "if:" at 8 spaces in that step); the diag folder is not mounted read only into the server
  container (REAL_DIAG_MOUNT count not 1); the container tests are not told where the diag folder
  is (a "docker exec" line ending in "-m container /app/tests" without
  f"{REAL_DIAG_ENV} {REAL_ENV}"); the diag steps run out of order (REAL_CONVERT, REAL_DIAG_RUN,
  REAL_DIAG_MOUNT, REAL_DIAG_ENV positions not ascending). test_the_diag_folder_is_made_without_network_and_mounted_read_only
  asserts no findings on the real sandbox.yml (red now); test_self_the_diag_rules_fire mutates the
  source (drop --network none of that step, add an if:, drop :ro, drop the env, missing step) and
  expects exactly the matching finding. Existing tests stay untouched.

  From backend/: run both files; expected failures are the new soffice_diag tests (module missing)
  and the new real-sandbox workflow test; every older test passes. ruff check and ruff format
  --check on both files. Stage only these two files (never touch .planning/debug/) and commit with
  git -c user.name=street1983nk -c user.email=k.cherif@outlook.de commit, message
  "test(quick-261128-qaa): soffice diagnosis inventory, tiny copies and workflow rules (RED)",
  body one line naming run 46167327129. No "closes/fixes #N", no Claude-Session line, no
  Co-Authored-By.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_ci_soffice_diag.py tests/test_workflows.py -q 2>&1 | tail -5  (expect failures only in the new tests) && uv run ruff check tests/test_ci_soffice_diag.py tests/test_workflows.py && uv run ruff format --check tests/test_ci_soffice_diag.py tests/test_workflows.py</automated>
  </verify>
  <done>One commit with the two test files; new tests red for the stated reason, all older tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN, ci/soffice_diag.py and the inventory step in sandbox.yml</name>
  <files>ci/soffice_diag.py, .github/workflows/sandbox.yml</files>
  <behavior>
    - All tests of Task 1 pass; test_workflows.py passes in full (older real corpus and tolerance rules included)
    - Script is standard library only, exit 2 on broken input, exit 0 otherwise, prints only names and numbers
  </behavior>
  <action>
  ci/soffice_diag.py in the style of ci/convert_corpus.py: module docstring (purpose: diagnosis of
  quick 261128-qaa, owner 28.11.2026, run 46167327129 facts in two lines, usage
  "python -I soffice_diag.py <derived> <outdir>", runs in a throwaway container without network,
  nothing leaves RUNNER_TEMP, the log lines, standard library only, exit codes), Final constants,
  frozen slots dataclasses Inventory (name, format, bytes, images, png, jpeg, gif, other,
  unreadable, image_bytes, pixels, decoded_bytes, largest_w, largest_h) and Stripped (name, source,
  format, replaced, kept_other, bytes), exception DiagError. Functions: sniff(data) by magic bytes;
  dimensions(data) for PNG (signature plus IHDR, big endian width and height), JPEG (walk the
  segments from SOI, skip fill bytes and standalone markers, first SOF0 to SOF15 except C4, C8,
  CC gives height then width, any length past the end gives None), GIF (87a or 89a, little endian
  logical screen size), zero sizes count as None; inventory(path, prefix) over ZipInfo entries
  below prefix that are not folders, image_bytes from file_size, pixels from dimensions,
  decoded_bytes = pixels * 4; TINY mapping for png (build at import from struct and zlib with
  CRCs, 1x1 RGBA), jpeg (a fixed baseline 1x1 byte constant), gif (fixed 1x1 constant); strip(src,
  dst, prefix) opens dst with mode "xb", copies every ZipInfo in order with writestr(info, data)
  so name, date_time, compress_type and attributes stay, replaces png/jpeg/gif members below the
  prefix with TINY of their sniffed format, keeps others; DiagError for BadZipFile, no image
  member, existing dst. Prefix per format: docx "word/media/", odt "Pictures/". STRIP_SOURCES =
  ("1800107.pdf",); tiny name "<stem>_tiny.<fmt>" from the derived name. main(argv): read
  <derived>/manifest.json "files", inventory every entry with result ok (line SOFFICE-DIAG-IMAGES
  doc= format= bytes= images= png= jpeg= gif= other= unreadable= image_bytes= pixels=
  decoded_bytes= largest_px=<w>x<h>), make both tiny copies of STRIP_SOURCES, inventory them too,
  print SOFFICE-DIAG-STRIP doc= source= format= replaced= kept_other= bytes=, write
  <outdir>/manifest.json with "inventory" and "stripped" lists (asdict, names only), flush stdout.
  Exit 2 with a one-line message on stderr for every case of Task 1 test 8. No em or en dashes
  anywhere.

  .github/workflows/sandbox.yml: a new step directly after "Convert the PDFs of the real corpus
  outside the sandbox", named "Inventory the images of the derived files and make the tiny copies",
  with a comment (owner 28.11.2026, quick 261128-qaa, why both arches: seconds; the soffice runs of
  the diagnosis are amd64 only, see tests/test_container_soffice_diag.py; never uploaded). Body:
  diag="${RUNNER_TEMP}/real-diag"; sudo install -d -o 10001 -g 10001 -m 0755 "${diag}"; docker run
  --rm --network none --user 10001:10001 --entrypoint /app/.venv/bin/python with
  -v "${REAL_DERIVED}:/real-derived:ro" -v "${diag}:/real-diag" and
  -v "${GITHUB_WORKSPACE}/ci/soffice_diag.py:/opt/soffice_diag.py:ro", then
  pii-sandbox:test -I /opt/soffice_diag.py /real-derived /real-diag; test -f
  "${diag}/manifest.json"; echo "REAL_DIAG=${diag}" >> "${GITHUB_ENV}". No if:. In "Start the
  server as PID 1 without a network" add the line -v "${REAL_DIAG}:/real-diag:ro" \ directly after
  the REAL_MOUNTS line. In "Run the container tests" insert "-e PII_REAL_DIAG=/real-diag" directly
  before "-e PII_REAL_CORPUS=/real-corpus". timeout-minutes stays 120; nothing else changes.

  Gates from backend/ (see verify) until green. Commit ci/soffice_diag.py and sandbox.yml, same
  author and rules as Task 1, message "ci(quick-261128-qaa): image inventory and tiny copies of the
  1800107 conversions for the soffice diagnosis".
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_ci_soffice_diag.py tests/test_workflows.py tests/test_ci_convert_corpus.py -q && uv run ruff check . ../scripts ../ci && uv run ruff format --check . ../scripts ../ci && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright && uv run vulture</automated>
  </verify>
  <done>All Task 1 tests green, workflow rules green, ruff/pyright/vulture clean; one ci commit; no file below backend/src touched.</done>
</task>

<task type="auto">
  <name>Task 3: Container diagnosis runs, full gates, STATE and SUMMARY</name>
  <files>backend/tests/test_container_soffice_diag.py, .planning/STATE.md, .planning/quick/261128-qaa-soffice-diagnose-1800107-speicher-und-la/SUMMARY.md</files>
  <action>
  New backend/tests/test_container_soffice_diag.py, pytestmark container and linux, module docstring
  (owner 28.11.2026, Q1 and Q2, decisions 1, 3, 4 of this plan in short, the log line format, that
  only the diagnosis code raises the wall and profiles.py is unchanged). Constants:
  REAL_DIAG_ENV = "PII_REAL_DIAG", DIAG_WALL_S: Final = 900.0, JOB_BASE: Final = 990_700,
  AMD64: Final = frozenset({"x86_64", "amd64"}). Imports from tests.test_container_corpus only
  Sampler, WatchedConvert, soffice_end, leftovers, DASH, load_real_corpus (no test function), plus
  product_path, soffice, child, reap_group, become_subreaper, settled_zombies.

  One async test, test_soffice_diagnosis_of_the_1800107_conversions: first, if
  platform.machine().lower() not in AMD64, pytest.skip("soffice diagnosis on amd64 only: job
  budget, quick 261128-qaa"). Then become_subreaper(); load the real corpus (fails loudly when
  absent); PII_REAL_DIAG must name a folder with manifest.json, else pytest.fail; every file used
  must exist, else pytest.fail. Runs in this order, each with its own job id and tmp folder, each
  inside a Sampler:
  1. odt original, product path, plain WatchedConvert (product wall 120 s): positive control.
  2. odt tiny copy, product path, plain WatchedConvert: causal control.
  3. docx original, product path, convert wrapper that calls the WatchedConvert with timeout_s =
     DIAG_WALL_S (mode product_wall900).
  4. docx tiny copy, same as 3.
  5. docx original unjailed (mode unjailed_wall900): helper that takes job_profile via
     soffice.prepare_profile, seed_profile, harden_profile, removes own IPC sockets before and
     after (soffice.is_own_ipc_socket over PROFILE_ROOT glob IPC_SOCKET_GLOB), starts
     soffice.command(src, outdir, job id) with asyncio.create_subprocess_exec, env
     child.child_env(env, profile="soffice"), stdin/stdout/stderr DEVNULL, cwd outdir,
     start_new_session=True; asyncio.wait_for DIAG_WALL_S, on TimeoutError os.killpg SIGKILL and
     wait; finally reap_group(pid) and rmtree of the profile. End word: pdf (exit 0 and exactly
     one PDF), no_pdf, timeout, exit=<code>.
  Around every soffice call (inside the wrappers) measure soffice ms with time.monotonic and CPU
  seconds as the delta of resource.getrusage(RUSAGE_CHILDREN) ru_utime + ru_stime. One line per
  run, printed outside the capture (capsys.disabled, like _say):
  SOFFICE-DIAG-RUN doc=<name> variant=<original|tiny> mode=<product|product_wall900|unjailed_wall900>
  result=<word|-> reason=<word|-> soffice=<end> soffice_ms=<n> cpu_s=<n.n> vmpeak_kb= vmhwm_kb=
  samples= as_limit= wall_s=<120|900> pages=<n|->, plus SOFFICE-DIAG-TAIL doc= mode= tail= (600
  chars) when WatchedConvert kept a tail, and finally JAIL-ZOMBIES after=diag n=<n>.
  Asserts only on the measurement, never on what soffice did: every run where soffice started has
  samples > 0 and vmpeak_kb > 0; jailed runs have as_limit unlimited; run_product returned (one
  ack); leftovers(job id) is empty after each run; settled_zombies() is empty at the end. A
  timeout, a signal or render_failed is reported, not asserted.

  Locally (Windows) the file must collect and skip (container only); docker stays off unless
  4 GiB RAM are free and no other Docker work runs (optional, CI is the measurement). Full gates
  from backend/ (verify), full suite at least baseline 1633 passed (new unit tests on top), skips
  74 plus one. Commit the file, same author and rules, message "ci(quick-261128-qaa): container
  diagnosis of the 1800107 conversions, amd64 only".

  .planning/STATE.md: append to the end of the "Quick Tasks Completed" table the row
  | 261128-qaa | 2026-11-28 | soffice diagnosis: why 1800107_pdf.odt needs 4.4 GB and how long 1800107_pdf.docx needs (measurement only) | done, push pending |
  Write SUMMARY.md in this task dir: what was added and why (facts of run 46167327129), the budget
  decision, the RLIMIT_CPU finding (125 s hard in the jail, so run 5 exists), the unjailed versus
  sanitized-copy difference, the commit hashes, gate results with pytest counts, push pending,
  how to read the next CI run (Q1: VmHWM of run 2 against run 1 and decoded_bytes of the
  inventory; Q2: soffice end and cpu_s of run 3 against soffice_ms of run 5). Commit PLAN.md,
  SUMMARY.md and STATE.md as "docs(quick-261128-qaa): plan and summary", same rules. Never push,
  never touch .planning/debug/, never `python -` or `python -c`.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_container_soffice_diag.py -q -rs 2>&1 | tail -3 && uv run ruff check . ../scripts ../ci && uv run ruff format --check . ../scripts ../ci && PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright && uv run vulture && uv run pytest -q 2>&1 | tail -3 && git diff --stat HEAD~4 -- src</automated>
  </verify>
  <done>Container test collects and skips off the container; all gates green with 1633 plus new passed; four commits (RED, two ci, docs) as street1983nk; backend/src unchanged; nothing pushed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| runtime download to CI | public PDFs and the LibreOffice derived packages are foreign input to the inventory script and to soffice |
| CI log and artifacts | everything printed or uploaded leaves the runner |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-261128-qaa-01 | Information Disclosure | tiny copies, derived files | mitigate | Written only to RUNNER_TEMP/real-diag and container tmp_path; the upload step names only measurements/; no record_measurement; workflow rule "an artifact names the real corpus" covers the real-diag path; manifest and lines carry names and numbers only (unit test 8) |
| T-261128-qaa-02 | Tampering / DoS | ci/soffice_diag.py parsing foreign zips | mitigate | Runs in a throwaway container with --network none as uid 10001, input mounted read only; header parsers bounds-checked and return None instead of raising (unit test 2); output opened with "xb" |
| T-261128-qaa-03 | Elevation of Privilege | unjailed soffice run 5 | accept | Diagnosis only, public documents with fixed sha256, inside the server container that has --network none, as uid 10001, own profile removed afterwards; never reachable from the product (test code only) |
| T-261128-qaa-04 | Denial of Service | CI job budget | mitigate | soffice runs amd64 only, every run capped at 900 s and killed by process group; worst case about 35 min on top of the amd64 job, under timeout-minutes 120 |
| T-261128-qaa-05 | Repudiation / integrity of the measurement | container diag test | mitigate | Fails on missing files, zero samples, leftover profile or socket, zombies; positive control (run 1) in the same test as the causal control (run 2) |
</threat_model>

<verification>
git log -4 --format="%an <%ae> %s" shows the RED, two ci and the docs commit by street1983nk; git diff HEAD~4 -- backend/src is empty; git status shows only .planning/debug/ untracked; grep -n "soffice_diag.py /real-derived /real-diag" .github/workflows/sandbox.yml finds one line.
</verification>

<success_criteria>
Next CI run (after the owner pushes): both arches print SOFFICE-DIAG-IMAGES for all derived files
and SOFFICE-DIAG-STRIP for both tiny copies; amd64 prints five SOFFICE-DIAG-RUN lines and
JAIL-ZOMBIES after=diag n=0; arm64 shows the stated skip; both jobs green and under 120 min. The
numbers answer Q1 (VmHWM of the tiny ODT against about 4.4 GB of the original) and Q2 (what stops
the jailed DOCX at 900 s wall, and how long and how many CPU seconds it really takes unjailed).
</success_criteria>

<output>
Create `.planning/quick/261128-qaa-soffice-diagnose-1800107-speicher-und-la/SUMMARY.md` when done
</output>
