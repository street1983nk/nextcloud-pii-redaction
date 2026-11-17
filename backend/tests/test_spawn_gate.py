"""No process starts outside workers/child.py, no exec outside sandbox/jail.py, never waitpid(-1).

Read as a syntax tree over backend/src. A module that started a process on
its own would skip the jail (rlimits, Landlock, seccomp) and the reaper, so
the rule holds for every name a process can be started with. Each rule has a
probe source that has to make it fire.
"""

import ast
from pathlib import Path

import pytest

from tests.conftest import BACKEND_ROOT

SOURCE_ROOT = BACKEND_ROOT / "src"
PACKAGE = SOURCE_ROOT / "pii_redaction_backend"
SPAWN_HOME = PACKAGE / "workers" / "child.py"
EXEC_HOME = PACKAGE / "sandbox" / "jail.py"

SPAWN_ASYNCIO = frozenset({"create_subprocess_exec", "create_subprocess_shell"})
SPAWN_OS = frozenset({"system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp"})
SPAWN_PTY = frozenset({"fork", "spawn"})


def _dotted(node: ast.expr) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return parts[::-1]


def _imported_names(tree: ast.Module) -> dict[str, str]:
    """Local name -> module.attr for every 'from m import a [as b]'."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def _qualified(node: ast.expr, imported: dict[str, str]) -> str:
    parts = _dotted(node)
    if not parts:
        return ""
    head = imported.get(parts[0], parts[0])
    return ".".join([head, *parts[1:]])


def _is_spawn(name: str) -> bool:
    module, _, attr = name.rpartition(".")
    if module == "subprocess" or module.startswith("subprocess.") or name.startswith("subprocess."):
        return True
    if module in {"asyncio", "asyncio.subprocess"} and attr in SPAWN_ASYNCIO:
        return True
    if module == "os" and (attr in SPAWN_OS or attr.startswith("spawn")):
        return True
    if module == "multiprocessing" or name.startswith("multiprocessing."):
        return True
    return module == "pty" and attr in SPAWN_PTY


def _is_exec(name: str) -> bool:
    module, _, attr = name.rpartition(".")
    return module == "os" and attr.startswith("exec")


def _waits_for_any(call: ast.Call, name: str) -> bool:
    if not name.endswith("waitpid") or not call.args:
        return False
    first = call.args[0]
    return (
        isinstance(first, ast.UnaryOp)
        and isinstance(first.op, ast.USub)
        and isinstance(first.operand, ast.Constant)
        and first.operand.value == 1
    ) or (isinstance(first, ast.Constant) and first.value == -1)


def problems(source: str, path: Path) -> list[str]:
    """Every rule the source breaks, for a module at path."""
    tree = ast.parse(source)
    imported = _imported_names(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [
                f"imports {alias.name}" for alias in node.names if alias.name == "subprocess" and path != SPAWN_HOME
            ]
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess" and path != SPAWN_HOME:
            found.append("imports from subprocess")
        # A reference counts like a call: os.execv handed on as a value
        # (execv=os.execv) or bound to a new name starts a process all the same.
        if isinstance(node, ast.Attribute | ast.Name) and not isinstance(getattr(node, "ctx", None), ast.Store):
            name = _qualified(node, imported)
            if _is_spawn(name) and path != SPAWN_HOME:
                found.append(f"starts a process: {name}")
            if _is_exec(name) and path != EXEC_HOME:
                found.append(f"execs: {name}")
        if isinstance(node, ast.Call) and _waits_for_any(node, _qualified(node.func, imported)):
            found.append("waits for any child")
    return found


def _sources() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def test_the_gate_reads_the_whole_package() -> None:
    files = _sources()
    assert SPAWN_HOME in files
    assert EXEC_HOME in files
    assert len(files) > 20


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(SOURCE_ROOT)))
def test_no_module_starts_execs_or_waits_outside_its_home(path: Path) -> None:
    assert problems(path.read_text(encoding="utf-8"), path) == []


def test_positive_control_the_homes_really_do_it() -> None:
    # The same files moved elsewhere break the rule: the gate sees their calls.
    child_source = SPAWN_HOME.read_text(encoding="utf-8")
    jail_source = EXEC_HOME.read_text(encoding="utf-8")
    assert any("starts a process" in problem for problem in problems(child_source, PACKAGE / "elsewhere.py"))
    assert any("execs" in problem for problem in problems(jail_source, PACKAGE / "elsewhere.py"))


ELSEWHERE = PACKAGE / "runner" / "probe_module.py"


@pytest.mark.parametrize(
    "probe",
    [
        "import asyncio\nasyncio.create_subprocess_exec('/bin/true')\n",
        "import asyncio\nasyncio.create_subprocess_shell('true')\n",
        "from asyncio import create_subprocess_exec as go\ngo('/bin/true')\n",
        "import subprocess\nsubprocess.run(['/bin/true'])\n",
        "from subprocess import Popen\nPopen(['/bin/true'])\n",
        "import os\nos.system('true')\n",
        "import os\nos.popen('true')\n",
        "import os\nos.fork()\n",
        "import os\nos.spawnv(0, '/bin/true', [])\n",
        "import os\nos.posix_spawn('/bin/true', [], {})\n",
        "import os\nos.execv('/bin/true', [])\n",
        "import os\nos.execve('/bin/true', [], {})\n",
        "from os import execvp\nexecvp('true', [])\n",
        "import os\nos.waitpid(-1, 0)\n",
        "import os\nos.waitpid(-1, os.WNOHANG)\n",
        "import multiprocessing\nmultiprocessing.Process(target=print).start()\n",
        "import pty\npty.spawn('/bin/sh')\n",
    ],
)
def test_each_rule_fires_on_its_probe(probe: str) -> None:
    assert problems(probe, ELSEWHERE) != []


def test_exec_is_allowed_only_in_the_jail() -> None:
    probe = "import os\nos.execv('/bin/true', ['/bin/true'])\n"
    assert problems(probe, EXEC_HOME) == []
    assert problems(probe, SPAWN_HOME) != []


def test_waitpid_of_one_group_is_allowed_everywhere() -> None:
    assert problems("import os\nos.waitpid(-pgid, os.WNOHANG)\n", ELSEWHERE) == []
