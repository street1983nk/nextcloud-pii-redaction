"""The two store archives: what goes in, how each is signed, which tag fits.

Since plan 01-18 one repository releases two apps (AVS plan 01-10, Findling
pattern):

- ``pii_redaction``: the PHP app, staged out of ``php/`` with an include list
  (``appinfo lib templates js css img l10n`` plus ``LICENSE`` and
  ``CHANGELOG.md``), ``.gitkeep`` removed, never ``src/``, ``node_modules/``
  or ``tests/``. The bundle ``js/pii_redaction-init.mjs`` is built first
  (``npm ci && npm run build`` in ``php/``); staging stops when it is missing
  or empty, because without it the file action never shows. Code signed with
  ``occ integrity:sign-app`` (``appinfo/signature.json``) and release signed
  with ``APP_PRIVATE_KEY``, certificate pin ``4f61842e...``.
- ``pii_redaction_backend``: the ExApp, whose archive carries
  ``backend/appinfo/info.xml`` byte for byte (``cmp``) with its empty
  ``<routes/>`` element, because AppAPI reads the routes out of the archive
  and an empty element is what empties the route list on an update (pitfall
  D). Release signed with ``BACKEND_PRIVATE_KEY``; its pin stays
  ``pending-certificate`` until app-certificate-requests PR 1419 is merged.

On a tag, release.yml compares the tag with both info.xml versions and the
image tag (lockstep). No key file is ever tracked.

The rules are read as text and, where a POSIX shell is at hand, run: the
staging subcommands are executed on a copy of the tree in a temporary
directory. Every rule has a counter sample that makes it fire.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "release" / "store-archive.sh"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
COMPANION = "pii_redaction"
BACKEND = "pii_redaction_backend"
COMPANION_DIRS = ("appinfo", "lib", "templates", "js", "css", "img", "l10n")
COMPANION_FILES = ("LICENSE", "CHANGELOG.md")
INIT_BUNDLE = "js/pii_redaction-init.mjs"
COMPANION_PIN = "4f61842edfb06ad0f8ea480d618e8d17c17dde779bcadf496a73def1e78fff22"
# Computed locally from the backend key; checked against the certificate once
# PR 1419 is merged, and only then written into BACKEND_CERT_PUBKEY_SHA256.
BACKEND_LOCAL_PIN = "7a8c64ae174d6d7aebf968519725989c5a8672d4abb54eb4366887a980ab6d4d"
PENDING = "pending-certificate"
PENDING_MESSAGE = (
    "BACKEND_PRIVATE_KEY is not set; the backend certificate request "
    "(app-certificate-requests PR 1419) must be merged first."
)
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
KEY_FILE = re.compile(r"\.(key|pem|p12|csr)$")


def function_body(script: str, name: str) -> str:
    """The body of one shell function, up to its closing brace in column one."""
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", script, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def env_value(source: str, key: str) -> str | None:
    match = re.search(rf"^  {key}: ['\"]?([^'\"\s]+)['\"]?\s*$", source, re.MULTILINE)
    return match.group(1) if match else None


def script_findings(script: str) -> list[str]:
    findings: list[str] = []
    companion = function_body(script, "stage_companion")
    backend = function_body(script, "stage_backend")
    if not companion:
        findings.append("store-archive.sh has no stage_companion")
    else:
        loop = re.search(r"for d in ([a-z0-9 ]+); do", companion)
        if loop is None or tuple(loop.group(1).split()) != COMPANION_DIRS:
            findings.append("stage_companion does not copy exactly the include list of php/")
        if '"php/${d}"' not in companion:
            findings.append("stage_companion does not copy out of php/")
        if f'/{COMPANION}"' not in companion:
            findings.append(f"stage_companion does not stage under {COMPANION}/")
        if not all(name in companion for name in COMPANION_FILES):
            findings.append("stage_companion does not take LICENSE and CHANGELOG.md along")
        if "-name '.gitkeep' -delete" not in companion:
            findings.append("stage_companion leaves .gitkeep files in the archive")
        check = companion.find(f'[ -s "php/{INIT_BUNDLE}" ]')
        copy = companion.find("for d in ")
        if check < 0 or (copy >= 0 and check > copy):
            findings.append("stage_companion does not stop before copying when the init bundle is missing or empty")
    if not backend:
        findings.append("store-archive.sh has no stage_backend")
    else:
        if f'/{BACKEND}"' not in backend:
            findings.append(f"stage_backend does not stage under {BACKEND}/")
        copies = re.findall(r"^\s*cp (?:-R )?(\S+)", backend, re.MULTILINE)
        if copies != ["backend/appinfo/info.xml", "LICENSE"]:
            findings.append("stage_backend copies more than backend/appinfo/info.xml, LICENSE and CHANGELOG.md")
        if not re.search(r"^\s*cmp backend/appinfo/info\.xml ", backend, re.MULTILINE):
            findings.append("stage_backend does not prove info.xml byte identical with cmp")
        if "<routes/>" not in backend:
            findings.append("stage_backend does not check the empty routes element")
    for command in ("stage-companion)", "stage-backend)"):
        if command not in script:
            findings.append(f"store-archive.sh does not dispatch {command[:-1]}")
    return findings


def release_findings(release: str) -> list[str]:
    findings: list[str] = []
    companion_pin = env_value(release, "CERT_PUBKEY_SHA256")
    backend_pin = env_value(release, "BACKEND_CERT_PUBKEY_SHA256")
    if companion_pin != COMPANION_PIN:
        findings.append(f"release.yml does not pin CERT_PUBKEY_SHA256 of {COMPANION} to 4f61842e...")
    if backend_pin is None or not (backend_pin == PENDING or SHA256_HEX.match(backend_pin)):
        findings.append(f"release.yml has no pin BACKEND_CERT_PUBKEY_SHA256 for {BACKEND}")
    if companion_pin is not None and companion_pin == backend_pin:
        findings.append("release.yml pins both certificates to the same key")
    if backend_pin == PENDING and BACKEND_LOCAL_PIN not in release:
        findings.append("release.yml does not note the locally computed backend pin next to pending-certificate")
    if f'check {COMPANION} "${{CERT_PUBKEY_SHA256}}"' not in release:
        findings.append("release.yml does not check the companion certificate against its pin")
    if f'check {BACKEND} "${{BACKEND_CERT_PUBKEY_SHA256}}"' not in release:
        findings.append("release.yml does not check the backend certificate against its pin")
    if "${{ secrets.APP_PRIVATE_KEY }}" not in release:
        findings.append("release.yml does not sign with APP_PRIVATE_KEY")
    if "${{ secrets.BACKEND_PRIVATE_KEY }}" not in release:
        findings.append("release.yml does not sign with BACKEND_PRIVATE_KEY")
    if PENDING_MESSAGE not in release:
        findings.append("release.yml does not stop with the sentence about the pending backend certificate")
    build = release.find("npm ci --ignore-scripts")
    built = release.find("npm run build")
    stage = release.find("store-archive.sh stage-companion")
    if build < 0 or built < 0 or stage < 0 or not build < built < stage:
        findings.append("release.yml does not build the PHP bundle before stage-companion")
    for command in ("store-archive.sh stage-companion", "store-archive.sh stage-backend"):
        if command not in release:
            findings.append(f"release.yml does not run {command}")
    for archive in (f"dist/{COMPANION}.tar.gz.sig", f"dist/{BACKEND}.tar.gz.sig"):
        if "-sign " not in release or archive not in release:
            findings.append(f"release.yml does not produce {archive}")
    if "integrity:sign-app" not in release:
        findings.append("release.yml does not code sign the PHP app")
    tag_step = re.search(r"- name: On a tag.*?(?=\n      - name: )", release, re.DOTALL)
    text = tag_step.group(0) if tag_step else ""
    for needle in ("php/appinfo/info.xml", "backend/appinfo/info.xml", "<image-tag>", "refs/tags/v"):
        if needle not in text:
            findings.append(f"the tag check of release.yml does not read {needle}")
    return findings


def tracked_key_files(names: list[str]) -> list[str]:
    return [name for name in names if KEY_FILE.search(name)]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# -- the real files -------------------------------------------------------------


def test_the_archive_script_stages_both_apps() -> None:
    assert script_findings(read(SCRIPT)) == []


def test_the_release_workflow_builds_two_archives_with_two_pins() -> None:
    assert release_findings(read(WORKFLOWS / "release.yml")) == []


def test_no_key_file_is_tracked() -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("no git on this machine")
    names = subprocess.run(  # noqa: S603
        [git, "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert len(names) > 100, "git ls-files listed almost nothing, so the rule would judge nothing"
    assert tracked_key_files(names) == []


# -- counter samples ---------------------------------------------------------------


def test_the_include_list_rule_fires_on_an_extra_directory_and_a_kept_gitkeep() -> None:
    script = read(SCRIPT)
    broken = script.replace("img l10n; do", "img l10n src; do").replace("-name '.gitkeep' -delete", "-name x")
    assert broken != script

    assert script_findings(broken) == [
        "stage_companion does not copy exactly the include list of php/",
        "stage_companion leaves .gitkeep files in the archive",
    ]


def test_the_bundle_rule_fires_when_the_check_is_gone() -> None:
    script = read(SCRIPT)
    broken = script.replace(f'[ -s "php/{INIT_BUNDLE}" ]', "true")
    assert broken != script

    assert script_findings(broken) == [
        "stage_companion does not stop before copying when the init bundle is missing or empty"
    ]


def test_the_backend_rule_fires_on_extra_content_and_a_missing_cmp() -> None:
    script = read(SCRIPT)
    broken = script.replace(
        "\tcp backend/appinfo/info.xml",
        '\tcp -R backend/l10n "${app}/l10n"\n\tcp backend/appinfo/info.xml',
    ).replace("\tcmp backend/appinfo/info.xml", "\ttrue backend/appinfo/info.xml")
    assert broken != script

    assert script_findings(broken) == [
        "stage_backend copies more than backend/appinfo/info.xml, LICENSE and CHANGELOG.md",
        "stage_backend does not prove info.xml byte identical with cmp",
    ]


def test_the_pin_rule_fires_on_a_wrong_missing_or_shared_pin() -> None:
    release = read(WORKFLOWS / "release.yml")
    shared = re.sub(
        r"(?m)^  BACKEND_CERT_PUBKEY_SHA256: .*$", f"  BACKEND_CERT_PUBKEY_SHA256: {COMPANION_PIN}", release
    )
    assert release_findings(shared) == ["release.yml pins both certificates to the same key"]

    gone = re.sub(r"(?m)^  BACKEND_CERT_PUBKEY_SHA256: .*$", "  BACKEND_CERT_PUBKEY_SHA256: ''", release)
    assert release_findings(gone) == [f"release.yml has no pin BACKEND_CERT_PUBKEY_SHA256 for {BACKEND}"]

    other = release.replace(COMPANION_PIN, "0" * 64)
    assert release_findings(other) == [f"release.yml does not pin CERT_PUBKEY_SHA256 of {COMPANION} to 4f61842e..."]

    unnoted = release.replace(BACKEND_LOCAL_PIN, "")
    assert release_findings(unnoted) == [
        "release.yml does not note the locally computed backend pin next to pending-certificate"
    ]


def test_the_signature_rule_fires_without_the_backend_key_or_its_sentence() -> None:
    release = read(WORKFLOWS / "release.yml")
    broken = release.replace("${{ secrets.BACKEND_PRIVATE_KEY }}", "${{ secrets.APP_PRIVATE_KEY }}").replace(
        PENDING_MESSAGE, "no key"
    )
    assert broken != release

    assert release_findings(broken) == [
        "release.yml does not sign with BACKEND_PRIVATE_KEY",
        "release.yml does not stop with the sentence about the pending backend certificate",
    ]


def test_the_build_and_tag_rules_fire() -> None:
    release = read(WORKFLOWS / "release.yml")
    unbuilt = release.replace("npm run build", "npm run lint")
    assert release_findings(unbuilt) == ["release.yml does not build the PHP bundle before stage-companion"]

    one_half = release.replace(
        "backend_version=$(sed -n 's:.*<version>\\([^<]*\\)</version>.*:\\1:p' backend/appinfo/info.xml",
        "backend_version=$(sed -n 's:.*<version>\\([^<]*\\)</version>.*:\\1:p' php/appinfo/info.xml",
    ).replace("<image-tag>\\([^<]*\\)</image-tag>.*:\\1:p' backend/appinfo/info.xml", "x' php/appinfo/info.xml")
    assert one_half != release
    assert release_findings(one_half) == [
        "the tag check of release.yml does not read backend/appinfo/info.xml",
        "the tag check of release.yml does not read <image-tag>",
    ]


def test_the_key_file_rule_fires_on_a_tracked_key() -> None:
    assert tracked_key_files(["README.md", "php/appinfo/info.xml"]) == []
    assert tracked_key_files(["ci/app.key", "x/cert.pem", "y.p12", "z.csr", "keys.md"]) == [
        "ci/app.key",
        "x/cert.pem",
        "y.p12",
        "z.csr",
    ]


# -- the staging run itself, on a copy of the tree ---------------------------------

SH = shutil.which("sh")
TAR = shutil.which("tar")
needs_sh = pytest.mark.skipif(SH is None, reason="no POSIX sh on this machine")


def fake_root(tmp_path: Path, script: str | None = None, *, bundle: bytes | None = b"export {}\n") -> Path:
    """The parts of the repository the script reads, plus what it must leave out.

    ``bundle`` is the content of js/pii_redaction-init.mjs; None leaves it out.
    """
    root = tmp_path / "repo"
    (root / "scripts" / "release").mkdir(parents=True)
    (root / "scripts" / "release" / "store-archive.sh").write_bytes(
        (script if script is not None else read(SCRIPT)).encode("utf-8")
    )
    for name in ("appinfo", "lib", "templates", "css", "img", "l10n"):
        shutil.copytree(REPO_ROOT / "php" / name, root / "php" / name)
    (root / "php" / "js").mkdir()
    if bundle is not None:
        (root / "php" / INIT_BUNDLE).write_bytes(bundle)
    (root / "php" / "lib" / ".gitkeep").write_bytes(b"")
    for leftover in ("src/main.ts", "node_modules/x/index.js", "tests/Unit/XTest.php"):
        path = root / "php" / leftover
        path.parent.mkdir(parents=True)
        path.write_text("leftover\n", encoding="utf-8")
    (root / "backend" / "appinfo").mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "backend" / "appinfo" / "info.xml", root / "backend" / "appinfo" / "info.xml")
    for name in COMPANION_FILES:
        shutil.copyfile(REPO_ROOT / name, root / name)
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    return subprocess.run(  # noqa: S603
        [SH, "scripts/release/store-archive.sh", *args], cwd=root, capture_output=True, text=True, check=False
    )


def tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


@needs_sh
def test_the_companion_stage_holds_the_include_list_and_nothing_else(tmp_path: Path) -> None:
    root = fake_root(tmp_path)
    result = run(root, "stage-companion", "stage")
    assert result.returncode == 0, result.stdout + result.stderr

    stage = root / "stage"
    assert [path.name for path in stage.iterdir()] == [COMPANION]
    app = stage / COMPANION
    assert sorted(path.name for path in app.iterdir()) == sorted(COMPANION_DIRS + COMPANION_FILES)
    files = tree(app)
    assert INIT_BUNDLE in files
    assert "appinfo/info.xml" in files
    assert not [
        name for name in files if name.endswith(".gitkeep") or name.split("/", 1)[0] in {"src", "node_modules", "tests"}
    ]
    assert (app / "appinfo" / "info.xml").read_bytes() == (REPO_ROOT / "php" / "appinfo" / "info.xml").read_bytes()


@needs_sh
@pytest.mark.parametrize("bundle", [None, b""], ids=["missing", "empty"])
def test_the_companion_stage_stops_without_the_init_bundle(tmp_path: Path, bundle: bytes | None) -> None:
    root = fake_root(tmp_path, bundle=bundle)
    result = run(root, "stage-companion", "stage")

    assert result.returncode != 0
    assert "pii_redaction-init.mjs" in result.stdout + result.stderr
    assert not (root / "stage" / COMPANION / "lib").exists()


@needs_sh
def test_self_a_script_without_the_bundle_check_stages_an_app_without_its_file_action(tmp_path: Path) -> None:
    # The counter sample on the running script: with the check taken out, the
    # stage succeeds although the bundle is missing, which the text rule names.
    manipulated = read(SCRIPT).replace(f'[ -s "php/{INIT_BUNDLE}" ]', "true")
    root = fake_root(tmp_path, manipulated, bundle=None)

    assert run(root, "stage-companion", "stage").returncode == 0
    assert INIT_BUNDLE not in tree(root / "stage" / COMPANION)
    assert script_findings(manipulated) == [
        "stage_companion does not stop before copying when the init bundle is missing or empty"
    ]


@needs_sh
def test_the_backend_stage_carries_info_xml_byte_for_byte_with_empty_routes(tmp_path: Path) -> None:
    root = fake_root(tmp_path)
    result = run(root, "stage-backend", "stage")
    assert result.returncode == 0, result.stdout + result.stderr

    app = root / "stage" / BACKEND
    assert tree(app) == ["CHANGELOG.md", "LICENSE", "appinfo/info.xml"]
    staged = (app / "appinfo" / "info.xml").read_bytes()
    assert staged == (REPO_ROOT / "backend" / "appinfo" / "info.xml").read_bytes()
    assert staged.count(b"<routes/>") == 1
    assert b"<route>" not in staged


@needs_sh
def test_the_backend_stage_stops_on_a_route(tmp_path: Path) -> None:
    root = fake_root(tmp_path)
    info = root / "backend" / "appinfo" / "info.xml"
    info.write_bytes(info.read_bytes().replace(b"<routes/>", b"<routes><route><url>^/status$</url></route></routes>"))
    result = run(root, "stage-backend", "stage")

    assert result.returncode != 0
    assert "routes" in result.stdout + result.stderr


@needs_sh
@pytest.mark.skipif(TAR is None, reason="no tar on this machine")
def test_packed_archives_pass_their_assertions_and_a_signed_backend_does_not(tmp_path: Path) -> None:
    root = fake_root(tmp_path)
    assert run(root, "stage-companion", "stage-php").returncode == 0
    assert run(root, "stage-backend", "stage-backend").returncode == 0
    # occ integrity:sign-app writes this file in release.yml; a stand-in here.
    # Bytes, not text: on Windows write_text would add a carriage return, and
    # pack refuses that (seen here once, the CRLF guard at work).
    (root / "stage-php" / COMPANION / "appinfo" / "signature.json").write_bytes(b"{}\n")
    for stage, app in (("stage-php", COMPANION), ("stage-backend", BACKEND)):
        packed = run(root, "pack", stage, app, f"dist/{app}.tar.gz")
        assert packed.returncode == 0, packed.stdout + packed.stderr

    companion = run(root, "assert-contents", f"dist/{COMPANION}.tar.gz", COMPANION, "1")
    backend = run(root, "assert-contents", f"dist/{BACKEND}.tar.gz", BACKEND, "0")
    assert companion.returncode == 0, companion.stdout
    assert backend.returncode == 0, backend.stdout
    assert f"{COMPANION}/{INIT_BUNDLE}" in companion.stdout

    # Counter sample: the same companion archive judged as a container half.
    wrong = run(root, "assert-contents", f"dist/{COMPANION}.tar.gz", COMPANION, "0")
    assert wrong.returncode != 0
    assert "carries a code signature" in wrong.stdout
