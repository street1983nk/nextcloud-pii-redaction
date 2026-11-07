"""Every log call in backend/src, read as a syntax tree.

A log line leaves the application (docker logs, the AppAPI log view, a support
ticket), so it must never carry document content, a file name or a traceback
with local variables. The rules, on every call ``<x>.<level>(...)`` on an object
named ``LOGGER``, ``logger`` or ``log``:

1. The message is a plain string literal without ``%`` and without ``{``: no
   formatting, no f-string, so nothing variable reaches the message text.
2. ``.exception(`` is forbidden: it writes the traceback, and a traceback can
   carry a value out of a frame.
3. ``extra=`` is a dict literal whose keys come from the allowlist of
   01-SKELETON.md (the same set as ``ALLOWED_EXTRA`` in ``logs.py``).
4. ``print(`` is forbidden anywhere in backend/src.

Each rule has a mutated sample that has to make it fire.
"""

import ast
from pathlib import Path

from tests.conftest import BACKEND_ROOT

SOURCE_ROOT = BACKEND_ROOT / "src"
LOGGER_NAMES = frozenset({"LOGGER", "logger", "log"})
LEVELS = frozenset({"debug", "info", "warning", "error", "critical", "exception", "log"})
ALLOWED_EXTRA = frozenset(
    {
        "job_id",
        "task",
        "stage",
        "status",
        "reason",
        "pages",
        "bytes",
        "duration_ms",
        "attempt",
        "http_status",
        "exc_type",
        "where",
        "child",
        "rss_kb",
        "version",
        "binding",
        "enabled",
        "companion",
        "cancelled_tasks",
    }
)


def _logger_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _message_problem(call: ast.Call, level: str) -> str | None:
    arguments = call.args[1:] if level == "log" else call.args
    if not arguments:
        return "no message"
    message = arguments[0]
    if isinstance(message, ast.JoinedStr):
        return "f-string message"
    if not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
        return "message is not a string literal"
    if "%" in message.value or "{" in message.value:
        return "placeholder in message"
    if len(arguments) > 1:
        return "positional formatting arguments"
    return None


def _extra_problems(call: ast.Call) -> list[str]:
    problems = []
    for keyword in call.keywords:
        if keyword.arg is None:
            problems.append("keyword unpacking")
            continue
        if keyword.arg in {"exc_info", "stack_info"}:
            problems.append(f"{keyword.arg} writes a traceback")
            continue
        if keyword.arg != "extra":
            continue
        if not isinstance(keyword.value, ast.Dict):
            problems.append("extra is not a dict literal")
            continue
        for key in keyword.value.keys:
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                problems.append("extra key is not a string literal")
            elif key.value not in ALLOWED_EXTRA:
                problems.append(f"extra key {key.value} is not allowed")
    return problems


def findings(source: str, name: str = "<sample>") -> list[str]:
    """Every rule violation in one source text."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            found.append(f"{name}:{node.lineno} print")
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in LEVELS:
            continue
        if _logger_name(node.func.value) not in LOGGER_NAMES:
            continue
        level = node.func.attr
        if level == "exception":
            found.append(f"{name}:{node.lineno} exception")
            continue
        problem = _message_problem(node, level)
        if problem:
            found.append(f"{name}:{node.lineno} {problem}")
        found += [f"{name}:{node.lineno} {problem}" for problem in _extra_problems(node)]
    return found


def log_call_count(source: str) -> int:
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LEVELS
        and _logger_name(node.func.value) in LOGGER_NAMES
    )


def _sources() -> dict[str, str]:
    return {
        path.relative_to(BACKEND_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
    }


def test_every_log_call_in_backend_src_follows_the_rules() -> None:
    sources = _sources()
    assert sum(log_call_count(text) for text in sources.values()) >= 3, "the scanner sees no log call at all"
    assert [finding for name, text in sources.items() for finding in findings(text, name)] == []


def test_the_allowlist_matches_logs_py_once_it_carries_one() -> None:
    logs = (SOURCE_ROOT / "pii_redaction_backend" / "logs.py").read_text(encoding="utf-8")
    if "ALLOWED_EXTRA" not in logs:
        return
    from pii_redaction_backend import logs as module

    assert frozenset(getattr(module, "ALLOWED_EXTRA")) == ALLOWED_EXTRA  # noqa: B009


def test_self_a_clean_call_passes() -> None:
    assert findings('LOGGER.info("started", extra={"job_id": 1, "stage": "fetching"})') == []
    assert findings('logger.log(20, "plain")') == []
    assert findings('other.info("%s", x)') == [], "only logger objects are judged"


def test_self_a_placeholder_or_an_f_string_fires() -> None:
    assert findings('LOGGER.info("app %s", name)') == ["<sample>:1 placeholder in message"]
    assert findings('LOGGER.info(f"file {name}")') == ["<sample>:1 f-string message"]
    assert findings('LOGGER.info("a {x}")') == ["<sample>:1 placeholder in message"]
    assert findings("LOGGER.info(message)") == ["<sample>:1 message is not a string literal"]


def test_self_exception_and_tracebacks_fire() -> None:
    assert findings('LOGGER.exception("failed")') == ["<sample>:1 exception"]
    assert findings('log.error("failed", exc_info=True)') == ["<sample>:1 exc_info writes a traceback"]


def test_self_an_extra_outside_the_allowlist_fires() -> None:
    assert findings('LOGGER.warning("x", extra={"path": p})') == ["<sample>:1 extra key path is not allowed"]
    assert findings('LOGGER.warning("x", extra=values)') == ["<sample>:1 extra is not a dict literal"]
    assert findings('LOGGER.warning("x", **kw)') == ["<sample>:1 keyword unpacking"]


def test_self_print_fires() -> None:
    assert findings("print(secret)") == ["<sample>:1 print"]


def test_self_the_scanner_counts_calls() -> None:
    assert log_call_count('LOGGER.info("a")\nlogger.debug("b")\nx.info("c")') == 2


def test_the_source_tree_exists() -> None:
    assert Path(SOURCE_ROOT / "pii_redaction_backend" / "main.py").is_file()
