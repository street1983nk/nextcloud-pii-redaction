"""The signed container routes of the contract with the PHP app (01-SKELETON.md).

Every route sits behind ``AppAPIAuthMiddleware`` (main.py): a request without
a valid AppAPI signature is answered with 401 before it reaches a handler.
appinfo/info.xml declares no route at all (an empty ``<routes/>``), so HaRP
lets no browser reach them; only ExAppService in the PHP app calls them,
signed, through ``exAppRequest``.

The routes answer with ids, numbers and words of the closed lists, and with
the two files the contract names (page 1 as PNG, the finished output). No
answer carries a file name, a path or document text.
"""

from fastapi import APIRouter


def build_router() -> APIRouter:
    """All container routes in one router for main.py."""
    from pii_redaction_backend.api import output, pages, status

    router = APIRouter()
    router.include_router(status.router)
    router.include_router(pages.router)
    router.include_router(output.router)
    return router
