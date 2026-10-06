"""LLM provider boundary (spec §3.5, §5 LLM; ADR 0009).

LLMProvider
  -> OllamaProvider   /api/chat with a JSON schema, deterministic options, thinking disabled
  -> AnthropicProvider  /v1/messages of the Claude API; GeminiProvider streamGenerateContent
  -> OpenAIProvider   /v1/chat/completions of an OpenAI-compatible server (llama.cpp,
                      llama-swap, vLLM...): the same request in the other protocol (ADR 0023)

The answer is streamed (one JSON line per piece) and joined here. A long extraction can take
minutes, and a reverse proxy in front of Ollama cuts a connection that stays silent for its
read timeout (one operator's cut at about 90 s with 504); streamed pieces keep it alive. The
overall time limit is still `timeout_seconds`.

The optional API key goes in an `Authorization: Bearer` header on every call.

Only the model's final structured output is kept. Thinking is disabled at the request level
and any reasoning block that still appears is stripped before parsing: chain-of-thought is
never stored (spec §3.4). Prompts and outputs are never logged.
"""

import asyncio
import json
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.runtime_settings import RuntimeSettings

# Hosted OpenAI-compatible APIs that refuse request fields they do not know.
STRICT_OPENAI_HOSTS = {
    "api.openai.com",
    "api.groq.com",
    "api.mistral.ai",
    "openrouter.ai",
}
ANTHROPIC_VERSION = "2023-06-01"
MAX_OUTPUT_CHARS = 2_000_000  # far above any valid extraction; bounds memory on a runaway model
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMError(Exception):
    """A provider failure. `code` is safe to persist; the message is never logged."""

    retryable = True

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class LLMConfigurationError(LLMError):
    retryable = False


class LLMUnavailable(LLMError):
    pass


class LLMInvalidOutput(LLMError):
    pass


@dataclass(frozen=True)
class LLMResult:
    raw: str  # final output text only, never reasoning
    parsed: dict[str, Any]


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, context_tokens: int
    ) -> LLMResult: ...


def estimate_tokens(text: str) -> int:
    # Measured on a real transcript prompt (segment ids, timestamps, ca/es text): about 2.4
    # characters per token; 3 underestimated it by a fifth (44k estimated, 56k real).
    return int(len(text) / 2.3) + 1


def strip_reasoning(text: str) -> str:
    return THINK_BLOCK.sub("", text).strip()


def anthropic_headers(api_key: str) -> dict[str, str]:
    return {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}


def gemini_headers(api_key: str) -> dict[str, str]:
    return {"x-goog-api-key": api_key}


