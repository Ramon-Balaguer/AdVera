"""The OpenAI-compatible provider, with an in-process HTTP transport (ADR 0023)."""

import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.llm import (
    LLMConfigurationError,
    LLMInvalidOutput,
    LLMUnavailable,
    OllamaProvider,
    OpenAIProvider,
    list_models,
    openai_root,
    provider_for,
)
from app.summary_worker import default_provider


def transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def sse(*pieces: dict | str) -> httpx.Response:
    """A server-sent-events answer: one `data:` line per piece and the final `[DONE]`."""
    lines = [f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in pieces]
    return httpx.Response(
        200, content="".join(lines).encode(), headers={"content-type": "text/event-stream"}
    )


def delta(content: str | None = None, finish: str | None = None, **extra) -> dict:
    return {
        "choices": [
            {
                "delta": ({"content": content} if content is not None else {}) | extra,
                "finish_reason": finish,
            }
        ]
    }


async def test_the_request_carries_the_schema_and_asks_for_a_stream_without_thinking():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["path"] = request.url.path
        return sse(delta('{"answer": "ok"}'), delta(finish="stop"), "[DONE]")

    provider = OpenAIProvider(
        "http://h:8080/", "m", 30, transport=transport(handler), max_output_tokens=900
    )
    result = await provider.complete_json("sys", "user", {"type": "object"}, context_tokens=4096)

    assert result.parsed == {"answer": "ok"}
    assert seen["path"] == "/v1/chat/completions"
    assert seen["model"] == "m" and seen["stream"] is True and seen["temperature"] == 0
    assert seen["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["max_tokens"] == 900
    assert "num_ctx" not in seen and "options" not in seen  # the server decides the context
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]


async def test_a_streamed_answer_is_joined_and_reasoning_pieces_are_never_read():
    response = sse(
        delta(None, reasoning_content="private thoughts"),
        delta('{"answer": '),
        {"choices": []},  # a usage-only chunk has no choices
        delta('"ok"}'),
        delta(finish="stop"),
        "[DONE]",
    )
    provider = OpenAIProvider("http://h", "m", 30, transport=transport(lambda r: response))
    result = await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert result.parsed == {"answer": "ok"} and "private" not in result.raw


async def test_an_answer_cut_by_the_output_limit_is_reported_as_truncated():
    response = sse(delta('{"summary": "a'), delta(finish="length"), "[DONE]")
    provider = OpenAIProvider("http://h", "m", 30, transport=transport(lambda r: response))
    with pytest.raises(LLMInvalidOutput) as caught:
        await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert caught.value.code == "LLM_OUTPUT_TRUNCATED"


@pytest.mark.parametrize(
    ("response", "error", "code"),
    [
        (httpx.Response(404, json={}), LLMConfigurationError, "LLM_MODEL_NOT_FOUND"),
        (httpx.Response(500, json={}), LLMUnavailable, "LLM_HTTP_ERROR"),
        (sse(delta("not json"), "[DONE]"), LLMInvalidOutput, "LLM_INVALID_JSON"),
        (sse("{not an event"), LLMInvalidOutput, "LLM_INVALID_RESPONSE"),
        (sse(delta("{"), {"error": {"message": "crashed"}}), LLMUnavailable, "LLM_STREAM_ERROR"),
    ],
)
async def test_failures_are_classified_like_the_ollama_ones(response, error, code):
    provider = OpenAIProvider("http://h", "m", 30, transport=transport(lambda r: response))
    with pytest.raises(error) as caught:
        await provider.complete_json("s", "u", {}, context_tokens=1024)
    assert caught.value.code == code


async def test_the_overall_time_limit_still_applies_while_streaming():
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices": [{"delta": {"content": "{"}}]}\n\n'
            await asyncio.sleep(5)
            yield b"data: [DONE]\n\n"

    provider = OpenAIProvider(
        "http://h", "m", 0.2, transport=transport(lambda r: httpx.Response(200, stream=Slow()))
    )
    with pytest.raises(LLMUnavailable):
        await provider.complete_json("s", "u", {}, context_tokens=1024)


def test_a_model_is_required():
    with pytest.raises(LLMConfigurationError):
        OpenAIProvider("http://h", "", 30)


def test_the_address_is_accepted_with_or_without_v1():
    assert openai_root("http://h:8080") == "http://h:8080"
    assert openai_root("http://h:8080/") == "http://h:8080"
    assert openai_root("http://h:8080/v1") == "http://h:8080"
    assert OpenAIProvider("http://h:8080/v1/", "m", 30).base_url == "http://h:8080"


async def test_model_discovery_reads_v1_models_and_sorts_the_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "rag"}, {"id": "chat"}]})

    assert await list_models("openai", "http://h:8080/v1", transport=transport(handler)) == [
        "chat",
        "rag",
    ]


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(500, json={}), "OPENAI_HTTP_ERROR"),
        (httpx.Response(200, json={"models": []}), "OPENAI_INVALID_RESPONSE"),
        (httpx.Response(200, text="<html>"), "OPENAI_INVALID_RESPONSE"),
    ],
)
async def test_model_discovery_failures_have_their_own_codes(response, code):
    with pytest.raises((LLMUnavailable, LLMInvalidOutput)) as caught:
        await list_models("openai", "http://h", transport=transport(lambda r: response))
    assert caught.value.code == code


async def test_an_unreachable_server_is_reported_as_unreachable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailable) as caught:
        await list_models("openai", "http://h", transport=transport(refuse))
    assert caught.value.code == "OPENAI_UNREACHABLE"


async def test_an_unknown_provider_is_a_configuration_error():
    with pytest.raises(LLMConfigurationError):
        provider_for("nope", "http://h", "m", 30)
    with pytest.raises(LLMConfigurationError):
        await list_models("nope", "http://h")


def test_a_job_is_run_by_the_provider_it_was_created_with():
    settings = Settings(_env_file=None)

    class Job:
        base_url, model = "http://h:8080", "m"

    for name, expected in (("ollama", OllamaProvider), ("openai", OpenAIProvider)):
        job = Job()
        job.provider = name
        assert type(default_provider(job, settings)) is expected


@pytest.mark.parametrize("cls", [OllamaProvider, OpenAIProvider])
async def test_the_api_key_is_sent_as_a_bearer_token_only_when_there_is_one(cls):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        if cls is OpenAIProvider:
            return sse(delta('{"a": 1}'), delta(finish="stop"), "[DONE]")
        return httpx.Response(200, content=b'{"message": {"content": "{\\"a\\": 1}"}, "done": true}\n')

    for key, expected in (("sk-1", "Bearer sk-1"), ("", None)):
        provider = cls("http://h", "m", 30, transport=transport(handler), api_key=key)
        await provider.complete_json("s", "u", {"type": "object"}, context_tokens=1024)
        assert seen[-1] == expected


async def test_model_discovery_sends_the_api_key():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"data": [{"id": "m"}], "models": [{"name": "m"}]})

    for provider in ("openai", "ollama"):
        await list_models(provider, "http://h", transport=transport(handler), api_key="k")
    assert seen == ["Bearer k", "Bearer k"]
