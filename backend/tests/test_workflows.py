"""Triggers, size and secret reach of the workflows, read as text.

- Every workflow file stays under GitHub's 500 KB cap (Findling plan 41-08: a
  larger file is refused before any job starts).
- A push block names branches or tags, and every tag pattern is the release
  pattern, so no stray tag starts a workflow (Findling plan 31-01).
- release.yml and store-submit.yml have no pull_request trigger: that absence
  is what keeps the signing key and the store token away from forks.
- store-submit.yml runs by hand only.
- Only those two files name the signing key or the store token.
- The ExApp half lives in backend/: python.yml runs its gates there, docker.yml
  builds the image out of it, deploy-harp.yml builds the same context, and
  Dependabot watches the Dockerfile and the uv lock file there and the npm
  trees under php/ and ci/playwright/.
- No workflow or script writes to a pull request (gh pr comment, edit, review),
  and nothing that names nextcloud/app-certificate-requests runs a writing gh
  command: the certificate request is read with gh pr view only (owner rule).
"""

import re
from pathlib import Path

from pii_redaction_backend import APP_ID
from tests.conftest import REPO_ROOT

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CAP_BYTES = 500 * 1024
RELEASE_TAG = "'v[0-9]+.[0-9]+.[0-9]+'"
SECRET_HOLDERS = frozenset({"release.yml", "store-submit.yml"})
REQUIRED = ("python.yml", "php.yml", "docker.yml", "release.yml", "store-submit.yml", "deploy-harp.yml", "security.yml")


def workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def on_block(source: str) -> str:
    """The text of the top level on: block."""
    match = re.search(r"^on:\n(.*?)(?=^\S)", source, re.MULTILINE | re.DOTALL)
    assert match is not None
    return match.group(1)


def tag_patterns(source: str) -> list[str]:
    block = on_block(source)
    tags = re.search(r"^ {4}tags:\n((?: {6}- .*\n)+)", block, re.MULTILINE)
    return [line.strip()[2:] for line in tags.group(1).splitlines()] if tags else []


def test_the_required_workflows_exist() -> None:
    names = {path.name for path in workflow_files()}

    assert set(REQUIRED) <= names


def test_every_workflow_is_under_the_size_cap() -> None:
    assert [path.name for path in workflow_files() if path.stat().st_size >= CAP_BYTES] == []


def test_push_blocks_name_branches_or_release_tags_only() -> None:
    for path in workflow_files():
        source = path.read_text(encoding="utf-8")
        block = on_block(source)
        if "  push:" not in block:
            continue
        assert re.search(r"^ {4}(branches|tags):", block, re.MULTILINE), path.name
        assert all(pattern == RELEASE_TAG for pattern in tag_patterns(source)), path.name


def test_the_signing_workflows_cannot_be_started_from_a_pull_request() -> None:
    for name in SECRET_HOLDERS:
        assert "pull_request" not in on_block((WORKFLOWS / name).read_text(encoding="utf-8")), name


def test_the_store_submission_runs_by_hand_only() -> None:
    block = on_block((WORKFLOWS / "store-submit.yml").read_text(encoding="utf-8"))

    assert re.findall(r"^ {2}(\w+):", block, re.MULTILINE) == ["workflow_dispatch"]


def test_only_the_signing_workflows_name_the_key_or_the_store_token() -> None:
    for path in workflow_files():
        source = path.read_text(encoding="utf-8")
        if path.name not in SECRET_HOLDERS:
            assert "APP_PRIVATE_KEY" not in source, path.name
            assert "APPSTORE_TOKEN" not in source, path.name


def test_the_signing_workflows_refuse_other_repositories() -> None:
    # One repository carries both halves; its name follows the PHP app.
    repository = "street1983nk/nextcloud-pii-redaction"
    for name in SECRET_HOLDERS:
        assert f'"{repository}"' in (WORKFLOWS / name).read_text(encoding="utf-8"), name


def test_the_store_submission_checks_the_image_before_it_submits() -> None:
    source = (WORKFLOWS / "store-submit.yml").read_text(encoding="utf-8")

    assert source.index("imagetools inspect") < source.index("api/v1/apps/releases")
    assert "docker logout ghcr.io" in source


def test_the_tag_pattern_parser_sees_a_stray_pattern() -> None:
    sample = "on:\n  push:\n    tags:\n      - 'v[0-9]+.[0-9]+.[0-9]+'\n      - 'source-*'\njobs:\n"

    assert tag_patterns(sample) == [RELEASE_TAG, "'source-*'"]