def auth_headers(api_key: str) -> dict[str, str]:
    """The bearer header of an optional API key; none when the server needs no key."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        max_output_tokens: int | None = None,
        api_key: str = "",
    ) -> None:
        if not model:
            raise LLMConfigurationError("LLM_NOT_CONFIGURED")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.transport = transport
        self.max_output_tokens = max_output_tokens

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, context_tokens: int
    ) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": True,
            "think": False,
            "options": {"temperature": 0, "seed": 7, "num_ctx": context_tokens},
        }
        if self.max_output_tokens:
            payload["options"]["num_predict"] = self.max_output_tokens
        try:
            async with asyncio.timeout(self.timeout):
                content = await self._stream(payload)
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as error:
            raise LLMUnavailable("LLM_UNAVAILABLE") from error
        raw = strip_reasoning(str(content))
        try:
            parsed = json.loads(raw)
        except ValueError as error:
            raise LLMInvalidOutput("LLM_INVALID_JSON") from error
        if not isinstance(parsed, dict):
            raise LLMInvalidOutput("LLM_INVALID_JSON")
        return LLMResult(raw=raw, parsed=parsed)

    async def _stream(self, payload: dict[str, Any]) -> str:
        """The final answer text, joined from the streamed lines. Reasoning pieces (the
        `thinking` field) are never read."""
        parts: list[str] = []
        size = 0
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers=auth_headers(self.api_key)
        ) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise LLMConfigurationError("LLM_MODEL_NOT_FOUND")
                if response.status_code >= 400:
                    raise LLMUnavailable("LLM_HTTP_ERROR")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        piece = json.loads(line)
                        if "error" in piece:  # Ollama reports a failure mid-stream this way
                            raise LLMUnavailable("LLM_STREAM_ERROR")
                        text = piece["message"]["content"]
                    except (ValueError, KeyError, TypeError) as error:
                        raise LLMInvalidOutput("LLM_INVALID_RESPONSE") from error
                    size += len(text or "")
                    if size > MAX_OUTPUT_CHARS:
                        raise LLMInvalidOutput("LLM_OUTPUT_TOO_LARGE")
                    parts.append(str(text or ""))
                    if piece.get("done"):
                        if piece.get("done_reason") == "length":
                            # The context filled up before the JSON was closed: say so
                            # instead of reporting it as invalid JSON.
                            raise LLMInvalidOutput("LLM_OUTPUT_TRUNCATED")
                        break
        return "".join(parts)


def openai_root(base_url: str) -> str:
    """The server address without a trailing `/v1`, which the operator may have typed."""
    root = base_url.rstrip("/")
    return root[: -len("/v1")] if root.endswith("/v1") else root


class OpenAIProvider:
    """An OpenAI-compatible chat server. The JSON schema goes in `response_format`, which
    llama.cpp turns into a grammar like Ollama's `format`, so the size limits of the schema
    still hold. There is no context-size parameter in this protocol: the server decides it."""

    name = "openai"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        max_output_tokens: int | None = None,
        api_key: str = "",
    ) -> None:
        if not model:
            raise LLMConfigurationError("LLM_NOT_CONFIGURED")
        self.api_key = api_key
        self.base_url = openai_root(base_url)
        self.model = model
        self.timeout = timeout_seconds
        self.transport = transport
        self.max_output_tokens = max_output_tokens

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, context_tokens: int
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": True},
            },
            "stream": True,
            "temperature": 0,
            "seed": 7,
        }
        host = urllib.parse.urlsplit(self.base_url).hostname or ""
        if host not in STRICT_OPENAI_HOSTS:
            # Thinking off, as `think: false` in Ollama; local servers that do not know it
            # ignore it, but hosted APIs reject unknown fields.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if self.max_output_tokens:
            # OpenAI's newer models only accept the second name.
            payload["max_completion_tokens" if host == "api.openai.com" else "max_tokens"] = (
                self.max_output_tokens
            )
        try:
            async with asyncio.timeout(self.timeout):
                content = await self._stream(payload)
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as error:
            raise LLMUnavailable("LLM_UNAVAILABLE") from error
        raw = strip_reasoning(content)
        try:
            parsed = json.loads(raw)
        except ValueError as error:
            raise LLMInvalidOutput("LLM_INVALID_JSON") from error
        if not isinstance(parsed, dict):
            raise LLMInvalidOutput("LLM_INVALID_JSON")
        return LLMResult(raw=raw, parsed=parsed)

    async def _stream(self, payload: dict[str, Any]) -> str:
        """The final answer text, joined from the server-sent events. Reasoning pieces
        (`reasoning_content`) are never read."""
        parts: list[str] = []
        size = 0
        url = f"{self.base_url}/v1/chat/completions"
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers=auth_headers(self.api_key)
        ) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 404:
                    raise LLMConfigurationError("LLM_MODEL_NOT_FOUND")
                if response.status_code >= 400:
                    raise LLMUnavailable("LLM_HTTP_ERROR")
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        piece = json.loads(data)
                        if "error" in piece:  # a failure reported in the middle of the stream
                            raise LLMUnavailable("LLM_STREAM_ERROR")
                        choices = piece.get("choices") or []
                        choice = choices[0] if choices else {}
                        text = (choice.get("delta") or {}).get("content")
                    except (ValueError, KeyError, TypeError, AttributeError) as error:
                        raise LLMInvalidOutput("LLM_INVALID_RESPONSE") from error
                    if text:
                        size += len(text)
                        if size > MAX_OUTPUT_CHARS:
                            raise LLMInvalidOutput("LLM_OUTPUT_TOO_LARGE")
                        parts.append(str(text))
                    if choice.get("finish_reason") == "length":
                        # The output limit was reached before the JSON was closed.
                        raise LLMInvalidOutput("LLM_OUTPUT_TRUNCATED")
        return "".join(parts)


def parse_output(content: str) -> LLMResult:
    raw = strip_reasoning(content)
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise LLMInvalidOutput("LLM_INVALID_JSON") from error
    if not isinstance(parsed, dict):
        raise LLMInvalidOutput("LLM_INVALID_JSON")
    return LLMResult(raw=raw, parsed=parsed)


async def sse_data(response: httpx.Response):
    """The `data:` payloads of a server-sent-events answer, as parsed JSON."""
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return
        try:
            piece = json.loads(data)
        except ValueError as error:
            raise LLMInvalidOutput("LLM_INVALID_RESPONSE") from error
        if not isinstance(piece, dict):
            raise LLMInvalidOutput("LLM_INVALID_RESPONSE")
        yield piece


class AnthropicProvider:
    """Claude through the Messages API. The schema goes in `output_config.format`, the key in
    `x-api-key`. The model name is the Claude model id."""

    name = "anthropic"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        max_output_tokens: int | None = None,
        api_key: str = "",
    ) -> None:
        if not model:
            raise LLMConfigurationError("LLM_NOT_CONFIGURED")
        if not api_key:
            raise LLMConfigurationError("LLM_API_KEY_MISSING")
        self.api_key = api_key
        self.base_url = openai_root(base_url)
        self.model = model
        self.timeout = timeout_seconds
        self.transport = transport
        self.max_output_tokens = max_output_tokens

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, context_tokens: int
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens or 16384,  # required by this API
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
            "temperature": 0,
            "stream": True,
        }
        try:
            async with asyncio.timeout(self.timeout):
                content = await self._stream(payload)
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as error:
            raise LLMUnavailable("LLM_UNAVAILABLE") from error
        return parse_output(content)

    async def _stream(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        size = 0
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers=anthropic_headers(self.api_key)
        ) as client:
            async with client.stream(
                "POST", f"{self.base_url}/v1/messages", json=payload
            ) as response:
                if response.status_code == 404:
                    raise LLMConfigurationError("LLM_MODEL_NOT_FOUND")
                if response.status_code >= 400:
                    raise LLMUnavailable("LLM_HTTP_ERROR")
                async for piece in sse_data(response):
                    kind = piece.get("type")
                    if kind == "error":
                        raise LLMUnavailable("LLM_STREAM_ERROR")
                    if kind == "content_block_delta":
                        delta = piece.get("delta") or {}
                        text = delta.get("text") if delta.get("type") == "text_delta" else None
                        if text:
                            size += len(text)
                            if size > MAX_OUTPUT_CHARS:
                                raise LLMInvalidOutput("LLM_OUTPUT_TOO_LARGE")
                            parts.append(str(text))
                    elif kind == "message_delta":
                        if (piece.get("delta") or {}).get("stop_reason") == "max_tokens":
                            raise LLMInvalidOutput("LLM_OUTPUT_TRUNCATED")
        return "".join(parts)


class GeminiProvider:
    """Google Gemini through `streamGenerateContent`. The schema goes in
    `generationConfig.responseJsonSchema`, the key in `x-goog-api-key`. Thought parts are
    skipped."""

    name = "gemini"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        max_output_tokens: int | None = None,
        api_key: str = "",
    ) -> None:
        if not model:
            raise LLMConfigurationError("LLM_NOT_CONFIGURED")
        if not api_key:
            raise LLMConfigurationError("LLM_API_KEY_MISSING")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.transport = transport
        self.max_output_tokens = max_output_tokens

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], *, context_tokens: int
    ) -> LLMResult:
        config: dict[str, Any] = {
            "temperature": 0,
            "seed": 7,
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
        }
        if self.max_output_tokens:
            config["maxOutputTokens"] = self.max_output_tokens
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": config,
        }
        try:
            async with asyncio.timeout(self.timeout):
                content = await self._stream(payload)
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as error:
            raise LLMUnavailable("LLM_UNAVAILABLE") from error
        return parse_output(content)

    async def _stream(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        size = 0
        model = urllib.parse.quote(self.model.removeprefix("models/"), safe="")
        url = f"{self.base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse"
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers=gemini_headers(self.api_key)
        ) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 404:
                    raise LLMConfigurationError("LLM_MODEL_NOT_FOUND")
                if response.status_code >= 400:
                    raise LLMUnavailable("LLM_HTTP_ERROR")
                async for piece in sse_data(response):
                    if "error" in piece:
                        raise LLMUnavailable("LLM_STREAM_ERROR")
                    try:
                        candidate = (piece.get("candidates") or [{}])[0]
                        for part in (candidate.get("content") or {}).get("parts") or []:
                            text = part.get("text")
                            if text and not part.get("thought"):
                                size += len(text)
                                if size > MAX_OUTPUT_CHARS:
                                    raise LLMInvalidOutput("LLM_OUTPUT_TOO_LARGE")
                                parts.append(str(text))
                    except (KeyError, TypeError, AttributeError, IndexError) as error:
                        raise LLMInvalidOutput("LLM_INVALID_RESPONSE") from error
                    if candidate.get("finishReason") == "MAX_TOKENS":
                        raise LLMInvalidOutput("LLM_OUTPUT_TRUNCATED")
        return "".join(parts)


PROVIDERS: dict[str, type] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def provider_for(
    name: str,
    base_url: str,
    model: str,
    timeout_seconds: float,
    max_output_tokens: int | None = None,
    api_key: str = "",
) -> LLMProvider:
    """The provider a job names. Jobs keep the provider they were created with, so changing
    the setting never changes a job that is already queued."""
    cls = PROVIDERS.get(name)
    if cls is None:
        raise LLMConfigurationError("UNKNOWN_LLM_PROVIDER")
    return cls(
        base_url, model, timeout_seconds, max_output_tokens=max_output_tokens, api_key=api_key
    )


def build_provider(
    runtime: RuntimeSettings, timeout_seconds: float, max_output_tokens: int | None = None
) -> LLMProvider:
    return provider_for(
        runtime.llm_provider,
        runtime.llm_base_url,
        runtime.llm_model,
        timeout_seconds,
        max_output_tokens,
        runtime.llm_api_key,
    )


async def list_models(
    provider: str,
    base_url: str,
    timeout_seconds: float = 10,
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str = "",
) -> list[str]:
    if provider == "openai":
        return await list_openai_models(base_url, timeout_seconds, transport, api_key)
    if provider == "ollama":
        return await list_ollama_models(base_url, timeout_seconds, transport, api_key)
    if provider == "anthropic":
        return await list_anthropic_models(base_url, timeout_seconds, transport, api_key)
    if provider == "gemini":
        return await list_gemini_models(base_url, timeout_seconds, transport, api_key)
    raise LLMConfigurationError("UNKNOWN_LLM_PROVIDER")


async def list_openai_models(
    base_url: str,
    timeout_seconds: float = 10,
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str = "",
) -> list[str]:
    """Read-only model discovery through `/v1/models`; no meeting data is sent."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, transport=transport, headers=auth_headers(api_key)
        ) as client:
            response = await client.get(f"{openai_root(base_url)}/v1/models")
    except (httpx.TimeoutException, httpx.TransportError) as error:
        raise LLMUnavailable("OPENAI_UNREACHABLE") from error
    if response.status_code >= 400:
        raise LLMUnavailable("OPENAI_HTTP_ERROR")
    try:
        return sorted(str(model["id"]) for model in response.json()["data"])
    except (ValueError, KeyError, TypeError) as error:
        raise LLMInvalidOutput("OPENAI_INVALID_RESPONSE") from error


