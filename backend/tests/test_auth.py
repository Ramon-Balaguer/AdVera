"""Shared API access token (ADR 0019)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings

TOKEN = "s3cret-lan-token"


@pytest.fixture
def secured(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setenv("API_TOKEN", TOKEN)
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_open_when_no_token_is_configured(client):
    assert client.get("/api/session").json() == {"access": "open"}
    assert client.get("/api/settings").status_code == 200


def test_rest_requires_the_token(secured):
    assert secured.get("/api/health").status_code == 200
    assert secured.get("/api/session").json() == {"access": "required"}
    for path in ("/api/settings", "/api/meetings", "/api/memory/overview"):
        assert secured.get(path).status_code == 401
    assert secured.delete("/api/meetings/anything").status_code == 401
    assert secured.get("/api/settings", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_bearer_token_is_accepted_for_non_browser_clients(secured):
    response = secured.get("/api/settings", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


def test_session_cookie_replaces_the_token_and_never_contains_it(secured, monkeypatch):
    monkeypatch.setattr("app.auth.FAILED_LOGIN_DELAY_SECONDS", 0)
    wrong = secured.post("/api/session", json={"token": "wrong"})
    assert wrong.status_code == 401 and "set-cookie" not in wrong.headers
    ok = secured.post("/api/session", json={"token": TOKEN})
    assert ok.status_code == 204
    cookie = ok.headers["set-cookie"]
    assert TOKEN not in cookie
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert secured.get("/api/session").json() == {"access": "authenticated"}
    assert secured.get("/api/settings").status_code == 200
    secured.delete("/api/session")
    assert secured.get("/api/settings").status_code == 401


def test_websocket_handshake_is_guarded(secured):
    with pytest.raises(WebSocketDisconnect):
        with secured.websocket_connect("/ws/query/anything"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with secured.websocket_connect("/ws/capture-agents/some-agent"):
            pass


def test_agent_socket_accepts_the_same_bearer_token(secured):
    from app.capture_agent import _authorized

    class Fake:
        headers = {"authorization": "Bearer anything"}

    # With API_TOKEN set the middleware is the gate; the per-socket legacy check defers to it.
    assert _authorized(Fake()) is True
