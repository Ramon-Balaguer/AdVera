# Feature: Memory index queue hot-loop prevention
Status: complete
Last updated: 2026-09-26

## Objective

Prevent `advera:memory:index` from immediately requeueing the same job while its Brain extraction is still unavailable.

## Scope

When memory indexing has built the definitive transcript evidence but cannot find a completed Brain extraction, leave the job queued with an explicit waiting reason, without consuming an attempt and without requesting an immediate Redis retry. Brain completion remains responsible for enqueueing the memory job again.

## Acceptance criteria

- A memory job without a completed Brain extraction returns `False` to the Redis consumer.
- The job remains `queued` and retains the attempt consumed by its claim.
- The persisted reason states that the job is waiting for Brain.
- The consumer ACKs the current message without immediately adding another message for the same job.
- When Brain completes, its existing enqueue path can process the queued memory job.
- Genuine retryable memory failures continue to use the configured retry limit.

## Implementation state

Implemented. The missing-Brain dependency path no longer decrements attempts or returns a Redis retry signal.

## Decisions

- Treat missing Brain as a dependency wait, not a transient provider failure.
- Keep the existing `queued` state to avoid a schema change.
- Do not alter definitive transcript provenance or memory evidence behavior.

## Files changed

- `backend/app/memory_worker.py`
- `backend/tests/test_memory_backend.py`

## Validation

- Focused memory backend regression passes.
- The test verifies the job remains queued with its claim attempt intact and no immediate retry signal.

## Risks and next action

A permanently failed Brain job can leave its dependent memory job queued until an operator retries or repairs Brain. A future operational slice may add an explicit `waiting_for_brain` state and stale pending-message reclamation.