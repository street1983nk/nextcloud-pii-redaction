"""Structured logging: one JSON object per line on stdout, allowlisted fields only.

Docker and the AppAPI log view keep stdout, and a JSON line can be filtered by
level or logger without a regular expression. A log line leaves the container,
so it must never carry document content, a file name, a path or a secret:

- Only the keys of ``ALLOWED_EXTRA`` (01-SKELETON.md, the same set as in
  tests/test_log_calls.py) are copied out of ``extra=``, and only scalar values.
- The message is written as the literal the caller passed; formatting
  arguments are never merged in (the AST gate forbids them in this package,
  and a third party logger could carry a value through them).
- An exception becomes its type and ``where`` (``module:line`` of the innermost
  frame inside this package). Its text and the traceback are never written:
  an exception message can quote content, a traceback can show local values.
- The access log of uvicorn is switched off; it would write every request path.
- The HTTP client loggers (httpx, httpcore, niquests, urllib3) log every request
  line on INFO, and an OCS path carries a job id and a claim token. Outside
  debug they stand on WARNING.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final

CLIENT_LOGGERS: Final = ("httpx", "httpcore", "niquests", "urllib3")

ALLOWED_EXTRA: Final[frozenset[str]] = frozenset(
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

# The loggers that are routed through the root handler instead of their own.
ROUTED_LOGGERS: Final = ("uvicorn", "uvicorn.error", "starlette")
ACCESS_LOGGER: Final = "uvicorn.access"

_PACKAGE_DIR: Final = Path(__file__).resolve().parent


def _where(traceback: TracebackType | None) -> str | None:
    """``module:line`` of the innermost frame inside this package, or None."""
    found: str | None = None
    while traceback is not None:
        code = traceback.tb_frame.f_code
        try:
            relative = Path(code.co_filename).resolve().relative_to(_PACKAGE_DIR)
        except (ValueError, OSError):
            relative = None
        if relative is not None and relative.suffix == ".py":
            found = f"{'.'.join(relative.with_suffix('').parts)}:{traceback.tb_lineno}"
        traceback = traceback.tb_next
    return found


class JsonFormatter(logging.Formatter):
    """Format a record as one compact JSON object of allowlisted fields."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            # The literal, never record.getMessage(): arguments stay out.
            "msg": record.msg if isinstance(record.msg, str) else type(record.msg).__name__,
        }
        for key in sorted(ALLOWED_EXTRA):
            value = record.__dict__.get(key)
            if isinstance(value, str | int | float | bool):
                line[key] = value
        if record.exc_info:
            exc_class, _, traceback = record.exc_info
            line["exc_type"] = exc_class.__name__ if exc_class is not None else None
            where = _where(traceback)
            if where is not None:
                line["where"] = where
        return json.dumps(line, ensure_ascii=False)


def configure(level: str) -> None:
    """Route the root logger through the JSON formatter, idempotent per process."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ROUTED_LOGGERS:
        routed = logging.getLogger(name)
        routed.handlers[:] = []
        routed.propagate = True
    access = logging.getLogger(ACCESS_LOGGER)
    access.handlers[:] = []
    access.disabled = True
    if level != "debug":
        for name in CLIENT_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
