# ADR 0023: The LLM provider is selectable: Ollama or an OpenAI-compatible server

## Status

Accepted (2026-10-04), by the operator.

## Context

AdVera could only talk to Ollama. The operator has a llama-swap server (llama.cpp behind a model switcher) that speaks the OpenAI protocol (`/v1/models`, `/v1/chat/completions`) and none of Ollama's (`/api/tags`, `/api/chat`), so Settings could not check it and no job could use it. The specification already foresaw an `OpenAICompatibleProvider` next to `OllamaProvider`.

## Decision

- Settings has a **provider**: `ollama` or `openai` (shown as "OpenAI-compatible"). Both are `LLMProvider`s with the same contract and the same errors, so the Summary and Brain workers do not change.
- `OpenAIProvider` calls `POST {server}/v1/chat/completions`, streamed (server-sent events), with the JSON schema in `response_format` (llama.cpp turns it into a grammar, so the size limits of the schema still hold), `temperature: 0`, `seed: 7`, `max_tokens` and `chat_template_kwargs.enable_thinking: false`. Reasoning pieces are never read or stored. A `finish_reason` of `length` is `LLM_OUTPUT_TRUNCATED`. The context size is not sent: in this protocol the server decides it.
- Model discovery goes through the chosen provider (`POST /api/settings/models` with `{provider, base_url}`; `/v1/models` for OpenAI). The server address may be typed with or without `/v1`. Discovery errors have their own codes (`OPENAI_UNREACHABLE`, `OPENAI_HTTP_ERROR`, `OPENAI_INVALID_RESPONSE`).
- A job keeps the provider, address and model it was created with (as before), and the workers choose the provider by that stored name, so changing the setting never changes a job already queued. No migration: the provider is already text in the jobs and in `llm_runs`.
- One model for everything (summaries and searches) for now. Choosing a model per task is not part of this decision.
- No API key: Settings stores no secrets (ADR 0009), and the target servers (local llama.cpp, llama-swap, vLLM) do not need one.

## Consequences

- Servers such as llama-swap can be used; the same prompts, schemas and validation apply to both providers.
- A hosted OpenAI-style service may reject non-standard fields (`seed`, `chat_template_kwargs`) or need an API key; those are not supported targets.
- `POST /api/settings/ollama/models` is replaced by `POST /api/settings/models`.
- The long-context choice (for example a "rag" model for transcripts over about 15k tokens) is the operator's, made in Settings.

## Validation and rollback

Tests use an in-process transport (stream, truncation, invalid output, errors, time limit, request contents) and the settings API; one real call to the operator's server returned a valid answer under the schema. Rollback: set the provider back to Ollama; no data changes.

## Related records

- [Rebuild LLM providers](../features/rebuild-llm-providers.md)
- [ADR 0009: Summary output language provenance](0009-summary-output-language-provenance.md)
