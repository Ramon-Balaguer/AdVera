# Feature: Idempotent memory chunk retries
Status: complete
Last updated: 2026-09-26

## Problem and target user

Memory indexing can fail with PostgreSQL `UniqueViolationError` when deterministic `memory_chunks.id` values are inserted more than once during retries or overlapping jobs. Meeting owners and operators then receive a failed memory index instead of a usable memory view.

## Desired outcome

Repeated or overlapping indexing of the same definitive transcript remains idempotent and preserves one valid chunk per deterministic identity.

## Smallest useful increment

Persist memory chunks with an atomic primary-key conflict policy and add focused regression coverage.

## Scope

- Make `memory_chunks` persistence tolerate repeated deterministic IDs.
- Preserve chunk content, provenance, source segments, timestamps and embedding metadata.
- Add backend regression coverage.

Out of scope: changing chunk identity generation, transcript validation, embedding generation or frontend behavior.

## Acceptance criteria

- Repeated chunk IDs do not raise `UniqueViolationError`.
- At most one row exists for each chunk primary key.
- Existing provenance and source-segment fields remain unchanged.
- Definitive transcript validation and unrelated persistence errors retain their existing behavior.

## States and failure behavior

- First insert creates the chunk row.
- A repeated or concurrent deterministic ID is ignored and indexing continues.
- Invalid or changed definitive transcripts continue to fail using the existing behavior.

## Data and provenance constraints

Chunk identity remains the deterministic hash of meeting ID, source segment IDs and content hash. Conflict handling does not merge different IDs or consume provisional transcript data.

## Decisions and assumptions

The database is the authority for the atomic conflict decision. PostgreSQL is the production dialect; SQLite compatibility is retained for the backend test suite. No ADR is required because the primary-key contract and ownership boundary are unchanged.

## Implementation state

Product Owner brief, technical handoff, backend implementation and regression validation complete.

## Files changed

- `backend/app/memory_worker.py`
- `backend/tests/test_memory_backend.py`
- `docs/features/memory-chunk-idempotent-retry.md`

## Validation

- Focused regression test: `1 passed`.
- Full `backend/tests/test_memory_backend.py`: `16 passed`.
- Editor diagnostics: no errors in the modified test file; existing dynamic-typing diagnostics remain in `memory_worker.py`.

## Risks and open questions

A stale worker may still perform unrelated work concurrently; the existing job lease remains responsible for worker ownership. The conflict policy keeps the first persisted row for a deterministic identity.

## Next action

Deploy the worker change through the normal release gate and monitor memory indexing retries for duplicate-key failures.