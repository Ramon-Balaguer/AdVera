# Feature: Brain job schema drift recovery
Status: complete
Last updated: 2026-09-25

## Problem and target user

The backend selected `brain_jobs.language`, but the active PostgreSQL database was at Alembic revision `0011_transcription_jobs` and did not contain that column. AdVera developers and operators could see Brain worker and monitor requests fail while the API continued starting.

## Desired outcome

The database schema is upgraded before local workers start, and a failed migration prevents the API from starting in an incompatible state.

## Scope

- Apply migration `0012_brain_output_language` to the active development database.
- Run migrations before workers in local development mode.
- Fail fast when migrations return a non-zero exit code.
- Preserve the existing Brain output-language contract.

## Acceptance criteria

- The active database reports revision `0012_brain_output_language` or later.
- `brain_jobs.language` exists with the migration's Spanish default.
- `dev.ps1 local` and `dev.sh local` migrate before starting workers.
- A migration failure stops startup before dependent processes are opened.

## States and failure behavior

- Pending migration: apply it before workers and API start.
- Migration failure: stop startup and report the error.
- Healthy schema: continue with the existing local process startup.

## Data and provenance constraints

The migration preserves existing jobs and assigns the schema default `es` to existing rows. It does not alter definitive transcript data, hashes, evidence or Brain outputs.

## Dependencies and assumptions

The local PostgreSQL service is reachable at `localhost:5432`, and Alembic revision `0012_brain_output_language` is the intended contract already represented by `BrainJob`.

## Implementation record

- Applied `0011_transcription_jobs -> 0012_brain_output_language` to the active development database.
- Added shared PowerShell and shell migration steps with fail-fast exit handling.
- Moved local-mode migration ahead of worker startup to remove the startup race.

## Validation

- `python -m alembic upgrade head` completed successfully.
- PostgreSQL schema inspection confirmed the new revision and `brain_jobs.language`.
- PowerShell and shell syntax validation, startup-order regression tests and focused Brain worker tests completed successfully.

## Risks and open questions

The change covers the Windows and POSIX local development flows. Other deployment entrypoints must continue invoking Alembic before workers and API processes.

## Next action

Restart the local development environment so all processes use the repaired schema.
