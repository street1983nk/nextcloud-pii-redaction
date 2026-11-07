"""The only module that talks HTTP: nc_py_api for the AppAPI contract, httpx for the PHP app.

Every other module takes the AppAPI building blocks and the calls into
Nextcloud from here. Three reasons, the first two from Findling:

1. An nc_py_api update hits exactly one file. The sync API disappears in 0.31.0,
   so only the async entry points are handed out.
2. What the container may do in Nextcloud is checkable by reading one file.
   tests/test_boundary.py fails when another module imports nc_py_api or an
   HTTP client.
3. APP_SECRET only ever leaves this process inside the signed headers built
   here; the child processes never see it (workers/child.py).

What the container may do in Nextcloud, all of it signed as this ExApp with an
empty user (the PHP app acts as the initiator of a job by itself):

- ``claim``, ``progress``, ``ack``: the work queue of the PHP app
  (QueueController). Every answer is checked field by field against the closed
  lists of model.py and the shapes of 01-SKELETON.md; an answer outside them is
  discarded, never half used.
- ``fetch_source``: the job bound gateway. It hands out only the file of the
  job this container holds the claim token for, only while the lease runs and
  only while the etag is the one the job was started with (409 otherwise).
- ``fetch_handshake``: is the PHP app there (companion.py)?

Clients of nc_py_api live only inside ``nc_app()``: every AsyncNextcloudApp
opens its own HTTP sessions and nc_py_api has no public close, so a client that
is never closed leaks connections until the garbage collector finds it
(Gameworld WR-05). The httpx client is one per runner (``new_client``) and never
follows a redirect: a redirect would carry the signed headers to another host.

Logs carry the job id, an HTTP status, a byte count and a reason code; never a
URL (it holds the claim token), a user, an etag or a body.
"""

import asyncio
import hashlib
import logging
import os
import re
from base64 import b64encode
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final

import httpx
from nc_py_api import AsyncNextcloudApp, NextcloudException
from nc_py_api.ex_app import AppAPIAuthMiddleware, run_app, set_handlers
from nc_py_api.ex_app.ui.settings import SettingsField, SettingsFieldType, SettingsForm

from pii_redaction_backend.model import AckResult, Reason, Stage, Task

__all__ = [
    "AppAPIAuthMiddleware",
    "AsyncNextcloudApp",
    "Claim",
    "FetchResult",
    "NextcloudException",
    "SettingsField",
    "SettingsFieldType",
    "SettingsForm",
    "ack",
    "app_api_headers",
    "claim",
    "close_nc",
    "fetch_handshake",
    "fetch_source",
    "nc_app",
    "new_client",
    "progress",
    "run_app",
    "set_handlers",
]

LOGGER = logging.getLogger(__name__)

# The release the code was read against; an upgrade re-verifies this module.
NC_PY_API_VERIFIED_VERSION: Final = "0.30.3"

_ADAPTERS: Final = ("adapter", "adapter_dav")


