"""Every module that imports torch hands it the thread count of the parent (plan 02-16).

The detection child gets OMP_NUM_THREADS=n from the parent (workers/child.py
child_env) and no OMP_THREAD_LIMIT. torch must plan with the same n, so the
module that imports it calls hardware.apply_worker_threads(torch) right after
the import. Without that call torch planned with every core while OpenMP got
one thread, and detect never finished on arm64 (sandbox run 44221141543,
deferred-items 02-16). The real detection child comes in phase 8; this guard
makes the call impossible to forget there.

The rule, read as a syntax tree, never importing torch: a module that imports
torch, gliner2 or transformers (both pull torch in) by ``import``, ``from``,
``importlib.import_module("...")`` or ``__import__("...")`` must call
``apply_worker_threads`` somewhere in the same module. It applies to every
file under backend/src/pii_redaction_backend except hardware.py, which defines
the helper, and to tests/profile_work.py, the detect worker stand-in of the
container gate until phase 8.
"""

import ast

from tests.conftest import BACKEND_ROOT

PACKAGE_ROOT = BACKEND_ROOT / "src" / "pii_redaction_backend"
HELPER = PACKAGE_ROOT / "resources" / "hardware.py"
STAND_IN = BACKEND_ROOT / "tests" / "profile_work.py"
TORCH_ROOTS = frozenset({"torch", "gliner2", "transformers"})
DYNAMIC_IMPORTS = frozenset({"import_module", "__import__"})
CALL = "apply_worker_threads"


def _is_torch(module: str | None) -> bool:
    return module is not None and module.split(".", 1)[0] in TORCH_ROOTS


def _callee(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _dynamic_torch(node: ast.Call) -> bool:
    if _callee(node) not in DYNAMIC_IMPORTS or not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Constant) and isinstance(first.value, str) and _is_torch(first.value)


def _imports_torch(node: ast.Import | ast.ImportFrom | ast.Call) -> bool:
    if isinstance(node, ast.Import):
        return any(_is_torch(alias.name) for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.level == 0 and _is_torch(node.module)
    return _dynamic_torch(node)


def torch_imports(source: str) -> list[int]:
    """The line of every torch import in one source text."""
    nodes = [node for node in ast.walk(ast.parse(source)) if isinstance(node, (ast.Import, ast.ImportFrom, ast.Call))]
    return sorted(node.lineno for node in nodes if _imports_torch(node))


def calls_apply(source: str) -> bool:
    return any(isinstance(node, ast.Call) and _callee(node) == CALL for node in ast.walk(ast.parse(source)))


def findings(source: str, name: str = "<sample>") -> list[str]:
    """One finding per module that imports torch without calling apply_worker_threads."""
    lines = torch_imports(source)
    if lines and not calls_apply(source):
        return [f"{name}:{lines[0]} imports torch without {CALL}"]
    return []


def _guarded() -> dict[str, str]:
    paths = [path for path in sorted(PACKAGE_ROOT.rglob("*.py")) if path != HELPER]
    return {path.relative_to(BACKEND_ROOT).as_posix(): path.read_text(encoding="utf-8") for path in [*paths, STAND_IN]}


def test_every_torch_module_applies_the_worker_threads() -> None:
    sources = _guarded()
    assert len(sources) > 10, "the scanner sees no source tree"
    assert torch_imports(sources["tests/profile_work.py"]), "the scanner misses the torch import of the stand-in"
    assert [finding for name, text in sources.items() for finding in findings(text, name)] == []


def test_the_helper_exists_and_imports_no_torch() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert f"def {CALL}(" in text
    assert torch_imports(text) == []


def test_self_torch_without_the_call_fires() -> None:
    assert findings("import torch\n") == ["<sample>:1 imports torch without apply_worker_threads"]
    assert findings("x = 1\nfrom torch.nn import functional\n") == [
        "<sample>:2 imports torch without apply_worker_threads"
    ]
    assert findings("def load():\n    import torch.nn as nn\n") == [
        "<sample>:2 imports torch without apply_worker_threads"
    ]


def test_self_gliner2_and_transformers_without_the_call_fire() -> None:
    assert findings("from gliner2 import GLiNER2\n") == ["<sample>:1 imports torch without apply_worker_threads"]
    assert findings("import transformers\n") == ["<sample>:1 imports torch without apply_worker_threads"]


def test_self_a_dynamic_import_without_the_call_fires() -> None:
    assert findings('import importlib\ntorch = importlib.import_module("torch")\n') == [
        "<sample>:2 imports torch without apply_worker_threads"
    ]
    assert findings('torch = __import__("torch")\n') == ["<sample>:1 imports torch without apply_worker_threads"]


def test_self_the_call_clears_it() -> None:
    source = "import torch\nfrom pii_redaction_backend.resources import hardware\nhardware.apply_worker_threads(torch)"
    assert findings(source) == []
    assert findings("import torch\nfrom x import apply_worker_threads\napply_worker_threads(torch)\n") == []


def test_self_no_torch_is_fine() -> None:
    assert findings("import os\nimport torchvision_free\nfrom . import torch\n") == []
    assert findings('import importlib\nimportlib.import_module("spacy")\n') == []
