# Live summary observability
Status: complete
Last updated: 2026-09-19

## Objective
Make Ollama live-summary failures diagnosable from the API console while preserving the recoverable error shown in the UI.

## Scope
- Log live-summary request, response validation, success, and failure milestones.
- Log state transitions emitted by the audio WebSocket.
- Include safe operational metadata without prompts, transcript text, or secrets.
- Add regression coverage for incomplete Ollama output logging.

## Acceptance criteria
- An incomplete Ollama response logs the meeting, model, response keys, and validation reason.
- Live summary state changes are visible as `generating`, `available`, or `error` transitions.
- The browser continues to show `ERROR RECUPERABLE` for recoverable failures.
- Logs do not contain the prompt or transcript contents.

## Implementation state
Implemented. The API now logs safe lifecycle metadata for requests, responses, validation failures, successful summaries, and emitted state transitions. Validation distinguishes missing/unexpected keys from invalid JSON value types, including a non-string `summary`.

## Decisions
- Use Python module loggers so Docker/Uvicorn forwards messages to the API console.
- Use `INFO` for lifecycle and state transitions, `WARNING` for invalid model output, and `EXCEPTION` for transport or unexpected failures.
- Log response shape metadata only, not response content.

## Files changed
- `backend/app/live_summary.py`
- `backend/app/audio.py`
- `backend/tests/test_live_summary.py`
- `docs/features/live-summary-observability.md`

## Validation
- Focused tests: `5 passed`.
- `compileall` passed for the provider, audio WebSocket, and focused tests.
- Workspace diagnostics report no errors in changed code.

## Risks
The model can still return a syntactically valid but semantically poor summary; these logs diagnose contract failures, not summary quality. A response with the expected keys but a non-string `summary` is reported as `invalid_summary_type`.

## Next action
Inspect the API container console during the next live-summary request and use the `received_keys` field to diagnose any Ollama schema mismatch.
