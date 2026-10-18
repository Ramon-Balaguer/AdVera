from importlib.metadata import version

from fastapi.routing import APIRoute

from app.main import app

REQUIRED_PATHS = {
    "/api/health",
    # Meeting bot (ADR 0026) and the call's chat (ADR 0027).
    "/api/meeting-bot/capabilities",
    "/api/meetings/{meeting_id}/bot",
    "/api/meetings/{meeting_id}/chat",
    "/api/integrations/vexa/webhook",
}


def test_documentation_endpoints_are_published(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 200


def test_openapi_identifies_advera_and_every_route(client):
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "AdVera API"
    assert schema["info"]["version"] == version("advera-backend")
    registered = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.include_in_schema
    }
    assert REQUIRED_PATHS <= set(schema["paths"])
    assert registered <= set(schema["paths"])


def test_meeting_bot_contract(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/api/meetings/{meeting_id}/bot"]) == {"get", "post", "delete"}
    start = paths["/api/meetings/{meeting_id}/bot"]["post"]
    assert start["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "BotStartRequest"
    )
    assert "post" in paths["/api/integrations/vexa/webhook"]
