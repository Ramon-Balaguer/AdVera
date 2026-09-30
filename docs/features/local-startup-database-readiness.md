# Local startup database readiness
Status: complete
Last updated: 2026-09-30

## Product Owner discovery brief

Problem: The first local startup can run Alembic while PostgreSQL is still initializing, even though its container is already running.

Target user: The self-hosted AdVera operator starting the local development environment.

Desired outcome: `scripts/dev.ps1 local` waits for the local dependencies to become healthy before applying migrations.

Smallest useful increment: Make the infrastructure startup command wait for the existing Compose health checks.

In scope / Out of scope: In scope is the local PowerShell startup path. Out of scope are database schema changes and production deployment orchestration.

Acceptance criteria:

- The local startup waits for PostgreSQL and Redis health checks before migrations run.
- A first initialization does not fail solely because PostgreSQL is still starting.
- A genuine infrastructure failure stops startup with a clear error.

States and failure behavior: Healthy dependencies allow startup to continue. A dependency that does not become healthy within the timeout stops startup before migrations run.

Data and provenance constraints: No application data or credentials are changed.

Assumptions: The Docker Compose health checks remain the source of truth for local dependency readiness.

Open questions: None for this local startup increment.

Recommended next agent: Operations, then QA and Security.

## Objective

Make the first local initialization transparent by waiting for healthy infrastructure before running Alembic.

## Scope

- Wait for the existing PostgreSQL and Redis Compose health checks.
- Fail early with a clear message when the wait times out.

## Acceptance criteria

- `scripts/dev.ps1 local` invokes Compose with `--wait` before migrations.
- A failed health wait prevents migration execution.

## Implementation state

Implemented.

## Decisions

- Use Docker Compose's existing health checks instead of duplicating PostgreSQL readiness logic in PowerShell.
- Bound the wait to 120 seconds so a broken dependency cannot leave startup hanging indefinitely.

## Files changed

- `scripts/dev.ps1`
- `docs/features/local-startup-database-readiness.md`

## Validation

- PowerShell parse: passed.
- Docker Compose readiness wait: passed; PostgreSQL and Redis reached `Healthy`.

## Risks and next action

This depends on a Docker Compose version supporting `up --wait`; the local environment accepts and completes the command.