"""Static checks of the Dockerfile and the image scripts.

Images are not built on the development machine (RAM), so the rules a linter
such as hadolint would hold are held here as text, offline, on every run:
multi-stage, every base pinned by digest, a non-root user, a health check, no
ADD of a remote URL, apt lists removed, the app id in the entrypoint.
"""

import re

from pii_redaction_backend import APP_ID
from tests.conftest import BACKEND_ROOT

DOCKERFILE = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")


def from_lines(source: str) -> list[str]:
    return [line.split()[1] for line in source.splitlines() if line.startswith("FROM ")]


def resolved_bases(source: str) -> list[str]:
    """Every FROM and COPY --from image, with ARG defaults substituted."""
    arguments = dict(re.findall(r"^ARG (\w+)=(\S+)$", source, re.MULTILINE))
    stages = set(re.findall(r"^FROM \S+ AS (\w+)", source, re.MULTILINE))
    images = [
        re.sub(r"\$\{(\w+)\}", lambda m: arguments.get(m.group(1), m.group(0)), ref) for ref in from_lines(source)
    ]
    images += [ref for ref in re.findall(r"COPY --from=(\S+)", source) if ref not in stages]
    return images


def unpinned(source: str) -> list[str]:
    return [image for image in resolved_bases(source) if not DIGEST.search(image)]


def test_the_build_is_multi_stage_with_a_runtime_stage_last() -> None:
    stages = re.findall(r"^FROM \S+ AS (\w+)", DOCKERFILE, re.MULTILINE)

    assert len(stages) >= 2
    assert stages[-1] == "runtime"


def test_every_base_image_is_pinned_by_digest() -> None:
    assert resolved_bases(DOCKERFILE)
    assert unpinned(DOCKERFILE) == []


def test_the_runtime_runs_as_a_fixed_non_root_user() -> None:
    runtime = DOCKERFILE.split(" AS runtime", 1)[1]
    users = re.findall(r"^USER (\S+)", runtime, re.MULTILINE)

    assert users == ["10001:10001"]


def test_health_check_entrypoint_and_app_module() -> None:
    assert (
        'HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 CMD ["/healthcheck.sh"]' in DOCKERFILE
    )
    assert f'"-m", "{APP_ID}.main"]' in DOCKERFILE
    assert f"/nc_app_{APP_ID}_data" in DOCKERFILE


def test_no_remote_add_and_apt_lists_are_removed() -> None:
    assert not re.search(r"^ADD\s+https?://", DOCKERFILE, re.MULTILINE)
    for block in re.findall(r"apt-get install[^\n]*(?:\n\s+[^\n]*)*", DOCKERFILE):
        assert "--no-install-recommends" in block
    assert DOCKERFILE.count("apt-get update") == DOCKERFILE.count("rm -rf /var/lib/apt/lists/*")


def test_the_frpc_download_is_checked_against_a_checksum() -> None:
    assert "sha256sum -c -" in DOCKERFILE
    assert len(re.findall(r"FRP_\w+_SHA256=[0-9a-f]{64}", DOCKERFILE)) == 2


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
    assert libreoffice_findings(DOCKERFILE) == []


def test_the_libreoffice_rule_fires() -> None:
    good = "RUN apt-get install -y --no-install-recommends " + " ".join(LIBREOFFICE_PACKAGES) + "\nUSER 10001\n"
    assert libreoffice_findings(good) == []
    assert libreoffice_findings(good.replace("--no-install-recommends ", "")) == ["recommends are installed"]
    assert libreoffice_findings(good.replace(" fonts-crosextra-carlito", "")) == [
        "fonts-crosextra-carlito missing from the install line"
    ]
    assert libreoffice_findings(good + "RUN apt-get install -y default-jre\n") == ["default-jre in the image"]
    assert libreoffice_findings("USER 10001\n") == ["0 RUN lines install libreoffice-writer-nogui"]
