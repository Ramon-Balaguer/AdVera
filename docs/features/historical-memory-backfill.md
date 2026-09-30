# Historical Memory Backfill
Status: partial
Last updated: 2026-09-25

## Objective
Populate Brain and Memoria from existing definitive meeting transcripts.

## Scope
Reconcile existing definitive transcripts with idempotent Brain and memory index jobs, and run the memory worker in the development Compose stack. Partial, missing, invalid, or provisional transcripts are skipped.

## Acceptance Criteria
- A dry run reports eligible and skipped meetings without creating jobs.
- An apply run creates or reuses Brain jobs and enqueues them.
- Completed Brain extractions receive a compatible memory index job.
- Re-running does not create duplicate effective jobs or derived records.
- Failed jobs are not forced unless explicitly requested.
- Memory processing retains transcript hashes, segment IDs, timestamps, and provider metadata.
- Brain can reach `ready` or `partial` after the workers finish.

## Implementation State
Delivered. The operator backfill and development memory worker are available.

## Decisions
- The definitive transcript remains the only intelligence source.
- Backfill is an operator command, not a user-facing UI action.
- Redis enqueue failures remain recoverable through persisted queued jobs.
- Development backend services share the `advera-backend:dev` image; application code and migrations are mounted for incremental updates.

## Files Changed
- `backend/app/backfill_memory.py`
- `backend/app/memory_worker.py`
- `backend/app/models.py`
- `backend/migrations/versions/0009_memory_chunk_hash_ids.py`
- `backend/tests/test_backfill_memory.py`
- `backend/tests/test_backend_services.py`
- `docker/compose.dev.yml`

## Validation
- `python -m pytest -q backend/tests/test_backfill_memory.py backend/tests/test_memory_backend.py backend/tests/test_memory_intelligence.py backend/tests/test_brain_worker.py` -> 19 passed.
- Compose configuration validated.
- Dry run found 11 definitive meetings.
- Applied run reconciled 11 eligible meetings and skipped 1 meeting without a transcript.
- Live overview reached `partial` with 9 indexed meetings, 10 chunks, and 45 nodes while the worker continued processing.
- `docker compose -f docker/compose.dev.yml up -d --no-build memory-worker` started the Compose-managed worker using the existing backend image.
- Regression fix validated with `python -m pytest backend/tests/test_backend_services.py -q` -> 30 passed, and the complete backend suite -> 203 passed.

## Risks
Historical Brain and embedding processing may be resource-intensive. Provider failures are isolated per meeting and must be retried explicitly. Backfill now resolves the unique completed extraction by `brain_job.id`, preventing stale or unrelated extractions from being selected.

## Next Action
Configure a working embedding provider and allow the memory worker to finish the remaining queued/running jobs; rerun the backfill safely if needed.
