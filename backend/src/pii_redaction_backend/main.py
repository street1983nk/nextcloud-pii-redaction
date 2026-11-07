"""Entry point: FastAPI application, AppAPI lifecycle, graceful shutdown.

The routes AppAPI expects come from nc_py_api's ``set_handlers``:

- ``GET /heartbeat`` answers ``{"status": "ok"}`` without authentication. It is
  the health probe of AppAPI and of the Docker HEALTHCHECK (docker/healthcheck.sh).
- ``POST /init`` acknowledges at once; an app that has to fetch models or build
  an index reports progress from a background task instead of blocking here.
- ``PUT /enabled?enabled=0|1`` calls ``enabled_handler``. It has to be a
  coroutine: a synchronous handler is deprecated in nc-py-api 0.30.x and gone
  in 0.31.0, and pyproject.toml turns that warning into a test failure.

Every other route passes ``AppAPIAuthMiddleware``: it checks EX-APP-ID against
APP_ID, requires EX-APP-VERSION and compares the secret inside
AUTHORIZATION-APP-API with APP_SECRET, and answers 401 otherwise. The user id
comes from that header alone and never from a request body.

Graceful shutdown: uvicorn turns SIGTERM into the end of the lifespan. The
``finally`` block below cancels the background tasks with a deadline below the
ten seconds Docker waits before SIGKILL.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any, Final

from fastapi import FastAPI

from pii_redaction_backend import APP_ID, companion, config, logs, settings
from pii_redaction_backend.api import build_router
from pii_redaction_backend.nc import AppAPIAuthMiddleware, AsyncNextcloudApp, run_app, set_handlers
from pii_redaction_backend.runner.runner import Runner

LOGGER = logging.getLogger(APP_ID)

# What AppAPI shows the admin when enabling fails. The detail goes to the log.
ENABLE_FAILED: Final = "PII Redaction could not register its settings page. Details are in the log of the ExApp."

# How long the shutdown waits for background tasks before it cancels them.
TASK_STOP_SECONDS: Final = 5.0

# Strong references to background tasks, otherwise the event loop may drop them.
_TASKS: set[asyncio.Task[None]] = set()


def start_background(coroutine: Coroutine[Any, Any, None], name: str) -> asyncio.Task[None]:
    """Start a task that the shutdown waits for and, after the deadline, cancels."""
    task = asyncio.get_running_loop().create_task(coroutine, name=name)
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


async def stop_background(deadline: float = TASK_STOP_SECONDS) -> int:
    """Wait for every background task up to the deadline, cancel the rest; returns how many were cancelled."""
    pending = list(_TASKS)
    if not pending:
        return 0
    _, still_running = await asyncio.wait(pending, timeout=deadline)
    for task in still_running:
        task.cancel()
    await asyncio.gather(*still_running, return_exceptions=True)
    return len(still_running)


async def enabled_handler(enabled: bool, nc: AsyncNextcloudApp) -> str:
    """Register or remove the settings page. An empty string is success for AppAPI."""
    try:
        if enabled:
            await settings.register(nc)
        else:
            await settings.unregister(nc)
    except Exception as exc:
        LOGGER.error("enable handler failed", extra={"enabled": enabled, "exc_type": type(exc).__name__})
        return ENABLE_FAILED
    LOGGER.info("enable state changed", extra={"enabled": enabled})
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging, register the AppAPI routes once, stop in order."""
    logs.configure(config.log_level())
    # set_handlers adds routes to the application object, which outlives the
    # lifespan; a test suite that enters it twice would otherwise get two copies.
    if not getattr(app.state, "handlers_registered", False):
        set_handlers(app, enabled_handler)  # pyright: ignore[reportArgumentType]
        app.state.handlers_registered = True
    LOGGER.info("starting", extra={"version": config.app_version(), "binding": config.binding_mode()})
    # Is the PHP app there? Asked now and every five minutes (companion.py);
    # the runner claims work only while the answer is ok.
    checker = start_background(companion.run_periodic(), "companion")
    stop = asyncio.Event()
    worker = Runner()
    app.state.runner = worker
    start_background(worker.run(stop), "runner")
    try:
        yield
    finally:
        # The companion loop never ends on its own; the runner finishes its
        # round and leaves at the next pause, or is cancelled at the deadline.
        checker.cancel()
        stop.set()
        cancelled = await stop_background()
        app.state.runner = None
        LOGGER.info("stopped", extra={"cancelled_tasks": cancelled})


APP = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
APP.add_middleware(AppAPIAuthMiddleware)
# /status, /jobs/{job_id}/pages/{n}.png, /jobs/{job_id}/output: signed only (api/__init__.py).
APP.include_router(build_router())


def main() -> None:
    """Start uvicorn the way AppAPI expects: unix socket behind HaRP, TCP otherwise."""
    unusable = config.unusable_startup_variables()
    if unusable:
        raise SystemExit(f"{APP_ID}: cannot start, missing or not a number: {', '.join(unusable)}")
    run_app(
        f"{APP_ID}.main:APP",
        log_level=config.log_level(),
        log_config=None,
        # Every request path would land in the log; logs.py silences the
        # logger as well, this keeps uvicorn from writing it at all.
        access_log=False,
        timeout_graceful_shutdown=config.GRACEFUL_SHUTDOWN_SECONDS,
    )


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
