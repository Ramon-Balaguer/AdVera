# Feature: Rebuild settings page and LLM provider
Status: partial
Last updated: 2026-09-30

## Objective

Let the operator choose the Ollama server, the model and the Brain output language from a Settings page instead of environment variables, and provide the `LLMProvider` boundary used by the Brain and Memory (spec §5 LLM, §3.5; ADR 0009).

## Scope

In scope:
- Persistent runtime settings in one local JSON file shared by the API and the workers (`RUNTIME_SETTINGS_PATH`, the `app-config` volume). Environment variables supply the defaults.
- `GET` and `PUT /api/settings`, and `POST /api/settings/ollama/models`, which does read-only discovery through `/api/tags` (spec §20).
- A Settings page:
  - server URL, a "Comprobar" button, and model auto-discovery on load (`ollama-settings-auto-discovery.md`);
  - a model selector and the Brain output language, `es` or `en` (ADR 0009);
  - a visible notice that transcript content is sent to that server (spec §29).
- `OllamaProvider`:
  - `/api/chat` with a JSON schema, `temperature 0`, a fixed seed and an explicit `num_ctx`;
  - `think: false`, and any reasoning block that still appears is stripped before parsing (spec §3.4: no chain-of-thought is stored);
  - classified failures: configuration (terminal), unavailable and invalid output (retryable).

Out of scope: other LLM providers, secrets or API keys, and UI localization beyond the Settings page.

## Acceptance criteria

1. Settings survive an API restart and are read by every worker.
2. An invalid URL or language returns 422 and never overwrites the stored settings.
3. "Comprobar" lists the server's models; an unreachable server shows an error and keeps the form.
4. The provider never asks for thinking, and never keeps reasoning text in the stored output.

## Implementation state

Implemented. Product owner decisions (2026-09-30):
- Ollama runs on the operator's own server, reachable over HTTPS; its address lives only in the runtime settings file.
- The model is `ornith-1.5:35b`.
- URL and model are chosen on a Settings page.

The server's address is stored only in the local runtime settings file, never in the repository.

## Decisions

- Runtime settings override environment defaults field by field. A corrupt file falls back to the defaults.
- URLs with credentials are rejected.
- Model discovery goes through the backend so the browser never needs direct access to the LLM server.

## Files changed

- `backend/app/{runtime_settings,llm,settings_api}.py` (new), `backend/app/{config,main}.py`, `backend/pyproject.toml` (httpx)
- `backend/tests/test_llm_settings.py` (new), `backend/tests/conftest.py`
- `frontend/src/features/settings/SettingsPage.tsx` (new), `frontend/src/{App.tsx,api.ts,styles.css}`, `frontend/tests/e2e/brain-settings.spec.ts` (new)
- `docker/compose.dev.yml` (the `app-config` volume and LLM variables), `.env.example`

## Validation

- Unit tests: settings file precedence and corruption, URL validation, the Ollama request shape (schema, `think: false`, seed, `num_ctx`), reasoning stripping, failure classification, model discovery, and the settings API round trip with a rejected invalid update.
- E2E with the backend and server mocked: auto-discovery, model and language selection, save, and the unreachable-server error.
- The real server answered `/api/tags` and `/api/version` (Ollama 0.34.4) and lists `ornith-1.5:35b`.

## Risks

Transcripts leave the machine for the configured server. The operator chose their own server; the Settings page states the data flow.

## Next action

Independent QA/Security review of the outbound data flow.
