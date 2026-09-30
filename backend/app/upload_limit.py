"""Reject oversized or unsized media uploads before the body is read (QA/Security review).

Starlette spools multipart file parts to a temporary file with no size cap before the
endpoint runs, so the endpoint's own byte counter only fires after the whole upload is on
disk. This ASGI middleware checks `Content-Length` first: a request without it (chunked) is
refused with 411 and one larger than the import limit with 413, both before any body byte is
consumed. A body that then sends more than it declared is cut by the HTTP server.
"""

import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

IMPORT_PATH = re.compile(r"^/api/meetings/[^/]+/imports$")
MULTIPART_OVERHEAD = 1024 * 1024  # boundaries and headers around the file


class UploadLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not IMPORT_PATH.match(scope["path"])
        ):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        declared = headers.get("content-length", "")
        limit = get_settings().media_import_max_bytes + MULTIPART_OVERHEAD
        if not declared.isdigit():
            response = JSONResponse({"detail": "LENGTH_REQUIRED"}, status_code=411)
        elif int(declared) > limit:
            response = JSONResponse({"detail": "FILE_TOO_LARGE"}, status_code=413)
        else:
            await self.app(scope, receive, send)
            return
        await response(scope, receive, send)
