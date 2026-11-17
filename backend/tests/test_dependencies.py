"""Static checks of the runtime pins, the torch index and the pytest markers (plan 02-02).

- Every runtime dependency is pinned with "==", no ranges.
- The detection stack and the two document libraries stand at exactly the
  versions the owner cleared on 17.11.2026 (package gate). transformers is 5.22.1
  and not the spike's 4.57.6: 4.57.6 carries six advisories.
- gliner2 never comes with its [local] extra (that one pulls peft).
- torch comes only from the PyTorch CPU index, declared explicit, and the lock
  file names that index for every torch entry: PyPI's torch pulls CUDA.
- The container and linux markers are registered, and python.yml leaves the
  container tests out (they run in the test stage of the image).
- The lock holds the owner's two-week rule: a fixed exclude-newer cut-off in
  [tool.uv], recorded in uv.lock, and no locked file uploaded after it.

Every rule is a *_findings function with a self test on a falsified probe, the
pattern of tests/test_dockerfile.py.
"""

import re
import tomllib

from tests.conftest import BACKEND_ROOT, REPO_ROOT

PYPROJECT_TEXT = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads(PYPROJECT_TEXT)
LOCK = (BACKEND_ROOT / "uv.lock").read_text(encoding="utf-8")
PYTHON_YML = (REPO_ROOT / ".github" / "workflows" / "python.yml").read_text(encoding="utf-8")

CPU_INDEX = "https://download.pytorch.org/whl/cpu"

STACK = {
    "presidio-analyzer": "2.2.366",
    "spacy": "3.8.18",
    "gliner2": "2.1.0",
    "torch": "2.15.0",
    "transformers": "5.22.1",
    "huggingface-hub": "2.4.0",
    "tokenizers": "0.23.3",
    "safetensors": "0.8.0",
    "numpy": "2.4.6",
    "pikepdf": "10.17.0",
    "lxml": "6.1.3",
}

REQUIRED_MARKERS = ("container", "linux")


def dependencies(pyproject: dict) -> list[str]:
    return list(pyproject["project"]["dependencies"])


def range_findings(deps: list[str]) -> list[str]:
    """Every runtime dependency is name[extras]==version and nothing else."""
    return [dep for dep in deps if not re.fullmatch(r"[A-Za-z0-9_.-]+(\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+]+", dep)]


def stack_findings(deps: list[str]) -> list[str]:
    """Each stack package stands exactly once, with exactly the cleared version."""
    pins: dict[str, list[str]] = {}
    for dep in deps:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==(\S+)", dep)
        if match:
            pins.setdefault(match.group(1).lower(), []).append(match.group(2))
    findings = []
    for name, version in STACK.items():
        found = pins.get(name, [])
        if found != [version]:
            findings.append(f"{name}: expected =={version}, found {found}")
    return findings


def local_extra_findings(deps: list[str]) -> list[str]:
    """gliner2 without any extra that pulls the training stack."""
    return [dep for dep in deps if re.match(r"gliner2\s*\[", dep)]


def torch_index_findings(pyproject: dict, lock: str) -> list[str]:
    """torch from the explicit CPU index only, in pyproject and in every lock entry."""
    findings = []
    uv = pyproject.get("tool", {}).get("uv", {})
    source = uv.get("sources", {}).get("torch", {})
    index_name = source.get("index") if isinstance(source, dict) else None
    indexes = [index for index in uv.get("index", []) if index.get("name") == index_name]
    if index_name is None or len(indexes) != 1:
        findings.append("torch has no index source")
    else:
        if indexes[0].get("url") != CPU_INDEX:
            findings.append(f"torch index url is {indexes[0].get('url')}")
        if indexes[0].get("explicit") is not True:
            findings.append("torch index is not explicit")
    blocks = [block for block in lock.split("[[package]]") if re.search(r'^name = "torch"$', block, re.MULTILINE)]
    if not blocks:
        findings.append("torch missing in uv.lock")
    for block in blocks:
        match = re.search(r'^source = \{ registry = "([^"]+)" \}$', block, re.MULTILINE)
        if match is None or match.group(1) != CPU_INDEX:
            findings.append(f"uv.lock torch source is {match.group(1) if match else None}")
    return findings


def marker_findings(pyproject: dict) -> list[str]:
    markers = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    names = {marker.split(":", 1)[0].strip() for marker in markers}
    return [f"marker {name} not registered" for name in REQUIRED_MARKERS if name not in names]


def container_filter_findings(workflow: str) -> list[str]:
    """The pytest step of python.yml deselects the container tests."""
    runs = [line for line in workflow.splitlines() if re.search(r"run: uv run pytest\b", line)]
    if len(runs) != 1:
        return [f"expected one pytest step, found {len(runs)}"]
    return [] if '-m "not container"' in runs[0] else ["pytest step keeps the container tests"]


def test_runtime_pins_are_exact() -> None:
    assert range_findings(dependencies(PYPROJECT)) == []


def test_the_range_rule_fires() -> None:
    assert range_findings(["lxml>=6.1.3", "torch==2.15.0", "spacy~=3.8"]) == ["lxml>=6.1.3", "spacy~=3.8"]


def test_detection_stack_is_pinned() -> None:
    assert stack_findings(dependencies(PYPROJECT)) == []


def test_the_stack_rule_fires() -> None:
    deps = [dep.replace("transformers==5.22.1", "transformers==4.57.6") for dep in dependencies(PYPROJECT)]
    deps = [dep for dep in deps if not dep.startswith("pikepdf")]
    assert stack_findings(deps) == [
        "transformers: expected ==5.22.1, found ['4.57.6']",
        "pikepdf: expected ==10.17.0, found []",
    ]


