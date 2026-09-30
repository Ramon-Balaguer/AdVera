# Feature: Alembic schema ownership
Status: complete
Last updated: 2026-09-25

## Problem and target user

Application startup called SQLAlchemy `create_all()` before Alembic migrations. When a new model was deployed, startup could create its table while Alembic still recorded the previous revision, causing the next migration to fail with `DuplicateTableError`. The affected users are AdVera developers and operators starting or upgrading the backend.

## Desired outcome

Alembic is the sole owner of runtime schema creation and upgrades. Application startup checks database connectivity without creating or altering tables.

## Scope

- Remove runtime metadata DDL from backend startup.
- Preserve isolated test fixtures that explicitly create their own schemas.
- Recover the current local database by stamping `0011_transcription_jobs` after verifying its existing table matches the migration.

## Acceptance criteria

- Backend startup does not call `Base.metadata.create_all()`.
- `alembic upgrade head` can apply pending migrations without startup-created tables.
- Existing compatible `transcription_jobs` data is preserved.
- A regression test protects the no-runtime-DDL behavior.

## States and failure behavior

- Fresh or upgraded databases are prepared by Alembic before the backend starts.
- Startup verifies connectivity only; migration failures remain visible and actionable.
- An already partially provisioned database must be schema-checked before its revision is stamped.

## Data and provenance constraints

No application data is changed by startup. Migration history remains the source of schema state.

## Dependencies and assumptions

Deployment and local development invoke Alembic before starting the API. Existing test fixtures may continue using explicit `create_all()` for temporary databases.

## Implementation record

Changed runtime database initialization to open and close a connection without emitting DDL. The local `transcription_jobs` table was inspected and matched migration `0011` including all columns and indexes.

## Validation

- `backend/tests/test_database.py` verifies startup does not create schema objects.
- Local recovery command: `python -m alembic stamp 0011_transcription_jobs`, followed by `python -m alembic upgrade head`.

## Risks and open questions

Environments that previously depended on application startup to create an empty schema must run the documented migration command first.

## Next action

Stamp the verified local database at `0011_transcription_jobs`, then restart the API through the normal development script.