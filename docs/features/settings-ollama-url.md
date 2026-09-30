# Feature: Configuracion de Ollama
Status: complete
Last updated: 2026-09-19

## Objective

Provide an initial settings page where a local AdVera administrator can view and update the Ollama base URL used by the backend.

## Scope

- Enable the Ajustes navigation item.
- Add a frontend settings view with the Ollama URL field.
- Add GET and PUT API endpoints for the setting.
- Validate HTTP and HTTPS URLs and expose loading, saving, success, and error states.
- Keep the first increment in memory; environment configuration remains the startup default.

## Acceptance criteria

- Ajustes opens from the main navigation.
- The current Ollama URL is loaded from the API and defaults to `http://localhost:11434`.
- A valid HTTP or HTTPS URL can be saved and is returned by the API afterward.
- Invalid URLs are rejected without replacing the current value.
- The save action communicates success or failure and prevents duplicate submission.

## Implementation state

Product Owner discovery brief recorded. Implementation in progress.

## Decisions

- Use the existing FastAPI and React patterns.
- Store the runtime override in memory for this first increment; persistent installation-level storage is a follow-up decision.
- Do not support credentials or connection testing yet.

## Files changed

- `backend/app/settings.py`
- `backend/app/main.py`
- `backend/app/audio.py`
- `backend/tests/test_settings.py`
- `backend/tests/integration/test_settings_api.py`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/tests/e2e/settings.spec.ts`

## Validation

Backend focused and integration tests pass. Frontend diagnostics report no errors; npm/Node is not available in the current terminal, so the frontend build and Playwright test could not be executed here.

## Risks and next action

The runtime override resets when the backend restarts. Next action: decide whether installation-level persistence belongs in the database or deployment configuration, and run the frontend build plus Playwright check in a Node-enabled environment.
