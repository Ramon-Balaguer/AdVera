# Feature: Interface language and LLM response language
Status: complete
Last updated: 2026-09-25

## Product Owner discovery brief

Problem: Operators cannot choose the language of the AdVera interface or Summary output.

Target user: The single operator of a self-hosted AdVera installation.

Desired outcome: The operator selects Spanish or English in Settings and new Summary responses follow that language.

Smallest useful increment: Persist one validated language preference, expose it in Settings, localize the Settings screen, and include the preference in each Summary job prompt and provenance.

In scope / Out of scope: In scope are Spanish and English, the persisted `/api/settings` contract, the Settings screen, Summary extraction prompts and job metadata. Out of scope are ASR language, transcript translation, historical extraction translation, multi-user preferences and Live Summary localization.

## Acceptance criteria

- Settings accepts only `es` or `en` and defaults to `es`.
- The selected language survives a backend restart and frontend reload.
- Settings labels switch between Spanish and English.
- New Summary jobs persist the selected language and explicitly instruct the LLM to produce textual fields in it.
- Transcript hashes, evidence IDs, statuses, JSON keys and provenance remain unchanged except for the recorded output language.
- Invalid language values do not overwrite the valid persisted setting.

## Implementation state

Implemented. Runtime settings persist the language in the existing local JSON file. Summary jobs record the language and the provider includes it in the output instruction. Existing jobs default to Spanish through the model migration default.

## Decisions

- Use `es` and `en` as canonical values, with Spanish as the backward-compatible default.
- Freeze language on `SummaryJob` creation so queued work remains reproducible if the global setting changes.
- Do not include language in the definitive transcript hash because it is an output preference, not source data.
- Keep the first UI localization slice scoped to Settings; other screens remain on their existing copy until a broader localization feature is defined.

## Files changed

- `backend/app/settings.py`
- `backend/app/models.py`
- `backend/app/summary_jobs.py`
- `backend/app/summary.py`
- `backend/app/worker.py`
- `backend/migrations/versions/0012_summary_output_language.py`
- `frontend/src/App.tsx`
- `frontend/src/features/settings/SettingsPage.tsx`
- `scripts/dev.ps1`
- `scripts/dev.sh`
- `backend/tests/test_settings.py`
- `backend/tests/integration/test_settings_api.py`
- `backend/tests/test_summary.py`
- `backend/tests/test_summary_worker.py`

## Validation

- Focused backend tests: 26 passed.
- Local settings path check resolves to `data/config/advera-settings.json`; Settings regressions: 13 passed.
- Frontend build was attempted; it remains blocked by pre-existing `cytoscape` dependency/type errors and an existing `MeetingLibrary`/`Meeting` type mismatch.

## Risks and next action

The LLM is instructed to use the selected language but output-language compliance is not independently detected. A future localization slice should define a shared translation catalog for all screens and decide whether Live Summary follows this preference.

## Architecture

- [ADR 0009](../adr/0009-summary-output-language-provenance.md)