def backend_findings(sources: dict[str, str]) -> list[str]:
    """Every place where a workflow or Dependabot misses the backend/ or php/ half."""
    findings = []
    python = sources.get("python.yml", "")
    if not re.search(r"^defaults:\n  run:\n    working-directory: backend$", python, re.MULTILINE):
        findings.append("python.yml does not run in backend/")
    docker = sources.get("docker.yml", "")
    if "context: backend\n" not in docker or "file: backend/Dockerfile\n" not in docker:
        findings.append("docker.yml does not build out of backend/")
    if f"IMAGE: ghcr.io/street1983nk/{APP_ID}\n" not in docker:
        findings.append("docker.yml does not push the backend image")
    harp = sources.get("deploy-harp.yml", "")
    if f"BACKEND_APP_ID: {APP_ID}\n" not in harp or "./app-src/backend\n" not in harp:
        findings.append("deploy-harp.yml does not deploy the backend")
    dependabot = sources.get("dependabot.yml", "")
    for ecosystem, directory in (
        ("docker", "/backend"),
        ("uv", "/backend"),
        ("npm", "/php"),
        ("npm", "/ci/playwright"),
    ):
        if not re.search(rf'package-ecosystem: {ecosystem}\n(?:    #.*\n)*    directory: "{directory}"', dependabot):
            findings.append(f"dependabot {ecosystem} does not watch {directory}")
    return findings


def real_sources() -> dict[str, str]:
    sources = {path.name: path.read_text(encoding="utf-8") for path in workflow_files()}
    sources["dependabot.yml"] = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    return sources


def test_workflows_and_dependabot_work_on_both_halves() -> None:
    assert backend_findings(real_sources()) == []


def test_the_backend_rule_fires_on_the_old_root_layout() -> None:
    old = {
        name: source.replace("working-directory: backend", "working-directory: .")
        .replace("context: backend", "context: .")
        .replace("./app-src/backend", "./app-src")
        .replace('"/backend"', '"/"')
        .replace('"/php"', '"/"')
        .replace('"/ci/playwright"', '"/"')
        for name, source in real_sources().items()
    }

    assert backend_findings(old) == [
        "python.yml does not run in backend/",
        "docker.yml does not build out of backend/",
        "deploy-harp.yml does not deploy the backend",
        "dependabot docker does not watch /backend",
        "dependabot uv does not watch /backend",
        "dependabot npm does not watch /php",
        "dependabot npm does not watch /ci/playwright",
    ]


# Writing gh commands. The words are split, so this file does not carry them
# whole; it is not scanned anyway (only .github, scripts and ci are).
PR_WRITE = re.compile(r"\bgh\s+pr\s+(?:" + "comm" + "ent|ed" + "it|rev" + r"iew)\b")
GH_WRITE = re.compile(
    r"\bgh\s+(?:"
    r"(?:pr|issue)\s+(?:comment|edit|review|create|close|reopen|merge|lock|delete)\b"
    r"|api\b[^\n]*(?:-X|--method)\s*(?:POST|PATCH|PUT|DELETE)\b"
    r"|api\b[^\n]*\s(?:-f|-F|--field|--raw-field|--input)\s"
    r")"
)
CERTIFICATE_REPOSITORY = "app-certificate" + "-requests"
SCANNED_DIRECTORIES = (".github", "scripts", "ci")


def gh_write_findings(name: str, source: str) -> list[str]:
    """A pull request write anywhere, or any gh write in a file that names the certificate repository."""
    findings = [f"{name}: {match.group(0)}" for match in PR_WRITE.finditer(source)]
    if CERTIFICATE_REPOSITORY in source:
        findings += [
            f"{name}: {match.group(0)} next to {CERTIFICATE_REPOSITORY}" for match in GH_WRITE.finditer(source)
        ]
    return findings


def scanned_files() -> list[Path]:
    """Every text file under .github, scripts and ci (the ones that exist)."""
    return sorted(
        path
        for directory in SCANNED_DIRECTORIES
        if (REPO_ROOT / directory).is_dir()
        for path in (REPO_ROOT / directory).rglob("*")
        if path.is_file()
        and "node_modules" not in path.parts
        and "__pycache__" not in path.parts
        and path.suffix not in {".png", ".svg", ".pyc"}
    )


