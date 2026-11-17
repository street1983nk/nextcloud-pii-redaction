"""Static checks of the Dockerfile and the image scripts.

Images are not built on the development machine (RAM), so the rules a linter
such as hadolint would hold are held here as text, offline, on every run:
multi-stage, every base pinned by digest, a non-root user, a health check, no
ADD of a remote URL, apt lists removed, the app id in the entrypoint.
"""

import hashlib
import re

from pii_redaction_backend import APP_ID
from pii_redaction_backend.workers import soffice
from tests.conftest import BACKEND_ROOT, REPO_ROOT, repo_text

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")


def read_dockerfile() -> str:
    return repo_text(BACKEND_ROOT / "Dockerfile")


def from_lines(source: str) -> list[str]:
    return [line.split()[1] for line in source.splitlines() if line.startswith("FROM ")]


def resolved_bases(source: str) -> list[str]:
    """Every FROM and COPY --from image, with ARG defaults substituted."""
    arguments = dict(re.findall(r"^ARG (\w+)=(\S+)$", source, re.MULTILINE))
    # A FROM or COPY --from that names an earlier stage is no image of its own.
    stages = set(re.findall(r"^FROM \S+ AS ([\w-]+)", source, re.MULTILINE))
    images = [
        re.sub(r"\$\{(\w+)\}", lambda m: arguments.get(m.group(1), m.group(0)), ref)
        for ref in from_lines(source)
        if ref not in stages
    ]
    images += [ref for ref in re.findall(r"COPY --from=(\S+)", source) if ref not in stages]
    return images


def unpinned(source: str) -> list[str]:
    return [image for image in resolved_bases(source) if not DIGEST.search(image)]


TEST_STAGES = ("build-test", "test")


def stage_block(source: str, name: str) -> str:
    """The text of one stage, from its FROM line to the next FROM."""
    return source.split(f" AS {name}\n", 1)[1].split("\nFROM ", 1)[0]


def stage_findings(source: str) -> list[str]:
    """runtime is the last shipped stage: after it only the test stages, test last and FROM runtime."""
    stages = re.findall(r"^FROM (\S+) AS ([\w-]+)", source, re.MULTILINE)
    names = [name for _, name in stages]
    if "runtime" not in names:
        return ["no runtime stage"]
    findings = [
        f"stage {name} after runtime" for name in names[names.index("runtime") + 1 :] if name not in TEST_STAGES
    ]
    if stages[-1] != ("runtime", "test"):
        findings.append("the last stage is not FROM runtime AS test")
    if re.search(r"^COPY\b[^\n]*\btests\b", stage_block(source, "runtime"), re.MULTILINE):
        findings.append("the runtime stage copies tests")
    return findings


def test_runtime_is_the_last_shipped_stage() -> None:
    assert len(re.findall(r"^FROM ", read_dockerfile(), re.MULTILINE)) >= 4
    assert stage_findings(read_dockerfile()) == []


def test_the_stage_rule_fires() -> None:
    debug = read_dockerfile() + "\nFROM runtime AS debug\nRUN true\n"
    assert stage_findings(debug) == ["stage debug after runtime", "the last stage is not FROM runtime AS test"]
    leaked = read_dockerfile().replace("COPY l10n /app/l10n", "COPY l10n /app/l10n\nCOPY tests /app/tests")
    assert stage_findings(leaked) == ["the runtime stage copies tests"]


def frpc_mode_findings(source: str) -> list[str]:
    modes = re.findall(r"install -m (\d{4}) \S*frpc\S* /usr/local/bin/frpc", source)
    return [] if modes == ["0711"] else [f"frpc installed with {modes}"]


def test_frpc_is_installed_execute_only() -> None:
    assert frpc_mode_findings(read_dockerfile()) == []
    assert "install -m 0755" not in read_dockerfile()


def test_the_frpc_mode_rule_fires() -> None:
    assert frpc_mode_findings(read_dockerfile().replace("install -m 0711", "install -m 0755")) == [
        "frpc installed with ['0755']"
    ]