async def list_ollama_models(
    base_url: str,
    timeout_seconds: float = 10,
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str = "",
) -> list[str]:
    """Read-only model discovery through `/api/tags`; no meeting data is sent."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, transport=transport, headers=auth_headers(api_key)
        ) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/tags")
    except (httpx.TimeoutException, httpx.TransportError) as error:
        raise LLMUnavailable("OLLAMA_UNREACHABLE") from error
    if response.status_code >= 400:
        raise LLMUnavailable("OLLAMA_HTTP_ERROR")
    try:
        models = response.json()["models"]
        return sorted(str(model["name"]) for model in models)
    except (ValueError, KeyError, TypeError) as error:
        raise LLMInvalidOutput("OLLAMA_INVALID_RESPONSE") from error


async def list_anthropic_models(
    base_url: str,
    timeout_seconds: float = 10,
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str = "",
) -> list[str]:
    """Read-only model discovery through `/v1/models`; no meeting data is sent."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, transport=transport, headers=anthropic_headers(api_key)
        ) as client:
            response = await client.get(
                f"{openai_root(base_url)}/v1/models", params={"limit": 1000}
            )
    except (httpx.TimeoutException, httpx.TransportError) as error:
        raise LLMUnavailable("ANTHROPIC_UNREACHABLE") from error
    if response.status_code >= 400:
        raise LLMUnavailable("ANTHROPIC_HTTP_ERROR")
    try:
        return sorted(str(model["id"]) for model in response.json()["data"])
    except (ValueError, KeyError, TypeError) as error:
        raise LLMInvalidOutput("ANTHROPIC_INVALID_RESPONSE") from error


async def list_gemini_models(
    base_url: str,
    timeout_seconds: float = 10,
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str = "",
) -> list[str]:
    """Read-only model discovery through `/v1beta/models`: the ones that can generate text."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, transport=transport, headers=gemini_headers(api_key)
        ) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/v1beta/models", params={"pageSize": 1000}
            )
    except (httpx.TimeoutException, httpx.TransportError) as error:
        raise LLMUnavailable("GEMINI_UNREACHABLE") from error
    if response.status_code >= 400:
        raise LLMUnavailable("GEMINI_HTTP_ERROR")
    try:
        return sorted(
            str(model["name"]).removeprefix("models/")
            for model in response.json()["models"]
            if "generateContent" in model.get("supportedGenerationMethods", [])
        )
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise LLMInvalidOutput("GEMINI_INVALID_RESPONSE") from error
