# Feature: Rebuild setup wizard
Status: complete
Last updated: 2026-10-05

## Objective

A wizard on the first start that sets the minimum to begin working: the same choices as Settings (language, LLM provider, server and model), warning that all of it can be changed later (ADR 0025).

## Scope

- `setup_completed` in the settings file; `setup_completed` and `setup_required` in `/api/settings`.
- `SetupWizard` (language, server with check, model, summary), shown in place of the application when `setup_required`; "Skip" at any step; the note "you can change all of this later in Settings" in every step and in the summary.
- Shared `ServerFields`, `settingsApi` between Settings and the wizard. Texts in English, Spanish and Catalan.

Out of scope: any other setting (transcription, capture), a model per task, API keys.

## Acceptance criteria

1. A new installation (no model, wizard not finished) gets the wizard; one with a model, or after finishing or skipping, does not.
2. Language changes the wizard at once; the server must be checked and a model chosen to go on; Back keeps the choices.
3. Finishing saves provider, address, model, language and `setup_completed` in one request; skipping saves language and `setup_completed`.
4. Every step shows that the choices can be changed in Settings.
5. Backend (at least 90% coverage), Playwright and `check_docs.py` pass.

## Implementation state

Done on branch `feature/setup-wizard` (not merged) and deployed on 2026-10-05. On the real stack the operator's settings (which already have a model) answer `setup_required: false`; with an empty temporary settings file the backend answers `true`, and after skipping `false`. Backend 90.88% coverage, 69 Playwright tests.

## Decisions

- Shown only when no model is configured; skippable (operator).
- Order: language, server, model, summary (operator).
- A settings file without the field is read as not completed, so existing installations with a model are unaffected.

## Files changed

- `backend/app/runtime_settings.py`, `backend/app/settings_api.py`, `backend/tests/test_llm_settings.py`
- `frontend/src/App.tsx`, `frontend/src/features/setup/SetupWizard.tsx`, `frontend/src/features/settings/{ServerFields.tsx,settingsApi.ts,SettingsPage.tsx}`, `frontend/src/i18n/*`, `frontend/src/theme.css`, `frontend/tests/e2e/setup-wizard.spec.ts`

## Validation

- Backend tests of `setup_required`; 4 Playwright tests plus the settings ones that use the shared controls.

## Risks

- Testing the first start on the real stack must use a temporary settings file, never the operator's.

## Next action

The operator decides on merging the branch.