OFFLINE_ENV = {
    "TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS": '""',
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def offline_findings(source: str) -> list[str]:
    """The four offline variables in the ENV of the runtime stage."""
    found = dict(re.findall(r"^\s+(\w+)=(\S+?)(?: \\)?$", stage_block(source, "runtime"), re.MULTILINE))
    return [f"{name}={value} missing" for name, value in OFFLINE_ENV.items() if found.get(name) != value]


def test_offline_environment_is_set() -> None:
    assert offline_findings(read_dockerfile()) == []


def test_the_offline_rule_fires() -> None:
    assert offline_findings(read_dockerfile().replace("    HF_HUB_OFFLINE=1 \\\n", "")) == ["HF_HUB_OFFLINE=1 missing"]


def test_libseccomp_is_installed() -> None:
    installs = re.findall(r"apt-get install[^\n]*", stage_block(read_dockerfile(), "runtime"))
    assert any(re.search(r"\blibseccomp2\b", line) for line in installs)


# start.sh is the HaRP contract (frpc config, TLS, socket); a change is a reviewed one.
START_SH_SHA256 = "8cf550aade2e49e1572e93304747e3e0768c8d932738132253726e97cf4a3e53"


def test_start_sh_is_unchanged() -> None:
    digest = hashlib.sha256((BACKEND_ROOT / "docker" / "start.sh").read_bytes()).hexdigest()
    assert digest == START_SH_SHA256


WORKFLOWS = BACKEND_ROOT.parent / ".github" / "workflows"


def push_target_findings(workflow: str) -> list[str]:
    """Every build-push-action that pushes names target: runtime."""
    findings = []
    for number, block in enumerate(workflow.split("uses: docker/build-push-action")[1:], start=1):
        step = re.split(r"\n\s*- (?:name|uses):", block, maxsplit=1)[0]
        pushes = re.search(r"push(?:=|:\s*)true", step)
        if pushes and not re.search(r"^\s+target: runtime\s*$", step, re.MULTILINE):
            findings.append(f"build-push-action {number} pushes without target: runtime")
    return findings


def test_the_pushed_target_is_runtime() -> None:
    texts = {path.name: path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))}
    assert "docker.yml" in texts
    assert "uses: docker/build-push-action" in texts["docker.yml"]
    assert {name: push_target_findings(text) for name, text in texts.items() if push_target_findings(text)} == {}


def test_the_push_target_rule_fires() -> None:
    docker = (WORKFLOWS / "docker.yml").read_text(encoding="utf-8")
    probe = docker.replace("          target: runtime\n", "")
    assert push_target_findings(probe) == ["build-push-action 1 pushes without target: runtime"]


def test_every_base_image_is_pinned_by_digest() -> None:
    assert resolved_bases(read_dockerfile())
    assert unpinned(read_dockerfile()) == []


def test_the_runtime_runs_as_a_fixed_non_root_user() -> None:
    runtime = read_dockerfile().split(" AS runtime", 1)[1]
    users = re.findall(r"^USER (\S+)", runtime, re.MULTILINE)

    assert users == ["10001:10001"]


def test_health_check_entrypoint_and_app_module() -> None:
    dockerfile = read_dockerfile()
    healthcheck = 'HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 CMD ["/healthcheck.sh"]'
    assert healthcheck in dockerfile
    assert f'"-m", "{APP_ID}.main"]' in dockerfile
    assert f"/nc_app_{APP_ID}_data" in dockerfile


def test_no_remote_add_and_apt_lists_are_removed() -> None:
    assert not re.search(r"^ADD\s+https?://", read_dockerfile(), re.MULTILINE)
    for block in re.findall(r"apt-get install[^\n]*(?:\n\s+[^\n]*)*", read_dockerfile()):
        assert "--no-install-recommends" in block
    assert read_dockerfile().count("apt-get update") == read_dockerfile().count("rm -rf /var/lib/apt/lists/*")


def test_the_frpc_download_is_checked_against_a_checksum() -> None:
    assert "sha256sum -c -" in read_dockerfile()
    assert len(re.findall(r"FRP_\w+_SHA256=[0-9a-f]{64}", read_dockerfile())) == 2


def test_the_image_scripts_have_a_shebang_and_strict_mode() -> None:
    for name in ("entrypoint.sh", "healthcheck.sh", "start.sh"):
        text = (BACKEND_ROOT / "docker" / name).read_text(encoding="utf-8")
        assert text.startswith("#!/bin/"), name
        assert "set -e" in text, name
        assert "\r" not in text, name


