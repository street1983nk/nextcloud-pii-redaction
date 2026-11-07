"""Structured logging: JSON lines with allowlisted extras only, never a traceback.

A log line leaves the container (docker logs, the AppAPI log view, a support
ticket). The formatter therefore copies only the keys of ``ALLOWED_EXTRA``
(01-SKELETON.md), writes the type of an exception and the place it came from
(``where``), and never its message or a traceback. The canary below stands for
document content that ended up in an exception text.
"""

import io
import json
import logging
import sys
from pathlib import Path

import pytest

from pii_redaction_backend import config, logs

CANARY = "PIIKANARIE7Q4XZ9"
PACKAGE = Path(logs.__file__).resolve().parent
SKELETON_EXTRA = frozenset(
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


def _format(record: logging.LogRecord) -> str:
    return logs.JsonFormatter().format(record)


def _line(record: logging.LogRecord) -> dict[str, object]:
    return json.loads(_format(record))


def _record(message: str = "m", *, exc_info: object = None, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("pii_redaction_backend", logging.INFO, __file__, 1, message, None, None)
    if exc_info is not None:
        record.exc_info = exc_info  # pyright: ignore[reportAttributeAccessIssue]
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_the_allowlist_is_exactly_the_skeleton_set() -> None:
    assert frozenset(logs.ALLOWED_EXTRA) == SKELETON_EXTRA


def test_a_record_becomes_one_json_object_with_its_allowed_extras() -> None:
    line = _line(_record("processed", job_id=3, pages=2, duration_ms=12.5))

    assert line["level"] == "info"
    assert line["logger"] == "pii_redaction_backend"
    assert line["msg"] == "processed"
    assert (line["job_id"], line["pages"], line["duration_ms"]) == (3, 2, 12.5)
    assert str(line["ts"]).endswith("+00:00")


def test_an_extra_outside_the_allowlist_is_dropped() -> None:
    line = _line(_record(job_id=3, file_name="x.pdf", path="/alice/files/x.pdf", user_id="alice"))

    assert line["job_id"] == 3
    assert not {"file_name", "path", "user_id"} & line.keys()


def test_a_non_scalar_extra_is_dropped_and_not_written_as_its_repr() -> None:
    line = _line(_record(reason=[CANARY], job_id=1))

    assert "reason" not in line
    assert CANARY not in _format(_record(reason={"x": CANARY}))


def test_formatting_arguments_never_reach_the_line() -> None:
    record = logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, "file %s", (CANARY,), None)

    text = _format(record)

    assert CANARY not in text
    assert json.loads(text)["msg"] == "file %s"


def _raise_in_package(text: str) -> None:
    # Compiled under a file name inside the package, so the innermost frame of
    # the traceback counts as code of this app.
    code = compile(f"raise ValueError({text!r})\n", str(PACKAGE / "sample_module.py"), "exec")
    exec(code, {})  # noqa: S102 - a fixed literal, the test needs a frame inside the package


def test_an_exception_carries_type_and_place_but_never_its_text_or_a_traceback() -> None:
    try:
        _raise_in_package(CANARY)
    except ValueError:
        record = _record("failed", exc_info=sys.exc_info())

    text = _format(record)
    line = json.loads(text)

    assert line["exc_type"] == "ValueError"
    assert line["where"] == "sample_module:1"
    assert CANARY not in text
    assert "Traceback" not in text
    assert "exc" not in line


def test_where_names_the_innermost_frame_of_this_app() -> None:
    try:
        config.work_dir(0)
    except ValueError:
        record = _record("failed", exc_info=sys.exc_info())

    where = str(_line(record)["where"])

    assert where.startswith("config:")
    assert where.removeprefix("config:").isdigit()


def test_an_exception_without_a_frame_of_this_app_has_no_where() -> None:
    try:
        raise RuntimeError(CANARY)
    except RuntimeError:
        record = _record("failed", exc_info=sys.exc_info())

    text = _format(record)

    assert json.loads(text)["exc_type"] == "RuntimeError"
    assert "where" not in json.loads(text)
    assert CANARY not in text


def test_formatexception_is_never_called(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object) -> str:
        raise AssertionError

    formatter = logs.JsonFormatter()
    monkeypatch.setattr(formatter, "formatException", forbidden)
    try:
        raise ValueError(CANARY)
    except ValueError:
        record = _record("failed", exc_info=sys.exc_info())

    assert CANARY not in formatter.format(record)


@pytest.mark.parametrize(("level", "client_level"), [("info", logging.WARNING), ("debug", logging.NOTSET)])
def test_configure_quiets_the_http_client_outside_debug(level: str, client_level: int) -> None:
    for name in logs.CLIENT_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)

    logs.configure(level)

    assert logging.getLogger("httpx").level == client_level
    assert len(logging.getLogger().handlers) == 1
    assert isinstance(logging.getLogger().handlers[0].formatter, logs.JsonFormatter)


def test_configure_switches_the_access_log_off_and_routes_the_rest_through_the_formatter() -> None:
    logging.getLogger("uvicorn.error").addHandler(logging.StreamHandler(io.StringIO()))

    logs.configure("info")

    assert logging.getLogger("uvicorn.access").disabled is True
    for name in ("uvicorn", "uvicorn.error", "starlette"):
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True


def test_configure_writes_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)

    logs.configure("info")
    logging.getLogger("pii_redaction_backend").info("hello", extra={"job_id": 2})
    logging.getLogger("uvicorn.access").info("GET /jobs/1/output")

    lines = [json.loads(text) for text in buffer.getvalue().strip().splitlines()]
    assert lines[-1]["msg"] == "hello"
    assert lines[-1]["job_id"] == 2
    assert all("/jobs/" not in str(line["msg"]) for line in lines)
