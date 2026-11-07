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
        if path.is_file() and "node_modules" not in path.parts and path.suffix not in {".png", ".svg"}
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
