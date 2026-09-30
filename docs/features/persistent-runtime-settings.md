# Feature: Persistent runtime settings
Status: complete
Last updated: 2026-09-21

## Product Owner discovery brief

Problem: Runtime settings edited in AdVera are lost when the backend restarts, while the operator expects the configured runtime to remain stable.

Target user: The self-hosted AdVera operator managing the local AI runtime.

Desired outcome: All settings exposed by the AdVera Settings screen remain configured after backend restarts.

Smallest useful increment: Persist Ollama URL, Ollama model, metrics refresh interval and Hugging Face token in the existing local settings file and restore them on reads and ASR startup.

In scope / Out of scope: In scope are the `/api/settings` contract, Settings UI behavior, local settings file and Docker persistence. Out of scope are deployment-only environment settings such as database URL, Redis URL, GPU device and storage paths, which remain environment-managed infrastructure configuration.

User acceptance criteria:

- Saving any Settings screen value persists it across a backend restart.
- The Hugging Face token remains hidden from API responses and logs.
- Clearing the Hugging Face token is persistent.
- Existing environment values remain defaults when no persisted value exists.

States and failure behavior: Missing settings file uses environment/default values. Invalid or unreadable persisted settings fall back safely to environment/default values. An unwritable settings directory returns a clear API error.

Data and provenance constraints: The settings file may contain a secret token and must stay outside version control, use restrictive file permissions where supported, and never be returned in API responses.

Dependencies and constraints: Docker must persist the settings directory. The existing single-operator local file store remains the MVP secret/configuration store.

Assumptions: One self-hosted installation has one active runtime configuration.

Open questions: Multi-user deployments may require a database-backed settings model and an external secret manager.

Recommended next agent: Backend, Frontend, Operations, then QA and Security.

## Objective

Persist all user-editable runtime settings and restore them after backend restarts.

## Scope

- Persist Ollama URL, Ollama model, metrics refresh interval and Hugging Face token together.
- Keep environment configuration as fallback.
- Preserve the secret handling rules for the Hugging Face token.
- Keep deployment-only settings environment-managed.

## Acceptance criteria

- The four Settings screen values survive a process restart when the settings path remains available.
- The Settings screen restores the persisted Ollama URL and model and can rediscover installed models.
- GET `/api/settings` returns persisted non-secret values and only a configured flag for the token.
- Docker persists the settings path.

## Implementation state

Implemented. The existing local settings file now stores all four user-editable runtime settings and the API restores them when the runtime state is empty after a restart.

## Decisions

- Extend the existing local JSON settings file rather than introduce a new database table for this single-operator runtime configuration.
- Persist only settings already exposed as user-editable runtime settings.
- Environment variables remain the fallback and deployment contract for infrastructure settings.

## Files changed

- `backend/app/settings.py`
- `backend/tests/integration/test_settings_api.py`
- `docs/features/persistent-runtime-settings.md`

## Validation

- `backend/tests/integration/test_settings_api.py` and `backend/tests/test_backend_services.py`: 33 passed.
- `frontend`: `npm run build` passed.
- Ollama model discovery and selection E2E test passed.
- Settings persistence E2E test passed: saved URL, model, metrics interval and token state were restored after a page reload.
- Backend persistence and source diagnostics passed; Ruff reports only the pre-existing `FakeResponse.__enter__` fixture warning.

## Risks and next action

The local settings file must remain on persistent storage and receive a security review because it contains the Hugging Face token. Docker Compose mounts `/data/config`, and `data/config/.gitkeep` ensures the bind-mount source exists in a clean checkout; deployment-only settings remain environment-managed by design. The existing metrics E2E tests still expect the removed HTTP polling path and need separate maintenance.
