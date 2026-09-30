# MOSS persistent Hugging Face token
Status: complete
Last updated: 2026-09-30

## Product Owner discovery brief

Problem: MOSS is started by Docker Compose, but the Hugging Face token saved in AdVera Settings is only available to the backend process and is not passed to the MOSS container.

Target user: The self-hosted AdVera operator running the local MOSS profile.

Desired outcome: MOSS uses the existing saved Hugging Face token for authenticated model downloads without exposing the token in source, logs or API responses.

Smallest useful increment: Load the persisted token during the development MOSS startup command and export it to Docker Compose.

In scope / Out of scope: In scope is the local PowerShell startup path and its feature record. Out of scope are secret rotation, production secret managers and MOSS application changes.

Acceptance criteria:

- Starting MOSS uses an already configured `HF_TOKEN` environment value when present.
- When no environment value is present, starting MOSS reads the persisted Settings token and passes it to the container.
- Missing or malformed Settings do not stop MOSS startup or print a token.
- The token value is never committed or logged.

States and failure behavior: An absent token preserves unauthenticated startup. A malformed or unreadable Settings file is ignored and MOSS continues without a token.

Data and provenance constraints: The token remains in the existing local Settings file and process environment only. It must not appear in Compose YAML, diagnostics or tests.

Assumptions: The local development path uses `scripts/dev.ps1` and stores Settings at `data/config/advera-settings.json` unless `SETTINGS_PATH` overrides it.

Open questions: Production deployments should provide `HF_TOKEN` through their deployment secret mechanism rather than relying on this development helper.

Recommended next agent: Operations, then QA and Security.

## Objective

Pass the persisted Hugging Face token to the opt-in local MOSS container at startup.

## Scope

- Read the existing persisted token only when `HF_TOKEN` is not already set.
- Keep the Compose declaration unchanged because it already maps `HF_TOKEN` to MOSS.
- Do not expose the token in output or source control.

## Acceptance criteria

- `scripts/dev.ps1 moss` and `scripts/dev.ps1 local` export the saved token before `docker compose` starts MOSS.
- An explicit environment token takes precedence.
- Compose continues to render with an empty token when no token is configured.

## Implementation state

Implemented.

## Decisions

- Use the existing PowerShell development startup boundary as the adapter between persisted Settings and Docker Compose.
- Preserve an explicitly supplied environment token as the higher-precedence deployment value.

## Files changed

- `scripts/dev.ps1`
- `docs/features/moss-persistent-huggingface-token.md`

## Validation

- `scripts/dev.ps1` PowerShell parse: passed.
- Persisted token presence check: passed without printing the token.
- `docker compose -f docker/compose.dev.yml -f docker/compose.nvidia.yml --profile moss config --quiet`: passed.

## Risks and next action

The helper applies to the local PowerShell workflow only. Production or direct Compose invocations must continue to provide `HF_TOKEN` through their environment or secret manager.