def test_the_digest_rule_fires_on_a_tag() -> None:
    sample = "ARG BASE=python:3.13-slim\nFROM ${BASE} AS build\nCOPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uv\n"

    assert unpinned(sample) == ["python:3.13-slim", "ghcr.io/astral-sh/uv:0.11"]


LIBREOFFICE_PACKAGES = (
    "libreoffice-writer-nogui",
    "fonts-liberation2",
    "fonts-dejavu-core",
    "fonts-crosextra-carlito",
    "fonts-crosextra-caladea",
)
FORBIDDEN_PACKAGES = ("default-jre", "openjdk", "libreoffice-math")


def libreoffice_findings(dockerfile: str) -> list[str]:
    """What is wrong with the LibreOffice install: one RUN, no recommends, no Java, no math."""
    findings = []
    blocks = re.split(r"(?m)^(?=[A-Z]+ )", dockerfile)
    runs = [" ".join(block.split()) for block in blocks if block.startswith("RUN ")]
    holding = [run for run in runs if "libreoffice-writer-nogui" in run]
    if len(holding) != 1:
        findings.append(f"{len(holding)} RUN lines install libreoffice-writer-nogui")
    else:
        run = holding[0]
        findings += [f"{name} missing from the install line" for name in LIBREOFFICE_PACKAGES if name not in run]
        if "--no-install-recommends" not in run:
            findings.append("recommends are installed")
    lowered = dockerfile.lower()
    findings += [f"{name} in the image" for name in FORBIDDEN_PACKAGES if name in lowered]
    return findings


def test_libreoffice_and_the_fonts_are_installed_without_java() -> None:
    assert libreoffice_findings(read_dockerfile()) == []


def test_the_libreoffice_rule_fires() -> None:
    good = "RUN apt-get install -y --no-install-recommends " + " ".join(LIBREOFFICE_PACKAGES) + "\nUSER 10001\n"
    assert libreoffice_findings(good) == []
    assert libreoffice_findings(good.replace("--no-install-recommends ", "")) == ["recommends are installed"]
    assert libreoffice_findings(good.replace(" fonts-crosextra-carlito", "")) == [
        "fonts-crosextra-carlito missing from the install line"
    ]
    assert libreoffice_findings(good + "RUN apt-get install -y default-jre\n") == ["default-jre in the image"]
    assert libreoffice_findings("USER 10001\n") == ["0 RUN lines install libreoffice-writer-nogui"]


# -- the LibreOffice profile template (plan 02-16, owner decision 17.11.) -------------------

# What the RUN that makes the template must hold, each with the reason it matters.
TEMPLATE_NEEDS = {
    f"template={soffice.PROFILE_TEMPLATE};": "the path the product copies from",
    '"-env:UserInstallation=file://${template}"': "the profile lands in the template folder",
    "--terminate_after_init": "an init run without a document",
    "--headless": "no display in the build",
    'rm -rf "${scratch}" /tmp/.cache /tmp/.config /tmp/OSL_PIPE_* /tmp/lu*.tmp;': "no build remains in the image",
    f'test -f "${{template}}/user/{soffice.TEMPLATE_MARKER}";': "the build fails when the init did not run",
    # LibreOffice 25.2 desktop/source/app/app.cxx: without user/extensions/buildid
    # cleanExtensionCache() returns true and the start ends in a restart.
    'test -s "${template}/user/extensions/buildid";': "the copy starts without the extension restart",
    'test -z "$(find "${template}" ! -type d ! -type f)";': "only folders and files",
    'chown -R root:root "${template}";': "root-owned",
    'find "${template}" -type d -exec chmod 0555 {} +;': "folders read only",
    'find "${template}" -type f -exec chmod 0444 {} +': "files read only",
}


def template_findings(source: str) -> list[str]:
    """The template RUN: exactly one, in the runtime stage, after the LibreOffice install, before USER."""
    runtime = stage_block(source, "runtime")
    blocks = re.split(r"(?m)^(?=[A-Z]+ )", runtime)
    runs = [" ".join(block.split()) for block in blocks if block.startswith("RUN ")]
    holding = [run for run in runs if "--terminate_after_init" in run]
    if len(holding) != 1:
        return [f"{len(holding)} RUN lines make the profile template"]
    run = holding[0]
    findings = [f"missing: {need} ({why})" for need, why in TEMPLATE_NEEDS.items() if need not in run]
    install = runtime.find("libreoffice-writer-nogui")
    make = runtime.find("--terminate_after_init")
    user = runtime.find("USER 10001")
    if not install < make < user:
        findings.append("the template is not made between the LibreOffice install and USER")
    if soffice.PROFILE_TEMPLATE in stage_block(source, "test"):
        findings.append("the test stage touches the template")
    return findings


