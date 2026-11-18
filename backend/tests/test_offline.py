"""Hidden network calls of the libraries: offline switches, a tripwire, and a gate on their network APIs.

Audit hooks cannot be removed, so every check that installs the tripwire runs
in a child process (sys.executable -I with a script file in tmp_path).
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pii_redaction_backend import offline
from tests.conftest import REPO_ROOT

CHILD_TIMEOUT_S = 180


def _run(tmp_path: Path, body: str, env_extra: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    """Run body in a child; it writes its findings as JSON to OUT."""
    out = tmp_path / "out.json"
    script = tmp_path / "child_script.py"
    script.write_text(f"OUT = {str(out)!r}\n" + body, encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith(("TLDEXTRACT", "HF_", "TRANSFORMERS"))}
    env.update(env_extra or {})
    result = subprocess.run(  # noqa: S603 - fixed interpreter and a script written by this test
        [sys.executable, "-I", str(script)], env=env, check=False, timeout=CHILD_TIMEOUT_S
    )
    found = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    return result.returncode, found


RECORDER = """
import json, sys
SEEN = []
def _record(event, _args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto", "urllib.Request"}:
        SEEN.append(event)
sys.addaudithook(_record)
"""

EMAIL = """
from pii_redaction_backend import offline
{configure}
offline.install_network_tripwire()
from presidio_analyzer.predefined_recognizers import EmailRecognizer
hits = EmailRecognizer().analyze("Kontakt: max@example.org", ["EMAIL_ADDRESS"])
json.dump({{"hits": len(hits), "seen": SEEN}}, open(OUT, "w"))
"""


# -- configure -------------------------------------------------------------------------


def test_configure_sets_the_offline_variables_hard(monkeypatch: pytest.MonkeyPatch) -> None:
    import tldextract.tldextract as extractor_module

    for key in offline.OFFLINE_ENV:
        monkeypatch.setenv(key, "something else")
    monkeypatch.setattr(extractor_module, "TLD_EXTRACTOR", extractor_module.TLD_EXTRACTOR)

    offline.configure()
    first = extractor_module.TLD_EXTRACTOR
    offline.configure()

    for key, value in offline.OFFLINE_ENV.items():
        assert os.environ[key] == value
    assert offline.OFFLINE_ENV["TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS"] == ""
    assert extractor_module.TLD_EXTRACTOR.suffix_list_urls == ()
    assert extractor_module.TLD_EXTRACTOR._cache.enabled is False
    assert first.suffix_list_urls == ()


def test_the_offline_variables_are_the_four_of_the_research() -> None:
    assert set(offline.OFFLINE_ENV) == {
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HF_HUB_DISABLE_TELEMETRY",
        "TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS",
    }


# -- the tripwire, in children -----------------------------------------------------------


def test_the_tripwire_stops_a_name_lookup(tmp_path: Path) -> None:
    body = """
import json, socket
from pii_redaction_backend import offline
offline.install_network_tripwire()
try:
    socket.getaddrinfo("example.org", 80)
    result = "resolved"
except PermissionError:
    result = "blocked"
json.dump({"result": result}, open(OUT, "w"))
"""
    code, found = _run(tmp_path, body)
    assert code == 0
    assert found == {"result": "blocked"}


def test_the_tripwire_stops_a_connect_to_localhost(tmp_path: Path) -> None:
    body = """
import json, socket
from pii_redaction_backend import offline
server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1)
offline.install_network_tripwire()
try:
    socket.socket().connect(server.getsockname())
    result = "connected"
except PermissionError:
    result = "blocked"
