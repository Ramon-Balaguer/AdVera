"""LLM provider boundary (spec §3.5, §5 LLM; ADR 0009).

LLMProvider
  -> OllamaProvider   /api/chat with a JSON schema, deterministic options, thinking disabled

Only the model's final structured output is kept. Thinking is disabled at the request level
and any reasoning block that still appears is stripped before parsing: chain-of-thought is
never stored (spec §3.4). Prompts and outputs are never logged.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.runtime_settings import RuntimeSettings

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
    # Conservative for ca/es/en text: about 3 characters per token.
    return len(text) // 3 + 1


def strip_reasoning(text: str) -> str:
    return THINK_BLOCK.sub("", text).strip()


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not model:
            raise LLMConfigurationError("LLM_NOT_CONFIGURED")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.transport = transport

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
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "seed": 7, "num_ctx": context_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise LLMUnavailable("LLM_UNAVAILABLE") from error
        if response.status_code == 404:
            raise LLMConfigurationError("LLM_MODEL_NOT_FOUND")
        if response.status_code >= 400:
            raise LLMUnavailable("LLM_HTTP_ERROR")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as error:
            raise LLMInvalidOutput("LLM_INVALID_RESPONSE") from error
        raw = strip_reasoning(str(content))
        try:
            parsed = json.loads(raw)
        except ValueError as error:
            raise LLMInvalidOutput("LLM_INVALID_JSON") from error
        if not isinstance(parsed, dict):
            raise LLMInvalidOutput("LLM_INVALID_JSON")
        return LLMResult(raw=raw, parsed=parsed)


def build_provider(runtime: RuntimeSettings, timeout_seconds: float) -> LLMProvider:
    if runtime.llm_provider == "ollama":
        return OllamaProvider(runtime.llm_base_url, runtime.llm_model, timeout_seconds)
    raise LLMConfigurationError("UNKNOWN_LLM_PROVIDER")


async def list_ollama_models(
    base_url: str,
    timeout_seconds: float = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """Read-only model discovery through `/api/tags`; no meeting data is sent."""
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, transport=transport) as client:
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
