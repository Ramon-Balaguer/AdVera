# Feature: Ollama settings group
Status: complete
Last updated: 2026-09-21

## Product Owner discovery brief

Problem: The Settings card is titled Ollama even though it also contains Hugging Face and runtime metrics settings, which makes ownership and scope unclear.

Target user: AdVera operators configuring the local runtime.

Desired outcome: Ollama URL, model, and discovery controls appear together in a clearly labeled zone while unrelated settings remain outside it.

Smallest useful increment: Add a semantic and visual Ollama group around only the URL and model controls, leaving token and metrics controls outside the group.

In scope / Out of scope: In scope are the Settings page grouping, labels, styles, and a focused UI assertion. Out of scope are API contracts, persistence, and setting behavior.

User acceptance criteria:

- The Ollama URL and model controls are inside a clearly labeled Ollama zone.
- Hugging Face token and runtime metrics controls are outside the Ollama zone.
- Existing save, discovery, and persistence behavior remains unchanged.

States and failure behavior: Existing loading, saving, discovery, and error states remain unchanged.

Data and provenance constraints: No data or API contract changes.

Dependencies and constraints: Preserve the existing form and responsive styles.

Assumptions: A visual and semantic grouping is sufficient; no separate save action is needed.

Open questions: None for this UI refinement.

Recommended next agent: Frontend, followed by focused E2E validation.

## Objective

Clarify the Settings page by grouping only Ollama configuration controls together.

## Scope

- Add a labeled Ollama group around the Ollama URL and model controls.
- Keep Hugging Face token and runtime metrics outside that group.
- Preserve current interactions and responsive behavior.

## Acceptance criteria

- The Ollama group contains `URL base de Ollama` and `Modelo de Ollama`.
- The Hugging Face token and metrics controls are not descendants of the Ollama group.

## Implementation state

Implemented. Ollama URL and model controls now live in a labeled visual group, while Hugging Face and metrics settings remain outside it.

## Decisions

- Keep one form and one save action so the API contract and persistence behavior do not change.
- Use semantic labeling and existing visual language instead of introducing a new settings component.

## Files changed

- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/tests/e2e/settings.spec.ts`
- `docs/features/ollama-settings-group.md`

## Validation

Focused frontend E2E validation and frontend build pass.

## Risks and next action

The main risk is visual regression on narrow screens; the existing responsive form layout remains unchanged. Next action: monitor the grouping in the deployed settings view.
