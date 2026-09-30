# Feature: Persistent Hugging Face token settings
Status: complete
Last updated: 2026-09-20

## Product Owner discovery brief

Problem: Users can configure GPU transcription, but the Hugging Face token currently depends on environment configuration and cannot be entered or retained from AdVera settings.

Target user: The self-hosted AdVera operator who enables WhisperX and Pyannote model downloads.

Desired outcome: An operator can save a Hugging Face token once in Settings and have it available after backend restarts for authenticated model downloads.

Smallest useful increment: Add a persistent token setting, expose only whether it is configured, and use it for WhisperX and Pyannote model downloads.

In scope / Out of scope: In scope are the backend settings API, local persistent secret file, Settings UI, Docker persistence, and ASR model download authentication. Out of scope are multi-user secret management, cloud secret managers, token validation against Hugging Face, and token rotation workflows.

User acceptance criteria:

- The operator can enter and save a Hugging Face token from Settings.
- The token remains available after restarting the backend when the persistent settings path is retained.
- API responses never return the token value; they only report whether one is configured.
- WhisperX and Pyannote receive the configured token before downloading models.
- Existing `HF_TOKEN` environment configuration remains a compatible fallback.

States and failure behavior: Empty input leaves the configured token unchanged; an explicit clear action removes it. Invalid or unwritable persistent storage returns a clear settings error. Missing token leaves existing no-token ASR behavior unchanged.

Data and provenance constraints: The token is a secret and must not be logged, returned by API responses, committed, or included in tests. It is stored in a local file with restrictive permissions. Meeting audio and transcript data are not changed.

Dependencies and constraints: The deployment must persist the settings directory. Docker Compose must mount it separately from meeting data. The ASR provider must remain compatible with environment-based Hugging Face configuration.

Assumptions: A single self-hosted operator uses the installation. The local filesystem is the initial secret store.

Open questions: A future multi-user deployment should move this secret to an OS secret manager or deployment secret store.

Recommended next agent: Backend, Frontend, Operations, then QA and Security.

## Objective

Persist the Hugging Face token configured in AdVera Settings and use it for authenticated WhisperX and Pyannote model downloads.

## Scope

- Add a persistent local settings store for the Hugging Face token.
- Keep the token out of API responses and logs.
- Add Settings UI input and configured-state feedback.
- Preserve `HF_TOKEN` as an environment fallback.
- Persist the settings directory in Docker Compose.

## Acceptance criteria

- Saving a token survives backend restart when the settings volume remains.
- Clearing the token removes the persisted value.
- WhisperX model loading receives Hugging Face authentication through the supported hub environment variables.
- Pyannote diarization receives the same token explicitly.
- Focused backend and frontend checks pass.

## Implementation state

Implemented. The Settings API persists the token in the configured local JSON secret file, the frontend never receives the value, and ASR provider creation reads the persisted token before model loading.

## Decisions

- Use a configurable local JSON secret file for the single-user self-hosted MVP.
- Prefer the persisted token over `HF_TOKEN` when configured.
- Return only `hf_token_configured`, never the secret itself.

## Files changed

- `.env.example`
- `backend/app/asr.py`
- `backend/app/audio.py`
- `backend/app/config.py`
- `backend/app/settings.py`
- `backend/tests/integration/test_settings_api.py`
- `backend/tests/test_backend_services.py`
- `docker/compose.dev.yml`
- `frontend/src/App.tsx`

## Validation

- `backend/tests/integration/test_settings_api.py` and `backend/tests/test_backend_services.py`: 33 passed.
- `frontend`: `npm run build` passed.
- VS Code diagnostics reported no errors in the modified backend and frontend source files.
- Ruff still reports pre-existing issues in `backend/app/audio.py` and an existing fixture warning; no new source error was introduced by this feature.

## Risks and next action

The local file must be placed on persistent storage and protected by filesystem permissions. Docker Compose mounts `/data/config` for this purpose. A future multi-user deployment should move this secret to an OS secret manager or deployment secret store.
