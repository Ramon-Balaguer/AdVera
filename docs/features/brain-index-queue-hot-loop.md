# Feature: Brain index queue hot-loop prevention
Status: complete
Last updated: 2026-09-26

## Objective

Prevent `advera:brain:index` from immediately requeueing the same job while its Summary extraction is still unavailable.

## Scope

When brain indexing has built the definitive transcript evidence but cannot find a completed Summary extraction, leave the job queued with an explicit waiting reason, without consuming an attempt and without requesting an immediate Redis retry. Summary completion remains responsible for enqueueing the brain job again.

## Acceptance criteria

- A brain job without a completed Summary extraction returns `False` to the Redis consumer.
- The job remains `queued` and retains the attempt consumed by its claim.
- The persisted reason states that the job is waiting for Summary.
- The consumer ACKs the current message without immediately adding another message for the same job.
- When Summary completes, its existing enqueue path can process the queued brain job.
- Genuine retryable brain failures continue to use the configured retry limit.

## Implementation state

Implemented. The missing-Summary dependency path no longer decrements attempts or returns a Redis retry signal.

## Decisions

- Treat missing Summary as a dependency wait, not a transient provider failure.
- Keep the existing `queued` state to avoid a schema change.
- Do not alter definitive transcript provenance or brain evidence behavior.

## Files changed

- `backend/app/brain_worker.py`
- `backend/tests/test_brain_backend.py`

## Validation

- Focused brain backend regression passes.
- The test verifies the job remains queued with its claim attempt intact and no immediate retry signal.

## Risks and next action

A permanently failed Summary job can leave its dependent brain job queued until an operator retries or repairs Summary. A future operational slice may add an explicit `waiting_for_summary` state and stale pending-message reclamation.