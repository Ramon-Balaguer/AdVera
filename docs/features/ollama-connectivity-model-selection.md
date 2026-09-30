# Feature: Conectividad y seleccion de modelos Ollama
Status: complete
Last updated: 2026-09-19

## Objective

Allow an AdVera administrator to verify the configured Ollama endpoint, load its available models, and choose the model used by live summaries.

## Scope

- Add a connectivity and model discovery action beside the Ollama URL.
- Proxy Ollama `/api/tags` through the backend.
- Extend runtime settings with the selected Ollama model.
- Populate a model selector from names returned by Ollama.
- Show loading, success, empty, and failure states.

## Acceptance criteria

- The user can press a button beside the URL to check connectivity.
- A successful response populates a model selector using the returned model names.
- The selected model is returned by and saved through `/api/settings`.
- The live summary provider uses the saved model.
- Network errors, invalid responses, and an empty model list are visible without losing the URL or selected model.

## Implementation state

Product Owner discovery brief recorded. Implementation complete.

## Decisions

- The backend performs the Ollama request so the browser does not need direct access or CORS support.
- Only model names are exposed to the UI; model metadata is not persisted.
- Connectivity checks use Ollama's read-only `/api/tags` endpoint and do not send meeting data.

## Files changed

- `backend/app/settings.py`
- `backend/app/audio.py`
- `backend/app/config.py`
- `backend/tests/test_settings.py`
- `backend/tests/integration/test_settings_api.py`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/tests/e2e/settings.spec.ts`

## Validation

Focused backend tests pass (`7 passed`) and frontend diagnostics report no errors. The API integration test was added but could not run in the current environment because the active interpreter is missing `psutil`; the repository `.venv` does not have pytest installed.

## Risks and next action

The runtime settings remain in memory and reset on backend restart. Next action: decide whether settings persistence and authentication for remote Ollama servers are needed.