json.dump({"result": result}, open(OUT, "w"))
"""
    code, found = _run(tmp_path, body)
    assert code == 0
    assert found == {"result": "blocked"}


def test_presidio_finds_an_email_without_any_network_step(tmp_path: Path) -> None:
    empty_cache = tmp_path / "cache"
    empty_cache.mkdir()
    code, found = _run(
        tmp_path,
        RECORDER + EMAIL.format(configure="offline.configure()"),
        {"TLDEXTRACT_CACHE": str(empty_cache)},
    )
    assert code == 0
    assert found == {"hits": 1, "seen": []}


def test_positive_control_without_configure_tldextract_reaches_for_the_net(tmp_path: Path) -> None:
    empty_cache = tmp_path / "cache"
    empty_cache.mkdir()
    _, found = _run(
        tmp_path,
        RECORDER + EMAIL.format(configure=""),
        {"TLDEXTRACT_CACHE": str(empty_cache)},
    )
    # The tripwire stopped it (tldextract falls back to its snapshot), but the
    # attempt is on record: the test above can see a leak.
    assert found.get("seen"), "without configure tldextract made no network attempt"


# -- the gate on the network APIs of the libraries ---------------------------------------
#
# CLAUDE.md "What NOT to Use": no GLiNER2 cloud client, no Hugging Face download
# helpers, no spaCy model download, and from_pretrained only with an absolute
# local path. gliner2 imports its cloud client on its own, so the gate forbids
# the use, not the package.

# tests/probes: the probes load the models in the container (plan 02-22, offline_stack.py).
GATED_ROOTS = (
    REPO_ROOT / "backend" / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "ci",
    REPO_ROOT / "backend" / "tests" / "probes",
)
FORBIDDEN_NAMES = frozenset({"GLiNER2API", "hf_hub_download", "snapshot_download"})


def _dotted(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def network_api_findings(source: str) -> list[str]:
    """Every use of a library network API in source."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            names = {alias.name for alias in node.names}
            if module.startswith("gliner2") and ("API" in names or module.startswith("gliner2.api_client")):
                found.append(f"imports the gliner2 cloud client from {module}")
            if module.startswith("gliner2") and "api_client" in names:
                found.append("imports gliner2.api_client")
            if module == "spacy.cli" and "download" in names:
                found.append("imports spacy.cli.download")
            found += [f"imports {name}" for name in sorted(names & FORBIDDEN_NAMES)]
        if isinstance(node, ast.Import):
            found += [f"imports {a.name}" for a in node.names if a.name.startswith("gliner2.api_client")]
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append(f"names {node.id}")
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if node.attr in FORBIDDEN_NAMES:
                found.append(f"names {dotted}")
            if dotted.endswith("cli.download") and dotted.split(".")[0] == "spacy":
                found.append("calls spacy.cli.download")
            if dotted.startswith("gliner2.api_client") or dotted == "gliner2.API":
                found.append(f"names {dotted}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "from_pretrained":
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and not first.value.startswith("/"):
                found.append(f"from_pretrained with a repository id {first.value!r}")
    return found


def _gated_files() -> list[Path]:
    return sorted(path for root in GATED_ROOTS if root.is_dir() for path in root.rglob("*.py"))


def test_the_gate_reads_the_source_scripts_and_ci() -> None:
    files = _gated_files()
    assert any(path.name == "offline.py" for path in files)
    assert any(path.parent.name == "ci" for path in files)
    assert any(path.name == "offline_stack.py" and path.parent.name == "probes" for path in files)


@pytest.mark.parametrize("path", _gated_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_source_uses_a_library_network_api(path: Path) -> None:
    assert network_api_findings(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "probe",
    [
        "from gliner2 import GLiNER2API\n",
        "import gliner2\nclient = gliner2.GLiNER2API(api_key='x')\n",
        "from gliner2 import API\n",
        "from gliner2.api_client import GLiNER2API\n",
        "import gliner2.api_client\n",
        "from gliner2 import api_client\n",
        "from huggingface_hub import hf_hub_download\n",
        "import huggingface_hub\nhuggingface_hub.snapshot_download('fastino/x')\n",
        "from spacy.cli import download\n",
        "import spacy\nspacy.cli.download('de_core_news_lg')\n",
        "from transformers import AutoModel\nAutoModel.from_pretrained('microsoft/mdeberta-v3-base')\n",
        "GLiNER2.from_pretrained('fastino/gliner2-privacy-filter-PII-multi')\n",
    ],
)
def test_each_rule_fires_on_its_probe(probe: str) -> None:
    assert network_api_findings(probe) != []


def test_from_pretrained_with_an_absolute_path_is_allowed() -> None:
    assert network_api_findings("GLiNER2.from_pretrained('/models/gliner2/0280f6f3')\n") == []
