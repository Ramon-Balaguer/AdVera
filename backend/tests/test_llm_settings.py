"""Runtime settings and the Ollama provider, with an in-process HTTP transport."""

import json

import httpx
import pytest

from app import runtime_settings
from app.config import Settings
from app.llm import (
    LLMConfigurationError,
    LLMInvalidOutput,
    LLMUnavailable,
    OllamaProvider,
    list_ollama_models,
    strip_reasoning,
)


def settings(tmp_path, **overrides) -> Settings:
    return Settings(_env_file=None, runtime_settings_path=str(tmp_path / "s.json"), **overrides)


def test_file_overrides_environment_defaults_and_bad_file_is_ignored(tmp_path):
    base = settings(tmp_path, llm_base_url="http://env:11434", llm_model="env-model")
    assert runtime_settings.load(base).llm_model == "env-model"
    updated = runtime_settings.load(base).model_copy(update={"llm_model": "file-model"})
    runtime_settings.save(base, updated)
    assert runtime_settings.load(base).llm_model == "file-model"
    (tmp_path / "s.json").write_text("{corrupt")
    assert runtime_settings.load(base).llm_model == "env-model"


def test_url_validation():
    assert (
        runtime_settings.RuntimeSettings(llm_base_url=" https://h:1/ ").llm_base_url
        == "https://h:1"
    )
    for bad in ("ftp://h", "h:11434", "http://user:pw@h"):
        with pytest.raises(ValueError):
            runtime_settings.RuntimeSettings(llm_base_url=bad)


def transport(handler):
    return httpx.MockTransport(handler)


async def test_ollama_sends_schema_disables_thinking_and_strips_reasoning():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        content = '<think>internal reasoning</think>{"answer": "ok"}'
        return httpx.Response(200, json={"message": {"content": content}})

    provider = OllamaProvider("http://h", "m", 30, transport=transport(handler))
    result = await provider.complete_json("sys", "user", {"type": "object"}, context_tokens=4096)

    assert result.parsed == {"answer": "ok"}
    assert "reasoning" not in result.raw
    assert seen["think"] is False and seen["stream"] is False
    assert seen["format"] == {"type": "object"}
    assert seen["options"]["num_ctx"] == 4096 and seen["options"]["temperature"] == 0


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(404, json={}), LLMConfigurationError),
        (httpx.Response(500, json={}), LLMUnavailable),
        (httpx.Response(200, json={"message": {"content": "not json"}}), LLMInvalidOutput),
        (httpx.Response(200, json={"unexpected": True}), LLMInvalidOutput),
    ],
)
async def test_ollama_failures_are_classified(response, error):
    provider = OllamaProvider("http://h", "m", 30, transport=transport(lambda r: response))
    with pytest.raises(error):
        await provider.complete_json("s", "u", {}, context_tokens=1024)


def test_missing_model_is_a_configuration_error():
    with pytest.raises(LLMConfigurationError):
        OllamaProvider("http://h", "", 30)


async def test_model_discovery_uses_read_only_tags():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "b"}, {"name": "a"}]})

    assert await list_ollama_models("http://h", transport=transport(handler)) == ["a", "b"]


def test_strip_reasoning():
    assert strip_reasoning("<THINK>x\ny</THINK> {}") == "{}"


def test_settings_api_round_trip_and_invalid_update(client, tmp_path, monkeypatch):
    response = client.put(
        "/api/settings", json={"llm_base_url": "https://llm.example", "llm_model": "m1"}
    )
    assert response.status_code == 200 and response.json()["llm_configured"] is True
    assert client.put("/api/settings", json={"llm_output_language": "fr"}).status_code == 422
    assert client.get("/api/settings").json()["llm_model"] == "m1"
    assert client.get("/api/settings").json()["llm_output_language"] == "es"


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://[fe80::1]:11434",
        "http://0.0.0.0:11434",
        "http://[::ffff:169.254.169.254]",
        "http://224.0.0.1",
        "http://metadata.google.internal",
        "http://postgres:5432",
        "http://redis:6379",
        "http://api:8000",
    ],
)
def test_unsafe_llm_destinations_are_rejected_before_saving(client, url):
    before = client.get("/api/settings").json()
    response = client.put("/api/settings", json={"llm_base_url": url})
    assert (response.status_code, response.json()["detail"]) == (422, "UNSAFE_DESTINATION")
    assert client.get("/api/settings").json() == before
    discovery = client.post("/api/settings/ollama/models", json={"base_url": url})
    assert (discovery.status_code, discovery.json()["detail"]) == (422, "UNSAFE_DESTINATION")


def test_lan_and_loopback_ollama_addresses_stay_allowed(client):
    for url in ("http://192.168.1.20:11434", "http://10.0.0.5:11434", "http://127.0.0.1:11434"):
        response = client.put("/api/settings", json={"llm_base_url": url})
        assert response.status_code == 200, url
