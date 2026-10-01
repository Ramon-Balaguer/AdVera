# Feature: Rebuild streamed LLM answers
Status: complete
Last updated: 2026-10-01

## Objective

Let long Brain extractions finish behind a reverse proxy that closes silent connections. The operator's proxy in front of Ollama answers 504 after about 90 s without data, so the long meeting "guillem 2" failed three times with `LLM_HTTP_ERROR`, while AdVera itself waits up to `llm_timeout_seconds` (900 s).

## Scope

In scope: the Ollama provider (`backend/app/llm.py`) requests `stream: true` and joins the streamed answer; the overall limit stays `llm_timeout_seconds`; a failure reported mid-stream is retryable (`LLM_STREAM_ERROR`); the joined answer is bounded (`LLM_OUTPUT_TOO_LARGE`). Reasoning pieces (`thinking`) are never read, as before (spec §3.4).

Out of scope: showing partial output, changing the operator's proxy.

## Acceptance criteria

1. A streamed answer is joined into the same result as before, without reasoning.
2. An error line in the stream fails the call as retryable.
3. The overall time limit still applies while pieces keep arriving.
4. "guillem 2" is extracted through the operator's proxy.

## Implementation state

Implemented and unit-tested. Real run: a Brain job of 93 s completed through the operator's proxy, and "guillem 2" was extracted (prompt v4).

Context size (2026-10-01): the 73-minute podcast "Podcast urisabat cuanto fractur" failed with `LLM_OUTPUT_TRUNCATED`. The operator's Ollama log showed a 56,355-token prompt in a 65,536-token context: the answer used the 9,181 tokens left and was cut before the JSON closed. `llm_context_tokens` (`LLM_CONTEXT_TOKENS`, sent as `num_ctx`) is now 131,072; the model supports 262,144. The token estimate used to refuse prompts that cannot fit is now about 2.3 characters per token (3 underestimated this prompt by a fifth).

## Decisions

Streaming is used for every call (Brain and Memory answers): it keeps the same result and removes the dependency on the proxy's read timeout.

## Files changed

- `backend/app/llm.py`, `backend/tests/test_llm_settings.py`

## Validation

- Unit (mocked HTTP): pieces joined and reasoning ignored, mid-stream error, overall time limit, existing failure classification (404, 500, invalid JSON) still holds.

## Risks

- If the proxy also limits the total duration of a request, streaming does not help.

## Next action

None.
