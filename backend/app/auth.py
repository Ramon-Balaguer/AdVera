"""Shared API access token for LAN deployments (ADR 0019, amending ADR 0015).

When `API_TOKEN` is set, every `/api/*` and `/ws/*` request must present it, except the
health check and the session endpoints. Browsers exchange the token once for an HttpOnly,
SameSite=Strict cookie, so REST calls, WebSockets and `<audio>` elements (which cannot send
headers) are all covered and cross-site pages cannot ride the session. Non-browser clients
(the Capture Agent) send `Authorization: Bearer <token>`. Without a token the API stays open,
as ADR 0015 describes, which is only acceptable on a trusted machine.
"""

import asyncio
import hashlib
import hmac
from http.cookies import SimpleCookie

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

COOKIE = "advera_session"
PUBLIC_PATHS = {"/api/health", "/api/session"}
FAILED_LOGIN_DELAY_SECONDS = 1.0

router = APIRouter(tags=["session"])


def _session_value(token: str) -> str:
    # The cookie never carries the token itself.
    return hmac.new(token.encode(), b"advera-session-v1", hashlib.sha256).hexdigest()


def _authorized(token: str, headers: dict[str, str]) -> bool:
    bearer = headers.get("authorization", "")
    if bearer and hmac.compare_digest(bearer, f"Bearer {token}"):
        return True
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("cookie", ""))
    except Exception:
        return False
    morsel = cookie.get(COOKIE)
    return bool(morsel) and hmac.compare_digest(morsel.value, _session_value(token))


def access_state(request: Request) -> str:
    token = get_settings().api_token
    if not token:
        return "open"
    headers = {key.lower(): value for key, value in request.headers.items()}
    return "authenticated" if _authorized(token, headers) else "required"


class AccessTokenMiddleware:
    """Pure ASGI middleware, so it guards WebSocket handshakes as well as HTTP."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = get_settings().api_token
        path = scope.get("path", "")
        guarded = scope["type"] in ("http", "websocket") and (
            path.startswith("/api/") or path.startswith("/ws/")
        )
        if not token or not guarded or path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if _authorized(token, headers):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Closing before accept rejects the handshake (HTTP 403).
            await send({"type": "websocket.close", "code": 4401})
            return
        response = Response(
            content=b'{"detail":"UNAUTHORIZED"}',
            status_code=401,
            media_type="application/json",
        )
        await response(scope, receive, send)


class SessionState(BaseModel):
    access: str  # "open" (no token configured), "authenticated" or "required"


@router.get("/api/session", response_model=SessionState)
async def session_state(request: Request) -> SessionState:
    return SessionState(access=access_state(request))


class SessionRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


@router.post("/api/session", status_code=204)
async def create_session(body: SessionRequest, response: Response) -> Response:
    token = get_settings().api_token
    if not token:
        response.status_code = 204
        return response
    if not hmac.compare_digest(body.token, token):
        await asyncio.sleep(FAILED_LOGIN_DELAY_SECONDS)  # slows guessing
        return Response(
            content=b'{"detail":"INVALID_TOKEN"}', status_code=401, media_type="application/json"
        )
    response.status_code = 204
    response.set_cookie(
        COOKIE,
        _session_value(token),
        httponly=True,
        samesite="strict",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.delete("/api/session", status_code=204)
async def delete_session(response: Response) -> Response:
    response.status_code = 204
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return response