def test_no_workflow_or_script_writes_to_a_pull_request_or_the_certificate_request() -> None:
    files = scanned_files()
    assert len(files) >= 5, "the scan found almost nothing, so it would judge nothing"

    findings = []
    for path in files:
        findings += gh_write_findings(path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8"))

    assert findings == []


def test_the_gh_write_rule_fires_on_a_mutated_sample() -> None:
    comment = "gh pr " + "comm" + "ent 1419 --body x"
    api_post = f"gh api repos/nextcloud/{CERTIFICATE_REPOSITORY}/issues/1419/comments -X POST"

    assert gh_write_findings("s", comment) == ["s: gh pr " + "comm" + "ent"]
    assert gh_write_findings("s", api_post) == [f"s: {api_post} next to {CERTIFICATE_REPOSITORY}"]
    assert gh_write_findings("s", f"gh pr view 1419 --repo nextcloud/{CERTIFICATE_REPOSITORY}") == []
    assert gh_write_findings("s", "gh pr view 12 --json state") == []


# -- deploy-harp.yml: seven legs and a fixed order of checks (plan 15) ------------

DEPLOY = "deploy-harp.yml"
LEGS = frozenset(
    {(f"stable{major}", runner, "sqlite") for major in (33, 34, 35) for runner in ("ubuntu-24.04", "ubuntu-24.04-arm")}
    | {("stable35", "ubuntu-24.04", "mariadb")}
)
# Every check of the run, in the order the workflow has to call them: the
# fixtures and the seed, the core path per format and language, the check
# scripts of plan 17, Playwright of plan 16, the measurement, the canary last.
CHECK_ORDER = (
    "ci/make_fixtures.py",
    "ci/seed.sh",
    "ci/flow.sh pdf alice",
    "ci/flow.sh docx alice",
    "ci/flow.sh odt alice",
    "ci/flow.sh pdf elke",
    "ci/flow.sh pdf fleur",
    "ci/flow.sh pdf greta",
    "ci/rights.sh",
    "ci/stale.sh",
    "ci/queue.sh",
    "ci/routes.sh",
    "npx playwright test",
    "ci/measure.sh",
    "ci/canary.sh",
)
# The scripts of the drift steps, which run after the canary on purpose.
DRIFT_SCRIPTS = ("ci/redeploy.sh", "ci/admin-state.sh", "ci/lib.sh")
_JOB_START = re.compile(r"^ {2}([\w-]+):\n", re.MULTILINE)
_LEG_START = re.compile(r"^ {10}- server-version: (\S+)$")
_LEG_FIELD = re.compile(r"^ {12}([\w-]+): (.+)$")


def job_text(source: str, name: str) -> str:
    """The text of one job of the jobs: block, up to the next job; empty when absent."""
    jobs = source.find("\njobs:\n")
    starts = [match for match in _JOB_START.finditer(source) if match.start() > jobs >= 0]
    for index, match in enumerate(starts):
        if match.group(1) == name:
            end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
            return source[match.start() : end]
    return ""


def matrix_legs(source: str) -> list[tuple[str, str, str]]:
    """(server, runner, database) of every include entry, in file order."""
    legs: list[dict[str, str]] = []
    for line in source.splitlines():
        start = _LEG_START.match(line)
        if start:
            legs.append({"server-version": start.group(1)})
            continue
        field = _LEG_FIELD.match(line)
        if field and legs:
            legs[-1][field.group(1)] = field.group(2).strip("'\"")
        elif legs and not line.startswith(" " * 12):
            break
    return [(leg["server-version"], leg.get("runner", ""), leg.get("database", "")) for leg in legs]


def _env_blocks(source: str) -> str:
    """The workflow env and the job env, the places where the runner context does not exist."""
    top = re.search(r"^env:\n(.*?)(?=^\S)", source, re.MULTILINE | re.DOTALL)
    job = re.search(r"^ {4}env:\n((?: {6}.*\n)+)", source, re.MULTILINE)
    return (top.group(1) if top else "") + (job.group(1) if job else "")


def _without_comments(source: str) -> str:
    """The file without its comment lines: the header names the checks too, in prose."""
    return "".join(line for line in source.splitlines(keepends=True) if not line.lstrip().startswith("#"))


def deploy_findings(source: str) -> list[str]:
    findings = []
    source = _without_comments(source)
    legs = matrix_legs(source)
    if len(legs) != len(set(legs)) or set(legs) != LEGS:
        findings.append(f"the matrix runs {sorted(legs)} instead of the six legs plus the MariaDB leg")
    positions = [source.find(check) for check in CHECK_ORDER]
    for check, position in zip(CHECK_ORDER, positions, strict=True):
        if position < 0:
            findings.append(f"{check} is not called")
    present = [position for position in positions if position >= 0]
    if present != sorted(present):
        findings.append("the checks are not called in the fixed order")
    # The canary is the last check of the main run; only the drift steps of
    # plan 18 follow it (a redeploy replaces the container and its log).
    main_job = job_text(source, "deploy-harp")
    scripts = re.findall(r"ci/[a-z_-]+\.sh", main_job)
    checks = [script for script in scripts if script not in DRIFT_SCRIPTS]
    if not checks or checks[-1] != "ci/canary.sh":
        findings.append("ci/canary.sh is not the last check script")
    canary = main_job.find("ci/canary.sh")
    if any(0 <= main_job.find(script) < canary for script in DRIFT_SCRIPTS):
        findings.append("a drift step runs before ci/canary.sh")
    if "NEXTCLOUD_WORKERS=8" not in source:
        findings.append("the server runs without NEXTCLOUD_WORKERS=8")
    if "repository: nextcloud/notifications\n" not in source:
        findings.append("nextcloud/notifications is not checked out")
    build, move = source.find("npm run build"), source.find("mv app-src/php apps/pii_redaction")
    if build < 0 or move < 0 or build > move:
        findings.append("the PHP app is not built before it is moved into apps/")
    if not re.search(r"'mariadb:[0-9.]+@sha256:[0-9a-f]{64}'", source):
        findings.append("the MariaDB service is not pinned by digest")
    if "--database=mysql" not in source:
        findings.append("the MariaDB leg does not install on MySQL")
    for excluded in ("!app-src/ci/out/*.sql", "!app-src/ci/out/*-dump.*"):
        if excluded not in source:
            findings.append(f"the log artifact does not exclude {excluded[1:]}")
    if "runner." in _env_blocks(source):
        findings.append("the runner context is used in a workflow or job env block")
    return findings


def deploy_source() -> str:
    return (WORKFLOWS / DEPLOY).read_text(encoding="utf-8")


def test_deploy_harp_runs_seven_legs_and_the_checks_in_order() -> None:
    assert matrix_legs(deploy_source())
    assert deploy_findings(deploy_source()) == []


def test_self_the_leg_rule_fires_without_the_mariadb_leg() -> None:
    source = deploy_source()
    mutated = source.replace("            database: mariadb\n", "            database: sqlite\n")

    assert any("MariaDB leg" in finding for finding in deploy_findings(mutated))
    assert len(matrix_legs(source)) == 7


def test_self_the_order_rule_fires_when_the_canary_runs_before_the_measurement() -> None:
    mutated = (
        deploy_source()
        .replace("bash app-src/ci/measure.sh", "bash app-src/ci/MEASURE")
        .replace("bash app-src/ci/canary.sh", "bash app-src/ci/canary.sh\n          bash app-src/ci/measure.sh")
    )

    assert "the checks are not called in the fixed order" in deploy_findings(mutated)
    assert "ci/canary.sh is not the last check script" in deploy_findings(mutated)


def test_self_a_missing_check_is_named() -> None:
    mutated = deploy_source().replace("bash app-src/ci/queue.sh", "true")

    assert "ci/queue.sh is not called" in deploy_findings(mutated)


def test_self_workers_notifications_build_digest_and_artifact_rules_fire() -> None:
    mutated = (
        deploy_source()
        .replace("NEXTCLOUD_WORKERS=8", "NEXTCLOUD_WORKERS=4")
        .replace("repository: nextcloud/notifications", "repository: nextcloud/viewer")
        .replace("&& npm run build)", ")")
        .replace("@sha256:c4124d1afa875e47f2892edf26b482fa54f796e2f342d3717a04ca091a22a9bd", "")
        .replace("            !app-src/ci/out/*.sql\n", "")
    )

    assert deploy_findings(mutated) == [
        "the server runs without NEXTCLOUD_WORKERS=8",
        "nextcloud/notifications is not checked out",
        "the PHP app is not built before it is moved into apps/",
        "the MariaDB service is not pinned by digest",
        "the log artifact does not exclude app-src/ci/out/*.sql",
    ]


def test_self_the_runner_context_in_the_job_env_is_found() -> None:
    mutated = deploy_source().replace("      NC_ROOT: ${{ github.workspace }}\n", "      NC_ROOT: ${{ runner.temp }}\n")

    assert deploy_findings(mutated) == ["the runner context is used in a workflow or job env block"]


# -- deploy-harp.yml: upgrade job and drift steps (plan 18) ------------------------

DRIFT_TAGS = ("@patch", "@drift", "@disabled", "@unreachable", "@missing", "@noappapi")
# The five tags whose state is an error: a start there is refused.
ERROR_TAGS = ("@drift", "@disabled", "@unreachable", "@missing", "@noappapi")
UPGRADE_LEGS = frozenset(
    {
        ("stable33", "ubuntu-24.04", ""),
        ("stable34", "ubuntu-24.04", ""),
        ("stable35", "ubuntu-24.04", ""),
        ("stable35", "ubuntu-24.04-arm", ""),
    }
)
# What the upgrade job does, in this order (pitfalls 7, 9 and D).
UPGRADE_ORDER = (
    "repository: nextcloud/viewer",
    "<version>${PREV_VERSION}</version>",
    '--info-xml "${RUNNER_TEMP}/info-prev.xml"',
    "ci/seed.sh",
    'wait_status alice "${job}" review',
    "STATE_DB_INODE=",
    "./occ upgrade",
    "app_api:app:update",
    'test "${inode}" = "${STATE_DB_INODE}"',
    "ci/routes.sh",
    '${APP_PATH}/review/${UPGRADE_JOB}"',
)
# At the top level of a script only: a check inside a function (DB_FILE of
# db_query) belongs to that function and is set by the script itself.
_REQUIRED_VARIABLE = re.compile(r'^:\s*"\$\{([A-Z_]+):\?', re.MULTILINE)
_STEP_START = re.compile(r"^ {6}- name: ", re.MULTILINE)


def steps_of(job: str) -> list[str]:
    """The text of every step of one job, from its - name: to the next."""
    starts = [match.start() for match in _STEP_START.finditer(job)]
    return [job[start:end] for start, end in zip(starts, [*starts[1:], len(job)], strict=True)]


def upgrade_findings(source: str) -> list[str]:
    source = _without_comments(source)
    findings = []
    if len(re.findall(r"^ {2}upgrade:\n", source, re.MULTILINE)) != 1:
        return ["there is not exactly one job upgrade"]
    job = job_text(source, "upgrade")
    legs = matrix_legs(job)
    if len(legs) != len(set(legs)) or set(legs) != UPGRADE_LEGS:
        findings.append(f"the upgrade job runs {sorted(legs)} instead of 33, 34, 35 on amd64 and 35 on arm64")
    if "ref: ${{ matrix.server-version }}\n          path: apps/viewer" not in job:
        findings.append("the upgrade job does not check out viewer in the branch of its server version")
    if "PREV_VERSION: '0.0.1'" not in job:
        findings.append("the upgrade job does not start at 0.0.1")
    positions = [job.find(mark) for mark in UPGRADE_ORDER]
    for mark, position in zip(UPGRADE_ORDER, positions, strict=True):
        if position < 0:
            findings.append(f"the upgrade job lacks {mark}")
    present = [position for position in positions if position >= 0]
    if present != sorted(present):
        findings.append("the upgrade job does not run its steps in the fixed order")
    for mark, what in (
        ("0|3)", "accepts no exit 3 of occ upgrade"),
        ("installed=$(./occ config:app:get pii_redaction installed_version)", "does not read installed_version"),
        ('test "${installed}" = "${CURR_VERSION}"', "does not check that installed_version moved"),
        ('test "${created}" = "${VOLUME_CREATED}"', "does not compare the CreatedAt of the volume"),
        ('cmp "${CI_OUT}/upgrade-job-before.tsv"', "does not compare the job row in oc_pii_jobs"),
        ('cmp "${CI_OUT}/upgrade-volume-before.txt"', "does not compare the job in state.db and its page image"),
    ):
        if mark not in job:
            findings.append(f"the upgrade job {what}")
    return findings


def drift_findings(source: str) -> list[str]:
    source = _without_comments(source)
    findings = []
    called = re.findall(r"--grep (@\w+)", source)
    for tag in DRIFT_TAGS:
        if called.count(tag) != 1:
            findings.append(f"{tag} is called {called.count(tag)} times with --grep, not once")
    steps = steps_of(job_text(source, "deploy-harp"))
    canary = next((index for index, step in enumerate(steps) if "ci/canary.sh" in step), -1)
    for tag in DRIFT_TAGS:
        holding = [index for index, step in enumerate(steps) if f"--grep {tag}" in step]
        if not holding:
            continue
        index = holding[0]
        step = steps[index]
        if index < canary:
            findings.append(f"the step of {tag} runs before ci/canary.sh")
        if tag in ERROR_TAGS and (
            'test "${code}" = "503"' not in step or "'.reason == \"backend_unavailable\"'" not in step
        ):
            findings.append(f"the step of {tag} does not check 503 backend_unavailable")
        if tag in ("@patch", "@drift") and "PII_BACKEND_VERSION=" not in step:
            findings.append(f"the step of {tag} does not name PII_BACKEND_VERSION")
        if tag == "@patch" and 'start_job alice "${file}" 201' not in step:
            findings.append("the step of @patch does not show that a start works")
    companion = [step for step in steps if "app:disable pii_redaction" in step]
    if len(companion) != 1:
        findings.append("no single step disables the PHP app")
    else:
        step = companion[0]
        for mark, what in (
            ('\'"companion": "missing"\'', "does not wait for companion missing in the container log"),
            ('\'"companion": "ok"\'', "has no positive control of the log line"),
            ("seq 1 30", "does not wait at most 60 s"),
            ('test "${status}" = "queued"', "does not read the job as queued"),
            ("app:enable pii_redaction", "does not enable the PHP app again"),
        ):
            if mark not in step:
                findings.append(f"the companion step {what}")
    return findings


def required_variables(script: str) -> list[str]:
    """The variables a script stops without: ': "${NAME:?...}"' at the top level."""
    return sorted(set(_REQUIRED_VARIABLE.findall(script)))


def unset_variable_findings(workflow: str, scripts: list[str]) -> list[str]:
    """Every required variable of the scripts is set in the workflow (pitfall 8)."""
    code = _without_comments(workflow)
    findings = []
    for name in sorted({name for script in scripts for name in required_variables(script)}):
        if not re.search(rf"^\s+{name}: |echo \"{name}=", code, re.MULTILINE):
            findings.append(f"{name} is required by a drift script and set nowhere in the workflow")
    return findings


def loglevel_findings(workflow: str, canary: str, php_sources: list[str]) -> list[str]:
    """Owner 14.11.2026: loglevel 1 in CI before the canary, never debug, never in the app."""
    code = _without_comments(workflow)
    main_job = job_text(code, "deploy-harp")
    findings = []
    setting = main_job.find("config:system:set loglevel --value=1 --type=integer")
    if setting < 0 or setting > main_job.find("ci/canary.sh"):
        findings.append("the main run does not set loglevel 1 before ci/canary.sh")
    if re.search(r"loglevel --value=0", code):
        findings.append("a workflow sets the debug loglevel 0")
    if 'entry.get("level") == 1' not in canary or "positive control failed: nextcloud.log" not in canary:
        findings.append("ci/canary.sh has no positive control of the info lines of the app")
    if any("loglevel" in text for text in php_sources):
        findings.append("the PHP app touches the loglevel")
    return findings


def _php_sources() -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted((REPO_ROOT / "php" / "lib").rglob("*.php"))]


