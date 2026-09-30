# Feature: Hugging Face token usage and download logs
Status: complete
Last updated: 2026-09-21

## Product Owner discovery brief

Problem: The definitive ASR flow can use only the environment token instead of the token persisted in Settings, and model load/download activity is not visible in API logs.

Target user: AdVera operators diagnosing ASR model setup and downloads.

Desired outcome: All ASR flows use the persisted Hugging Face token and logs show model load/download lifecycle without exposing the token.

Smallest useful increment: Resolve the persisted token in the definitive flow and instrument WhisperX model, alignment, and diarization loads with redacted lifecycle logs.

In scope / Out of scope: In scope are token resolution, safe start/success/failure logs, and regression tests. Out of scope are ASR provider migration and changes to the Settings API contract.

User acceptance criteria:

- Persisted HF token is passed to every ASR provider creation path.
- Logs identify model load/download start, success, or failure and include model/stage metadata.
- The token is never present in logs, including failure messages.
- Existing ASR behavior remains unchanged apart from logging and token source consistency.

States and failure behavior: Missing token is represented only by `token_configured=false`. Load failures log stage, model, error type, sanitized error and duration, then re-raise the original failure.

Data and provenance constraints: Never log the token, its headers, or meeting/audio content. Model identifiers and durations are operational metadata.

Dependencies and constraints: Reuse the existing persisted settings reader and WhisperX loading points.

Assumptions: Hugging Face and WhisperX may include the token in dependency errors, so errors must be sanitized before logging.

Open questions: None for this increment.

Recommended next agent: Backend, followed by QA and Security.

## Objective

Use the persisted Hugging Face token consistently and make model download activity observable without leaking secrets.

## Scope

- Use `current_hf_token()` for definitive ASR provider creation.
- Log lifecycle events for WhisperX, alignment, and diarization model loads.
- Redact the token from logged error messages.
- Add focused regression tests.

## Acceptance criteria

- Both live and definitive ASR provider creation receive the persisted token.
- Successful and failed model loads produce safe logs.
- Tests prove the token value is absent from logs.

## Implementation state

Implemented. Live and definitive ASR provider creation now resolve the persisted token, and WhisperX model, alignment, and diarization loads emit redacted lifecycle logs.

## Decisions

- Log model load/download lifecycle because the dependency does not expose a stable download callback; cached loads use the same operational lifecycle.
- Log only `token_configured`, never token content.
- Re-raise load failures after logging so existing error handling remains intact.

## Files changed

- `backend/app/asr.py`
- `backend/app/audio.py`
- `backend/tests/test_asr.py`
- `backend/tests/test_backend_services.py`
- `docs/features/huggingface-download-logging.md`

## Validation

Focused backend tests pass (`37 passed`).

## Risks and next action

Third-party exceptions may contain credential material; the logging helper redacts the configured token and avoids traceback logging for model load failures. Next action: include the new lifecycle events in API log monitoring.