def test_gliner2_has_no_local_extra() -> None:
    assert local_extra_findings(dependencies(PYPROJECT)) == []
    assert "gliner2[" not in PYPROJECT_TEXT


def test_the_local_extra_rule_fires() -> None:
    assert local_extra_findings(["gliner2[local]==2.1.0"]) == ["gliner2[local]==2.1.0"]


def test_torch_comes_from_the_cpu_index() -> None:
    assert torch_index_findings(PYPROJECT, LOCK) == []


def test_the_torch_index_rule_fires() -> None:
    probe = tomllib.loads(PYPROJECT_TEXT.replace("explicit = true", "explicit = false"))
    assert torch_index_findings(probe, LOCK) == ["torch index is not explicit"]
    pypi_lock = LOCK.replace(
        f'source = {{ registry = "{CPU_INDEX}" }}', 'source = { registry = "https://pypi.org/simple" }'
    )
    assert "uv.lock torch source is https://pypi.org/simple" in torch_index_findings(PYPROJECT, pypi_lock)
    no_source = tomllib.loads(PYPROJECT_TEXT.replace('torch = { index = "pytorch-cpu" }', ""))
    assert torch_index_findings(no_source, LOCK) == ["torch has no index source"]


def test_container_and_linux_markers_are_registered() -> None:
    assert marker_findings(PYPROJECT) == []
    assert container_filter_findings(PYTHON_YML) == []


def test_the_marker_rules_fire() -> None:
    probe = tomllib.loads(re.sub(r'\s+"linux: [^"]*",', "", PYPROJECT_TEXT))
    assert marker_findings(probe) == ["marker linux not registered"]
    assert container_filter_findings(PYTHON_YML.replace(' -m "not container"', "")) == [
        "pytest step keeps the container tests"
    ]


def exclude_newer_findings(pyproject: dict, lock: str) -> list[str]:
    """Owner rule 17.11.2026: a fixed exclude-newer cut-off, recorded in the lock, held by every file.

    No per-package exception (exclude-newer-package), so torch from the CPU index
    falls under the same cut-off; that index reports upload-time for its wheels.
    """
    uv = pyproject.get("tool", {}).get("uv", {})
    cutoff = uv.get("exclude-newer")
    if not isinstance(cutoff, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cutoff):
        return [f"exclude-newer is not a fixed UTC timestamp: {cutoff!r}"]
    findings = []
    if "exclude-newer-package" in uv:
        findings.append("exclude-newer-package exempts packages from the cut-off")
    if f'exclude-newer = "{cutoff}"' not in lock.split("[[package]]", 1)[0]:
        findings.append("uv.lock was not resolved with this exclude-newer")
    # Same format on both sides, so string order is time order up to the seconds.
    findings += [
        f"file uploaded {stamp}, after the cut-off"
        for stamp in re.findall(r'upload-time = "([^"]+)"', lock)
        if stamp[:19] >= cutoff[:19]
    ]
    return findings


def test_the_lock_holds_the_two_week_rule() -> None:
    assert exclude_newer_findings(PYPROJECT, LOCK) == []


def test_the_exclude_newer_rule_fires() -> None:
    cutoff = PYPROJECT["tool"]["uv"]["exclude-newer"]
    no_cutoff = tomllib.loads(PYPROJECT_TEXT.replace(f'exclude-newer = "{cutoff}"', ""))
    assert exclude_newer_findings(no_cutoff, LOCK) == ["exclude-newer is not a fixed UTC timestamp: None"]
    relative = tomllib.loads(PYPROJECT_TEXT.replace(f'exclude-newer = "{cutoff}"', 'exclude-newer = "2 weeks"'))
    assert exclude_newer_findings(relative, LOCK) == ["exclude-newer is not a fixed UTC timestamp: '2 weeks'"]
    young = LOCK.replace('upload-time = "2026-10-28T13:19:05Z"', 'upload-time = "2026-11-16T10:12:19.491Z"', 1)
    assert young != LOCK
    assert exclude_newer_findings(PYPROJECT, young) == ["file uploaded 2026-11-16T10:12:19.491Z, after the cut-off"]
    stale = LOCK.replace(f'exclude-newer = "{cutoff}"', "", 1)
    assert exclude_newer_findings(PYPROJECT, stale) == ["uv.lock was not resolved with this exclude-newer"]
    exempt = tomllib.loads(
        PYPROJECT_TEXT.replace(
            f'exclude-newer = "{cutoff}"', f'exclude-newer = "{cutoff}"\nexclude-newer-package = {{ torch = false }}'
        )
    )
    assert exclude_newer_findings(exempt, LOCK) == ["exclude-newer-package exempts packages from the cut-off"]


SECURITY_YML = (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")


def audit_order_findings(workflow: str) -> list[str]:
    """security.yml drops the +cpu tag between the export and the audit, or --strict stops on torch."""
    steps = [
        workflow.find("uv export"),
        workflow.find(r"torch==\1 "),
        workflow.find("pip-audit --strict"),
    ]
    if -1 in steps:
        return ["export, +cpu strip or strict audit missing"]
    return [] if steps == sorted(steps) else ["the +cpu strip does not sit between export and audit"]


def test_the_audit_sees_torch_under_its_upstream_version() -> None:
    assert audit_order_findings(SECURITY_YML) == []
    # The sed expression of the workflow, applied to the line uv export writes.
    line = "torch==2.15.0+cpu ; sys_platform != 'darwin' \\"
    assert re.sub(r"^torch==([0-9.]+)\+cpu ", r"torch==\1 ", line) == "torch==2.15.0 ; sys_platform != 'darwin' \\"


def test_the_audit_order_rule_fires() -> None:
    assert audit_order_findings(SECURITY_YML.replace(r"torch==\1 ", "")) == [
        "export, +cpu strip or strict audit missing"
    ]