async def close_nc(nc: object) -> None:
    """Close both HTTP sessions of a client; a failure while closing is logged, never raised."""
    session = getattr(nc, "_session", None)
    for name in _ADAPTERS:
        close = getattr(getattr(session, name, None), "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception as exc:  # closing must never disturb the caller
            LOGGER.debug("nextcloud session not closed", extra={"exc_type": type(exc).__name__})


@asynccontextmanager
async def nc_app() -> AsyncIterator[AsyncNextcloudApp]:
    """A client in the app context without a user, closed on every way out."""
    nc = AsyncNextcloudApp()
    try:
        yield nc
    finally:
        await close_nc(nc)


# -- the routes of the PHP app ---------------------------------------------------

API_BASE: Final = "/ocs/v2.php/apps/pii_redaction/api/v1"
CLAIM_PATH: Final = API_BASE + "/queue/claim"
PROGRESS_PATH: Final = API_BASE + "/queue/{job_id}/progress"
ACK_PATH: Final = API_BASE + "/queue/{job_id}/ack"
FILES_PATH: Final = "/ocs/v2.php/apps/pii_redaction/api/v1/files/{job_id}"
HANDSHAKE_PATH: Final = API_BASE + "/handshake"

# The PHP app names the etag it served in this header (GatewayController).
ETAG_HEADER: Final = "X-Pii-Etag"

_DEFAULT_AA_VERSION: Final = "2.2.0"
# Connect fast or fail; a block of a large file may take a while on slow storage.
_TIMEOUT: Final = httpx.Timeout(60.0, connect=10.0)
# One mebibyte per block (Findling's measured value); nothing is kept per block.
CHUNK_SIZE: Final = 1024 * 1024
_OK: Final = 200
_CONFLICT: Final = 409

# Shapes of the fields of a claim (01-SKELETON.md, columns of pii_jobs).
_TOKEN: Final = re.compile(r"[0-9a-f]{16,64}")
_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_TASKS: Final = frozenset(item.value for item in Task)
_ETAG_MAX: Final = 40
_USER_MAX: Final = 64


def _base_url() -> str:
    """NEXTCLOUD_URL normalised the way nc_py_api does it."""
    return os.environ.get("NEXTCLOUD_URL", "").removesuffix("/").removesuffix("/index.php").removesuffix("/")


def app_api_headers(header_user: str = "") -> dict[str, str]:
    """The headers AppAPI authenticates an ExApp call with, built from the environment."""
    secret = os.environ.get("APP_SECRET", "")
    return {
        "AA-VERSION": os.environ.get("AA_VERSION", _DEFAULT_AA_VERSION),
        "EX-APP-ID": os.environ.get("APP_ID", ""),
        "EX-APP-VERSION": os.environ.get("APP_VERSION", ""),
        "AUTHORIZATION-APP-API": b64encode(f"{header_user}:{secret}".encode()).decode(),
        "OCS-APIRequest": "true",
    }


def _certificate_setting() -> bool | str:
    """Mirror NPA_NC_CERT of nc_py_api: True, False, or a path to a CA bundle."""
    value = os.environ.get("NPA_NC_CERT", "True")
    if value.lower() in {"false", "0"}:
        return False
    if value.lower() in {"true", "1"}:
        return True
    return value


def new_client() -> httpx.AsyncClient:
    """The client for every call into the PHP app. Redirects are not followed: they would carry the credential away."""
    return httpx.AsyncClient(verify=_certificate_setting(), timeout=_TIMEOUT, follow_redirects=False)


# -- field checks (Findling nc/queue.py _mapping, _positive_int) ------------------


def _mapping(value: object) -> Mapping[str, Any] | None:
    """The value as a string keyed mapping, or None. PHP renders an empty array as ``[]``."""
    return value if isinstance(value, dict) else None


def _positive_int(value: object) -> int | None:
    """A whole number above zero, or None. Accepts the string form OCS may deliver; rejects bool."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        number = int(value)
        return number if number > 0 else None
    return None


def _etag(value: object) -> str | None:
    """An etag of 1 to 40 visible ASCII characters, or None."""
    if not isinstance(value, str) or not 0 < len(value) <= _ETAG_MAX:
        return None
    return value if value.isascii() and value.isprintable() and " " not in value else None


def _user_id(value: object) -> str | None:
    """A user id of 1 to 64 printable characters, or None."""
    if not isinstance(value, str) or not 0 < len(value) <= _USER_MAX:
        return None
    return value if value.isprintable() else None


def _ocs_data(response: httpx.Response) -> object:
    """The ``ocs.data`` part of a JSON answer, or None when it is not one."""
    try:
        payload = response.json()
    except ValueError:
        return None
    ocs = _mapping(payload)
    envelope = _mapping(ocs.get("ocs")) if ocs is not None else None
    return envelope.get("data") if envelope is not None else None


# -- the queue -------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """One task the PHP app handed to this container, every field checked."""

    job_id: int
    task: Task
    token: str
    file_id: int
    user_id: str
    etag: str
    lease_seconds: int


def _parse_claim(data: object) -> Claim | None:
    fields = _mapping(data)
    if not fields:
        return None
    job_id = _positive_int(fields.get("jobId"))
    file_id = _positive_int(fields.get("fileId"))
    lease = _positive_int(fields.get("leaseSeconds"))
    task_word = fields.get("task")
    token = fields.get("token")
    user_id = _user_id(fields.get("userId"))
    etag = _etag(fields.get("etag"))
    if (
        job_id is None
        or file_id is None
        or lease is None
        or user_id is None
        or etag is None
        or not isinstance(task_word, str)
        or task_word not in _TASKS
        or not isinstance(token, str)
        or not _TOKEN.fullmatch(token)
    ):
        LOGGER.warning("claim answer discarded", extra={"reason": "shape"})
        return None
    return Claim(
        job_id=job_id,
        task=Task(task_word),
        token=token,
        file_id=file_id,
        user_id=user_id,
        etag=etag,
        lease_seconds=lease,
    )


async def _post(client: httpx.AsyncClient, path: str, body: dict[str, object]) -> httpx.Response | None:
    """POST one queue route; None when the instance could not be reached."""
    try:
        return await client.post(
            _base_url() + path,
            params={"format": "json"},
            json=body,
            headers=app_api_headers() | {"Accept": "application/json"},
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        # Debug only: the runner counts the rounds that came back like this and
        # owns the log policy for them (Findling Poller._retreat).
        LOGGER.debug("queue not reached", extra={"exc_type": type(exc).__name__})
        return None


async def claim(client: httpx.AsyncClient) -> Claim | None:
    """Ask for one task. None for an empty queue, an error, or an answer outside its shape."""
    response = await _post(client, CLAIM_PATH, {})
    if response is None:
        return None
    if response.status_code != _OK:
        LOGGER.info("claim refused", extra={"http_status": response.status_code})
        return None
    return _parse_claim(_ocs_data(response))


def _count(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = "a count must be a whole number of zero or more"
        raise ValueError(msg)
    return value


async def _report(client: httpx.AsyncClient, path: str, job: Claim, body: dict[str, object]) -> bool:
    response = await _post(client, path.format(job_id=job.job_id), body)
    if response is None:
        return False
    if response.status_code != _OK:
        LOGGER.info("queue report refused", extra={"job_id": job.job_id, "http_status": response.status_code})
        return False
    return True


async def progress(
    client: httpx.AsyncClient, claim: Claim, stage: Stage, pages_done: int | None, pages_total: int | None
) -> bool:
    """Report the stage of a running task and extend the lease.

    False when the PHP app answered 409 (the token is no longer the one of the
    job, the lease ran out or the job left its state) or any other refusal; the
    runner then stops working on the job. A value outside its list raises
    before anything is sent.
    """
    body: dict[str, object] = {
        "token": claim.token,
        "stage": Stage(stage).value,
        "pagesDone": _count(pages_done),
        "pagesTotal": _count(pages_total),
    }
    return await _report(client, PROGRESS_PATH, claim, body)


def _ack_body(
    claim: Claim,
    result: AckResult,
    *,
    reason: Reason | None,
    pages_total: int | None,
    etag_seen: str | None,
    image: tuple[int, int] | None,
    output: tuple[str, int] | None,
) -> dict[str, object]:
    body: dict[str, object] = {"token": claim.token, "result": AckResult(result).value}
    if reason is not None:
        body["reason"] = Reason(reason).value
    if pages_total is not None:
        body["pagesTotal"] = _count(pages_total)
    if etag_seen is not None:
        if _etag(etag_seen) is None:
            msg = "etag outside its shape"
            raise ValueError(msg)
        body["etagSeen"] = etag_seen
    if image is not None:
        width, height = (_positive_int(side) for side in image)
        if width is None or height is None:
            msg = "image size must be two whole numbers above zero"
            raise ValueError(msg)
        body["image"] = {"width": width, "height": height}
    if output is not None:
        digest, size = output
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            msg = "output hash must be 64 lowercase hex digits"
            raise ValueError(msg)
        body["output"] = {"sha256": digest, "size": _count(size)}
    return body


async def ack(
    client: httpx.AsyncClient,
    claim: Claim,
    result: AckResult,
    *,
    reason: Reason | None = None,
    pages_total: int | None = None,
    etag_seen: str | None = None,
    image: tuple[int, int] | None = None,
    output: tuple[str, int] | None = None,
) -> bool:
    """Close a claimed task. False on 409 or any other refusal; a value outside its shape raises before sending."""
    body = _ack_body(
        claim, result, reason=reason, pages_total=pages_total, etag_seen=etag_seen, image=image, output=output
    )
    return await _report(client, ACK_PATH, claim, body)


# -- the job bound gateway -------------------------------------------------------


@dataclass
class FetchResult:
    """The outcome of one source download.

    ``ok`` only for a 200 with a valid etag header whose bytes stayed within the
    cap and now sit at the target. ``stale`` for a 409: the file changed since
    the job started.
    """

    ok: bool
    stale: bool
    sha256: str | None
    size: int
    etag: str | None
    http_status: int | None


def _write(handle: BinaryIO, chunk: bytes) -> None:
    handle.write(chunk)


def _open_part(part: Path) -> BinaryIO:
    part.parent.mkdir(parents=True, exist_ok=True)
    return part.open("wb")


def _unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


def _refused(job_id: int, reason: str, status: int | None, *, stale: bool = False) -> FetchResult:
    LOGGER.info("source download refused", extra={"job_id": job_id, "reason": reason, "http_status": status})
    return FetchResult(ok=False, stale=stale, sha256=None, size=0, etag=None, http_status=status)


async def _stream(client: httpx.AsyncClient, claim: Claim, part: Path, max_bytes: int) -> FetchResult:
    digest = hashlib.sha256()
    size = 0
    async with client.stream(
        "GET",
        _base_url() + FILES_PATH.format(job_id=claim.job_id),
        params={"token": claim.token},
        headers=app_api_headers(),
        follow_redirects=False,
    ) as response:
        status = response.status_code
        if status == _CONFLICT:
            return _refused(claim.job_id, "stale", status, stale=True)
        if status != _OK:
            # A redirect (not followed), a refusal or an error. The body is not
            # read: it may be an OCS document or a proxy page.
            return _refused(claim.job_id, "status", status)
        etag = _etag(response.headers.get(ETAG_HEADER))
        if etag is None:
            return _refused(claim.job_id, "etag", status)
        declared = response.headers.get("Content-Length", "")
        if declared.isascii() and declared.isdigit() and int(declared) > max_bytes:
            return _refused(claim.job_id, "too_large", status)
        handle = await asyncio.to_thread(_open_part, part)
        try:
            async for chunk in response.aiter_bytes(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    return _refused(claim.job_id, "too_large", status)
                digest.update(chunk)
                await asyncio.to_thread(_write, handle, chunk)
        finally:
            await asyncio.to_thread(handle.close)
        if declared.isascii() and declared.isdigit() and size != int(declared):
            return _refused(claim.job_id, "short_read", status)
    return FetchResult(ok=True, stale=False, sha256=digest.hexdigest(), size=size, etag=etag, http_status=status)


async def fetch_source(client: httpx.AsyncClient, claim: Claim, target: Path, *, max_bytes: int) -> FetchResult:
    """Read the source file of a claimed job into ``target``, hashing it on the way.

    The bytes go to ``target`` with the suffix ``.part`` first and replace
    ``target`` only after a complete, valid download; on every other way out
    the part file is deleted and ``target`` stays as it was. 409 is ``stale``;
    any other status, a redirect, a missing etag header, more than
    ``max_bytes``, a short read or a broken stream is not ``ok``.
    """
    part = target.with_name(target.name + ".part")
    try:
        result = await _stream(client, claim, part, max_bytes)
    except httpx.HTTPError as exc:
        LOGGER.warning("source download broke off", extra={"job_id": claim.job_id, "exc_type": type(exc).__name__})
        result = FetchResult(ok=False, stale=False, sha256=None, size=0, etag=None, http_status=None)
    except OSError as exc:
        LOGGER.warning("source could not be written", extra={"job_id": claim.job_id, "exc_type": type(exc).__name__})
        result = FetchResult(ok=False, stale=False, sha256=None, size=0, etag=None, http_status=None)
    if result.ok:
        await asyncio.to_thread(os.replace, part, target)
        LOGGER.info("source fetched", extra={"job_id": claim.job_id, "bytes": result.size})
    else:
        await asyncio.to_thread(_unlink, part)
    return result


# -- the handshake ---------------------------------------------------------------


async def _ask_handshake(client: httpx.AsyncClient) -> tuple[int | None, str | None]:
    try:
        response = await client.get(
            _base_url() + HANDSHAKE_PATH,
            params={"format": "json"},
            headers=app_api_headers() | {"Accept": "application/json"},
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        LOGGER.debug("handshake not answered", extra={"exc_type": type(exc).__name__})
        return None, None
    if response.status_code != _OK:
        return response.status_code, None
    data = _mapping(_ocs_data(response))
    version = data.get("version") if data is not None else None
    return _OK, version if isinstance(version, str) else None


async def fetch_handshake(client: httpx.AsyncClient | None = None) -> tuple[int | None, str | None]:
    """Ask the PHP app whether it is there; returns (status, version).

    200 with the version string as the PHP app sent it (unchecked, companion.py
    validates it), an error status as it came (404: not installed or not
    enabled, 412: AppAPI has not enabled this container yet), and
    ``(None, None)`` when the instance could not be reached. Never raises.
    """
    if client is not None:
        return await _ask_handshake(client)
    async with new_client() as owned:
        return await _ask_handshake(owned)
