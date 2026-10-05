# ADR 0025: A setup wizard on the first start

## Status

Accepted (2026-10-05), by the operator.

## Context

On the first start there is no model configured, and the operator had to find Settings and fill in the provider, the server, the model and the language. The minimum to begin working is exactly those settings.

## Decision

- The settings file gets a field `setup_completed`. `GET /api/settings` also returns `setup_required`, true when the wizard has not been finished or skipped **and** no model is chosen. An installation that already has a model never sees the wizard, and no migration is needed: a file without the field reads as not completed.
- When `setup_required` is true the wizard takes the place of the application (no menu). Steps: language (the wizard changes to it at once), provider and server address with a check, model, and a summary with "Start". Every step says that everything can be changed later in Settings.
- "Skip" saves the chosen language and `setup_completed`, so the wizard does not come back even without a model; Settings stays available.
- It reuses what Settings already has: `PUT /api/settings`, `POST /api/settings/models` and the same controls (shared component), so both validate the same way.

## Consequences

- The only new state is one boolean in the existing settings file.
- A server that is not ready on the first day does not block anything: skip, and configure it later.

## Validation and rollback

Backend tests (new installation, model chosen, skipped, old file without the field) and Playwright tests (full flow, back and an unreachable server, skip, an installation with a model). Rollback: remove the wizard; the extra field in the file is ignored.

## Related records

- [Rebuild setup wizard](../features/rebuild-setup-wizard.md)
- [ADR 0023: Selectable LLM provider](0023-selectable-llm-provider.md)
