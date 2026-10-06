# Feature: Rebuild LLM providers
Status: in progress
Last updated: 2026-10-04

## Objective

Let the operator choose the LLM provider in Settings: Ollama or an OpenAI-compatible server. The trigger was a llama-swap server that Settings could not check and no job could use (ADR 0023).

## Scope

- `OpenAIProvider` (`backend/app/llm.py`) beside `OllamaProvider`, one factory `provider_for` used by the Summary and Brain workers according to the provider stored in each job, and model discovery per provider.
- Settings API: provider in the settings; `POST /api/settings/models` with `{provider, base_url}`.
- Settings page: a provider selector, a URL placeholder and a hint that depend on it, texts in English, Spanish and Catalan.

- Optional API key (branch `feature/llm-api-key`): `llm_api_key` in the runtime settings file (mode 0600, never returned by the API, which exposes `llm_api_key_set`), sent as `Authorization: Bearer` on every completion and model-discovery call; workers read it from the file at call time, so it is not copied into job rows. Settings and the wizard have a password field (blank keeps the stored key, "Remove key" clears it).

- More providers: `anthropic` (Messages API, `x-api-key`, schema in `output_config.format`) and `gemini` (`streamGenerateContent`, schema in `responseJsonSchema`, `x-goog-api-key`); both need an API key, have a fixed address in Settings and show a cloud-privacy notice. The OpenAI-compatible provider has presets (OpenAI, OpenRouter, Groq, Mistral, LM Studio) and omits `chat_template_kwargs` for those hosted APIs (`max_completion_tokens` on OpenAI). DeepSeek is left out: it has no `json_schema` response format.

Out of scope: a model per task.

## Acceptance criteria

1. Settings can save and read the provider; an unknown one is refused.
2. Checking a server lists its models with the chosen provider; errors have clear texts.
3. Both providers give the same results through the same contract (stream joined, reasoning ignored, truncation and failures classified).
4. A job runs with the provider it was created with.
5. Backend (at least 90% coverage), Playwright and `check_docs.py` pass; a real call to the operator's llama-swap works.

## Implementation state

Backend, page and tests done on branch `feature/llm-providers`. A real call (`ornith-1.5-35b-chat`, synthetic prompt, schema-bound answer in about 10 s) and the model list worked. Deployment and a summary of a test meeting are pending.

## Decisions

- One model for everything for now (operator).
- No API key; no secrets in Settings.
- The server address is accepted with or without `/v1`.

## Files changed

- `backend/app/{llm,runtime_settings,settings_api,summary_worker,brain_worker}.py`
- `backend/tests/test_openai_provider.py` (new), `backend/tests/test_llm_settings.py`
- `frontend/src/features/settings/SettingsPage.tsx`, `frontend/src/i18n/*`, `frontend/tests/e2e/summary-settings.spec.ts`
- `docs/adr/0023-selectable-llm-provider.md`, `docs/meeting_manager_project_spec.md`, `docs/meeting-processing-flow.md`

## Validation

- 18 provider tests with an in-process transport and 2 settings API tests; 2 new Playwright tests.
- One real call and the model list against the operator's llama-swap.

## Risks

- A hosted OpenAI-style service may reject `seed` or `chat_template_kwargs` or require a key.
- A "chat" model with a small prompt window used for long transcripts: the operator's choice in Settings.

## Next action

Deploy and generate a summary of a test meeting with the llama-swap server.
