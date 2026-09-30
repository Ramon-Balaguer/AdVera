# Feature: Ollama model auto-discovery on settings load
Status: complete
Last updated: 2026-09-21

## Product Owner discovery brief

Problem: The Settings page restores the saved Ollama URL and model, but users must manually request the model list each time they open the page.

Target user: AdVera operators using Ollama for runtime summaries.

Desired outcome: When a saved Ollama URL exists, Settings loads its available models automatically and restores the saved model selection when it is available.

Smallest useful increment: Trigger the existing model discovery request after settings load and cover the behavior with a focused E2E test.

In scope / Out of scope: In scope are automatic discovery on Settings load, loading/error states already supported by the UI, and restoration of the saved model. Out of scope are URL discovery, model installation, and provider changes.

User acceptance criteria:

- A saved Ollama URL triggers model discovery when Settings opens.
- The saved model remains selected when it is returned by Ollama.
- Discovery errors remain non-blocking and do not overwrite saved settings.
- The user can still retry manually with the existing action.

States and failure behavior: No saved URL leaves discovery idle. Discovery shows its existing loading, ready, empty, or error state. A failed request leaves the saved URL and model intact.

Data and provenance constraints: The model list is derived from the current Ollama response and is not persisted until the user saves a selection. No secrets or meeting content are logged.

Dependencies and constraints: Reuse the existing `/api/settings/ollama/models` endpoint and current React settings state.

Assumptions: The saved URL is reachable from the backend and the saved model is identified by its stable Ollama name.

Open questions: None for this increment.

Recommended next agent: Frontend, followed by QA validation.

## Objective

Automatically discover Ollama models when the Settings page loads with a configured URL.

## Scope

- Trigger the existing discovery request after `/api/settings` has loaded.
- Preserve the previously saved model when it is present in the discovered list.
- Add focused E2E coverage for automatic discovery and selection.

## Acceptance criteria

- Opening Settings with a saved Ollama URL requests `/api/settings/ollama/models` without a button click.
- The saved model is selected when the response contains it.
- Existing manual discovery remains available.

## Implementation state

Implemented. Settings now starts the existing Ollama model discovery after persisted settings finish loading.

## Decisions

- Reuse the existing backend proxy and model discovery function rather than adding a second API path.
- Start discovery only after settings have loaded, so the request uses the persisted URL.

## Files changed

- `frontend/src/App.tsx`
- `frontend/tests/e2e/settings.spec.ts`
- `docs/features/ollama-settings-auto-discovery.md`

## Validation

Focused frontend E2E validation passes.

## Risks and next action

The Ollama endpoint may be unavailable when Settings opens; the existing error state and manual retry action remain usable. Next action: monitor the behavior against remote Ollama endpoints.