def _ci(name: str) -> str:
    return (REPO_ROOT / "ci" / name).read_text(encoding="utf-8")


def test_the_upgrade_job_installs_0_0_1_and_proves_the_update() -> None:
    assert upgrade_findings(deploy_source()) == []


def test_every_drift_state_runs_once_after_the_canary_and_refuses_a_start() -> None:
    assert drift_findings(deploy_source()) == []


def test_every_required_variable_of_the_drift_scripts_is_set() -> None:
    scripts = [_ci("redeploy.sh"), _ci("admin-state.sh"), _ci("lib.sh")]
    assert "INFO_XML" in required_variables(scripts[0])
    assert unset_variable_findings(deploy_source(), scripts) == []


def test_ci_runs_nextcloud_log_at_info_and_the_canary_checks_it() -> None:
    php = _php_sources()
    assert len(php) >= 20, "the scan found almost no PHP file, so it would judge nothing"
    assert loglevel_findings(deploy_source(), _ci("canary.sh"), php) == []


def test_self_the_upgrade_rules_fire() -> None:
    source = deploy_source()
    renamed = source.replace("  upgrade:\n", "  upgrade-old:\n")
    assert upgrade_findings(renamed) == ["there is not exactly one job upgrade"]
    arm_leg = (
        "          - server-version: stable35\n            php-version: '8.3'\n            runner: ubuntu-24.04-arm\n"
    )
    mutated = (
        source.replace("          path: apps/viewer\n", "          path: apps/files_pdfviewer\n")
        .replace("0|3)", "0)")
        .replace('test "${inode}" = "${STATE_DB_INODE}"', "true")
        .replace(arm_leg + "    steps:", "    steps:")
    )
    found = upgrade_findings(mutated)
    assert len(found) == 4
    assert found[0].startswith("the upgrade job runs [")
    assert found[0].endswith(" instead of 33, 34, 35 on amd64 and 35 on arm64")
    assert found[1:] == [
        "the upgrade job does not check out viewer in the branch of its server version",
        'the upgrade job lacks test "${inode}" = "${STATE_DB_INODE}"',
        "the upgrade job accepts no exit 3 of occ upgrade",
    ]
    late = "bash app-src/ci/routes.sh\n\n      - name: After the update, the old job"
    early_step = "      - name: Routes too early\n        run: bash app-src/ci/routes.sh\n\n"
    first_job_step = "      - name: A job of alice up to review at 0.0.1\n"
    swapped = source.replace(late, "true\n\n      - name: After the update, the old job").replace(
        first_job_step, early_step + first_job_step
    )
    assert "the upgrade job does not run its steps in the fixed order" in upgrade_findings(swapped)


