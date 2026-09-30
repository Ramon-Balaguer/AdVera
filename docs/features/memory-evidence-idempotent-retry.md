# Feature: Idempotent memory evidence retries
Status: complete
Last updated: 2026-09-26

## Problem and target user

A memory indexing retry can attempt to insert an evidence row whose deterministic primary key was already written by another worker attempt. The meeting owner then gets a failed memory index instead of a usable memory view.

## Desired outcome

Repeated or overlapping indexing of the same definitive transcript remains idempotent and leaves one persisted row per evidence identity.

## Smallest useful increment

Persist `memory_evidence` rows with an atomic primary-key conflict policy and add a regression test for repeated evidence IDs in one insert batch.

## Scope

- Make memory evidence persistence tolerate repeated deterministic IDs.
- Preserve transcript hashes, timestamps, segment IDs and projection metadata.
- Add focused backend regression coverage.

Out of scope: changing embedding generation, transcript state rules, graph identity generation or frontend behavior.

## Acceptance criteria

- Repeated evidence IDs do not raise `UniqueViolationError`.
- A valid memory index can complete when a duplicate evidence identity is encountered.
- At most one row exists for each evidence primary key.
- Existing provenance fields remain unchanged.

## States and failure behavior

- First insert creates the evidence row.
- Repeated or concurrent insert ignores the conflicting row and continues indexing.
- Definitive transcript validation and unrelated persistence errors retain their existing behavior.

## Data and provenance constraints

Evidence identity remains the existing deterministic primary key. Conflict handling never merges rows with different IDs and does not consume provisional transcript data.

## Decisions and assumptions

The database is the authority for the atomic conflict decision. PostgreSQL is the production dialect; SQLite support is retained for the backend test suite.

## Implementation record

Updated `backend/app/memory_worker.py` to batch evidence rows through dialect-native `ON CONFLICT DO NOTHING` inserts for PostgreSQL and SQLite. The insert also runs under `session.no_autoflush` so pending ORM state cannot bypass the conflict-safe statement. The worker still deduplicates IDs in memory and persists base segment evidence before requeuing when Brain extraction is unavailable.

Files changed:

- `backend/app/memory_worker.py`
- `backend/tests/test_memory_backend.py`
- `docs/features/memory-evidence-idempotent-retry.md`

No ADR was created because this is an isolated persistence retry fix and does not change the data contract or ownership boundary.

## Validation

- Focused regression test: `1 passed`.
- Full `backend/tests/test_memory_backend.py`: `14 passed`.
- Editor diagnostics: no errors in modified Python files.
- Ruff validation was unavailable because `ruff` is not installed in the current environment.

## Risks and open questions

A stale worker can still perform other work concurrently; the existing job lease remains responsible for worker ownership. This change only makes evidence writes safe and idempotent.

## Next action

Deploy the worker change and monitor memory indexing retries for duplicate-key failures.