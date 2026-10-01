"""LLM provider boundary (spec §3.5, §5 LLM; ADR 0009).

LLMProvider
  -> OllamaProvider   /api/chat with a JSON schema, deterministic options, thinking disabled

The answer is streamed (one JSON line per piece) and joined here. A long extraction can take
minutes, and a reverse proxy in front of Ollama cuts a connection that stays silent for its
read timeout (one operator's cut at about 90 s with 504); streamed pieces keep it alive. The
overall time limit is still `timeout_seconds`.

Only the model's final structured output is kept. Thinking is disabled at the request level
and any reasoning block that still appears is stripped before parsing: chain-of-thought is
never stored (spec §3.4). Prompts and outputs are never logged.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.runtime_settings import RuntimeSettings

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
            "stream": True,
            "think": False,
            "options": {"temperature": 0, "seed": 7, "num_ctx": context_tokens},
        }
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
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
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