def test_self_the_drift_rules_fire() -> None:
    source = deploy_source()
    twice = source.replace("npx playwright test --grep @missing", "npx playwright test --grep @missing --grep @drift")
    assert "@drift is called 2 times with --grep, not once" in drift_findings(twice)
    no_503 = source.replace("jq -e '.reason == \"backend_unavailable\"' app-src/ci/out/start-unreachable.json", "true")
    assert drift_findings(no_503) == ["the step of @unreachable does not check 503 backend_unavailable"]
    no_version = source.replace('PII_BACKEND_VERSION="${DRIFT_MINOR_VERSION}" ', "")
    assert drift_findings(no_version) == ["the step of @drift does not name PII_BACKEND_VERSION"]
    no_queue = source.replace('test "${status}" = "queued"', "true")
    assert drift_findings(no_queue) == ["the companion step does not read the job as queued"]
    # The canary moved behind the drift steps: right before the first "Collect
    # the logs", which is the one of the main job.
    canary_step = (
        "      - name: Canary and test file names in no database, log or copy\n        run: bash app-src/ci/canary.sh\n"
    )
    collect = "      - name: Collect the logs\n"
    early = source.replace(canary_step, "").replace(collect, canary_step + "\n" + collect, 1)
    found = drift_findings(early)
    assert "the step of @patch runs before ci/canary.sh" in found
    assert "the step of @noappapi runs before ci/canary.sh" in found
    assert "a drift step runs before ci/canary.sh" in deploy_findings(early)


def test_self_a_required_variable_left_unset_is_named() -> None:
    scripts = [_ci("redeploy.sh"), _ci("admin-state.sh"), _ci("lib.sh")]
    mutated = deploy_source().replace('echo "INFO_XML=${RUNNER_TEMP}/info-citest.xml"', "true")
    assert unset_variable_findings(mutated, scripts) == [
        "INFO_XML is required by a drift script and set nowhere in the workflow"
    ]
    sample = ': "${NC_URL:?NC_URL is required}"\n: "${OTHER:-x}"\nf() {\n\t: "${INNER:?set by the script}"\n}\n'
    assert required_variables(sample) == ["NC_URL"]


def test_self_the_loglevel_rules_fire() -> None:
    canary = _ci("canary.sh")
    mutated = deploy_source().replace("loglevel --value=1 --type=integer", "loglevel --value=0 --type=integer")
    assert loglevel_findings(
        mutated, canary.replace('entry.get("level") == 1', "True"), ["$c->setValue('loglevel', 2);"]
    ) == [
        "the main run does not set loglevel 1 before ci/canary.sh",
        "a workflow sets the debug loglevel 0",
        "ci/canary.sh has no positive control of the info lines of the app",
        "the PHP app touches the loglevel",
    ]
