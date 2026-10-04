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
    assert seen["think"] is False and seen["stream"] is True
    assert seen["format"] == {"type": "object"}
    assert seen["options"]["num_ctx"] == 4096 and seen["options"]["temperature"] == 0
    assert "num_predict" not in seen["options"]  # only when a cap is configured


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


def ndjson(*pieces: dict) -> httpx.Response:
    lines = [json.dumps(p) + chr(10) for p in pieces]
    return httpx.Response(200, content="".join(lines).encode())


async def test_a_streamed_answer_is_joined_and_reasoning_pieces_are_ignored():
    # Streaming keeps a reverse proxy from cutting a long extraction for silence (504 at ~90 s).
    response = ndjson(
        {"message": {"role": "assistant", "content": "", "thinking": "private"}, "done": False},
        {"message": {"content": '{"answer": '}, "done": False},
        {"message": {"content": '"ok"}'}, "done": False},
        {"message": {"content": ""}, "done": True, "done_reason": "stop"},
    )
    provider = OllamaProvider("http://h", "m", 30, transport=transport(lambda r: response))
    result = await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert result.parsed == {"answer": "ok"} and "private" not in result.raw


async def test_an_answer_cut_by_the_context_is_reported_as_truncated():
    response = ndjson(
        {"message": {"content": '{"summary": "a'}, "done": False},
        {"message": {"content": ""}, "done": True, "done_reason": "length"},
    )
    provider = OllamaProvider("http://h", "m", 30, transport=transport(lambda r: response))
    with pytest.raises(LLMInvalidOutput) as caught:
        await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert caught.value.code == "LLM_OUTPUT_TRUNCATED"


async def test_an_error_in_the_middle_of_the_stream_is_retryable():
    response = ndjson({"message": {"content": "{"}, "done": False}, {"error": "model crashed"})
    provider = OllamaProvider("http://h", "m", 30, transport=transport(lambda r: response))
    with pytest.raises(LLMUnavailable) as caught:
        await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert caught.value.code == "LLM_STREAM_ERROR"