def test_the_image_makes_the_soffice_profile_template() -> None:
    assert template_findings(read_dockerfile()) == []


def test_the_template_rule_fires() -> None:
    source = read_dockerfile()
    assert template_findings(source.replace(" --terminate_after_init", "")) == ["0 RUN lines make the profile template"]
    cleanup = 'rm -rf "${scratch}" /tmp/.cache /tmp/.config /tmp/OSL_PIPE_* /tmp/lu*.tmp;'
    assert template_findings(source.replace(" /tmp/OSL_PIPE_* /tmp/lu*.tmp;", ";")) == [
        f"missing: {cleanup} (no build remains in the image)"
    ]
    assert template_findings(source.replace("chmod 0444", "chmod 0644")) == [
        'missing: find "${template}" -type f -exec chmod 0444 {} + (files read only)'
    ]
    late = source.replace("USER 10001:10001\n", "USER 10001:10001\nRUN true --terminate_after_init\n")
    assert "2 RUN lines make the profile template" in template_findings(late)


def smoke_template_findings(workflow: str) -> list[str]:
    """docker.yml checks the pushed image: the template file is there, root-owned and read only."""
    needle = f"stat -c '%U:%a' {soffice.PROFILE_TEMPLATE}/user/{soffice.TEMPLATE_MARKER}"
    findings = [] if needle in workflow else ["the smoke test does not look at the template"]
    if 'test "${template}" = "root:444"' not in workflow:
        findings.append("the smoke test does not gate owner and mode of the template")
    return findings


def test_the_pushed_image_is_checked_for_the_template() -> None:
    workflow = repo_text(REPO_ROOT / ".github" / "workflows" / "docker.yml")
    assert smoke_template_findings(workflow) == []
    assert smoke_template_findings(workflow.replace('= "root:444"', '= "exapp:644"')) == [
        "the smoke test does not gate owner and mode of the template"
    ]


# -- risk R3: a new LibreOffice package gets no tag without the product conversion ----------

# What the smoke step of docker.yml must hold, each with the reason it matters.
GATE_NEEDS = {
    "docker cp ci/soffice_gate.py smoke:/tmp/soffice_gate.py": "the gate runs inside the pushed digest",
    "gate=$(docker exec smoke /app/.venv/bin/python -I /tmp/soffice_gate.py) || gate_status=$?": "its exit is kept",
    'test "${gate_status}" = "0"': "a failed conversion fails the job",
    "dpkg-query -W -f '${Version}' libreoffice-core-nogui": "the package version stands in the log",
}


def smoke_gate_findings(workflow: str) -> list[str]:
    """docker.yml converts a DOCX on the pushed digest, and the tagging merge job needs that job."""
    findings = [f"missing: {needle} ({reason})" for needle, reason in GATE_NEEDS.items() if needle not in workflow]
    merge = workflow.partition("\n  merge:\n")[2]
    if "needs: build" not in merge.split("steps:")[0]:
        findings.append("the merge job does not wait for the build job")
    return findings


def test_the_pushed_image_must_convert_before_it_is_tagged() -> None:
    workflow = repo_text(REPO_ROOT / ".github" / "workflows" / "docker.yml")
    assert smoke_gate_findings(workflow) == []
    assert (REPO_ROOT / "ci" / "soffice_gate.py").is_file()


def test_the_gate_rule_fires() -> None:
    workflow = repo_text(REPO_ROOT / ".github" / "workflows" / "docker.yml")
    assert smoke_gate_findings(workflow.replace('test "${gate_status}" = "0"', "true")) == [
        'missing: test "${gate_status}" = "0" (a failed conversion fails the job)'
    ]
    assert smoke_gate_findings(workflow.replace("    needs: build\n", "")) == [
        "the merge job does not wait for the build job"
    ]
