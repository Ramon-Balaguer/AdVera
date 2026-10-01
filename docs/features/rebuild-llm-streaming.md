# Feature: Rebuild streamed LLM answers
Status: in progress
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

Implemented and unit-tested; the real check on "guillem 2" is pending.

## Decisions

Streaming is used for every call (Brain and Memory answers): it keeps the same result and removes the dependency on the proxy's read timeout.

## Files changed

- `backend/app/llm.py`, `backend/tests/test_llm_settings.py`

## Validation

- Unit (mocked HTTP): pieces joined and reasoning ignored, mid-stream error, overall time limit, existing failure classification (404, 500, invalid JSON) still holds.

## Risks

- If the proxy also limits the total duration of a request, streaming does not help.

## Next action

Redeploy and extract "guillem 2" again.