async def test_the_overall_time_limit_still_applies_while_streaming():
    import asyncio

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"message": {"content": "{"}, "done": false}' + bytes([10])
            await asyncio.sleep(5)
            yield b'{"message": {"content": "}"}, "done": true}' + bytes([10])

    provider = OllamaProvider(
        "http://h", "m", 0.2, transport=transport(lambda r: httpx.Response(200, stream=Slow()))
    )
    with pytest.raises(LLMUnavailable):
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


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Tests never hit a real resolver; names in `NAMES` resolve to fixed addresses."""
    names = {
        "llm.example": ["203.0.113.10"],
        "localhost": ["::1", "127.0.0.1"],
        "internal.example": ["169.254.169.254"],
        "ollama.lan": ["192.168.1.20"],
    }
    monkeypatch.setattr("app.net_safety._resolve", lambda host: names.get(host, []))
    return names


def test_settings_api_round_trip_and_invalid_update(client, tmp_path, monkeypatch):
    response = client.put(
        "/api/settings", json={"llm_base_url": "https://llm.example", "llm_model": "m1"}
    )
    assert response.status_code == 200 and response.json()["llm_configured"] is True
    assert client.put("/api/settings", json={"llm_output_language": "fr"}).status_code == 422
    assert client.get("/api/settings").json()["llm_model"] == "m1"
    assert client.get("/api/settings").json()["llm_output_language"] == "en"  # the default
    assert client.put("/api/settings", json={"llm_output_language": "ca"}).status_code == 200
    assert client.get("/api/settings").json()["llm_output_language"] == "ca"


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
        "http://2852039166",  # 169.254.169.254 as one decimal number
        "http://0xa9fea9fe",  # ...as hex
        "http://169.254.43518",  # ...as three parts
        "http://0251.0376.0251.0376",  # ...as octal
        "http://[fe80::1%25eth0]",
        "http://169.254.169.254.",  # trailing dot
        "http://internal.example",  # a name that resolves to the metadata address
    ],
)
def test_unsafe_llm_destinations_are_rejected_before_saving(client, url):
    before = client.get("/api/settings").json()
    response = client.put("/api/settings", json={"llm_base_url": url})
    assert (response.status_code, response.json()["detail"]) == (422, "UNSAFE_DESTINATION")
    assert client.get("/api/settings").json() == before
    discovery = client.post("/api/settings/models", json={"base_url": url})
    assert (discovery.status_code, discovery.json()["detail"]) == (422, "UNSAFE_DESTINATION")


def test_lan_and_loopback_ollama_addresses_stay_allowed(client):
    allowed = (
        "http://192.168.1.20:11434",
        "http://10.0.0.5:11434",
        "http://127.0.0.1:11434",
        "http://0x7f.1:11434",  # legacy spelling of 127.0.0.1
        "http://[::1]:11434",  # IPv6 loopback is "reserved" for Python but is a local server
        "http://localhost:11434",  # resolves to ::1 first on many machines: the project default
        "http://ollama.lan:11434",
    )
    for url in allowed:
        response = client.put("/api/settings", json={"llm_base_url": url})
        assert response.status_code == 200, url


def test_a_name_that_does_not_resolve_is_refused_when_saving(client):
    response = client.put("/api/settings", json={"llm_base_url": "http://no-such-host.invalid"})
    assert (response.status_code, response.json()["detail"]) == (422, "UNRESOLVABLE_HOST")
    assert client.get("/api/settings").json()["llm_base_url"] != "http://no-such-host.invalid"


def test_legacy_ipv4_parser():
    from app.net_safety import legacy_ipv4

    assert str(legacy_ipv4("2852039166")) == "169.254.169.254"
    assert str(legacy_ipv4("0x7f.1")) == "127.0.0.1"
    assert str(legacy_ipv4("0251.0376.0251.0376")) == "169.254.169.254"
    for not_ipv4 in ("localhost", "1.2.3.4.5", "256.1.1.1", "1..2", "0xzz", "4294967296", ""):
        assert legacy_ipv4(not_ipv4) is None, not_ipv4


async def test_the_output_cap_is_sent_as_num_predict():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "{}"}, "done": True})

    provider = OllamaProvider(
        "http://h", "m", 30, transport=transport(handler), max_output_tokens=100
    )
    await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert seen["options"]["num_predict"] == 100


def test_a_malformed_url_never_overwrites_the_saved_settings(client):
    client.put("/api/settings", json={"llm_base_url": "http://192.168.1.20:11434"})
    response = client.put("/api/settings", json={"llm_base_url": "ftp://nowhere"})
    assert (response.status_code, response.json()["detail"]) == (422, "INVALID_SETTINGS")
    assert client.get("/api/settings").json()["llm_base_url"] == "http://192.168.1.20:11434"


def test_model_discovery_lists_the_models_or_reports_the_server_failure(client, monkeypatch):
    async def models(provider, base_url):
        return ["ornith-1.5:35b", "other"]

    monkeypatch.setattr("app.settings_api.list_models", models)
    found = client.post("/api/settings/models", json={"base_url": "http://127.0.0.1:11434/"})
    assert found.status_code == 200
    assert found.json() == {
        "base_url": "http://127.0.0.1:11434",
        "models": ["ornith-1.5:35b", "other"],
    }

    async def down(provider, base_url):
        raise LLMUnavailable("LLM_UNAVAILABLE")

    monkeypatch.setattr("app.settings_api.list_models", down)
    failed = client.post("/api/settings/models", json={"base_url": "http://127.0.0.1:11434"})
    assert failed.status_code == 502 and failed.json()["detail"] == "LLM_UNAVAILABLE"

    invalid = client.post("/api/settings/models", json={"base_url": "ftp://nowhere"})
    assert (invalid.status_code, invalid.json()["detail"]) == (422, "INVALID_URL")


def test_the_provider_can_be_chosen_and_an_unknown_one_is_refused(client):
    assert client.get("/api/settings").json()["llm_provider"] == "ollama"
    saved = client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "llm_base_url": "http://192.168.1.20:8080",
            "llm_model": "rag",
        },
    )
    assert saved.status_code == 200 and saved.json()["llm_provider"] == "openai"
    assert client.get("/api/settings").json()["llm_provider"] == "openai"
    assert client.put("/api/settings", json={"llm_provider": "other"}).status_code == 422
    assert client.get("/api/settings").json()["llm_provider"] == "openai"


def test_model_discovery_asks_the_chosen_provider(client, monkeypatch):
    asked = []

    async def models(provider, base_url):
        asked.append((provider, base_url))
        return ["chat", "rag"]

    monkeypatch.setattr("app.settings_api.list_models", models)
    found = client.post(
        "/api/settings/models", json={"provider": "openai", "base_url": "http://127.0.0.1:8080"}
    )
    assert found.status_code == 200 and found.json()["models"] == ["chat", "rag"]
    client.post("/api/settings/models", json={"base_url": "http://127.0.0.1:11434"})
    assert asked == [("openai", "http://127.0.0.1:8080"), ("ollama", "http://127.0.0.1:11434")]
