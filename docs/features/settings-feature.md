# Feature: Settings frontend feature
Status: in progress
Last updated: 2026-09-21

## Problem and target user
The runtime settings UI is embedded in the application shell, mixing configuration workflow concerns with global navigation and runtime metrics.

## Desired outcome
Settings has a dedicated frontend feature boundary while preserving current configuration behavior.

## Scope
Extract the existing settings page, props, and settings-specific types/API boundary into `frontend/src/features/settings/`. Preserve `/settings`, loading/saving/model discovery/token behavior, labels, styles, and API contracts.

## Acceptance criteria
- The existing settings route renders through the settings feature.
- Loading, save, validation, model discovery, token, and error states behave as before.
- Runtime metrics remain available to the global shell.
- Existing settings tests and frontend build pass.

## States and failure behavior
Preserve settings loading, ready, saving, saved, save error, model discovery, and token-configured states.

## Data and provenance constraints
No secrets are logged or exposed. No API payloads or persistence behavior changes.

## Dependencies and assumptions
The shell keeps ownership of shared runtime metrics and passes settings data/callbacks into the feature initially.

## Implementation record
Pending extraction and validation.

## Validation
Pending.

## Risks and open questions
Settings state is coupled to runtime metrics in the shell; do not move that shared connection in the first extraction.

## Next action
Extract the settings page and run the focused settings suite.
