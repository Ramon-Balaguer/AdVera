# Summary Worker Redis Reconnect
Status: complete
Last updated: 2026-09-26

## Product Owner brief

Problem: A Redis connection closure during Summary worker stream consumption terminates the worker process and pauses asynchronous meeting processing.

Target user: AdVera operators and users relying on Summary extraction to complete without manual worker restarts.

Desired outcome: The Summary worker reconnects after a transient Redis disconnect and resumes consuming jobs.

Smallest useful increment: Recreate the Redis client with bounded backoff when `xreadgroup` reports a connection failure, with a regression test.

In scope: Redis read disconnect recovery, reconnect logging and focused worker tests.

Out of scope: Redis topology, job schemas, Summary processing semantics, deployment restart policy and Brain worker changes.

## Acceptance criteria

- A Redis connection closure during `xreadgroup` does not terminate the Summary worker.
- The worker recreates its Redis client and resumes stream consumption.
- Existing acknowledgements, PostgreSQL leases and job retry behavior remain unchanged.
- Reconnect delays are bounded and the failure is observable in logs.

## Implementation state

Implemented.

## Decisions

- PostgreSQL remains the source of truth for job state; Redis remains transport only.
- Reconnect backoff starts at one second and is capped at 30 seconds.
- The existing stream, consumer group and consumer identity are reused after reconnect.

## ADR and flow impact

No new ADR or `docs/meeting-processing-flow.md` update is required. The processing stages, contracts and provenance boundaries are unchanged.

## Files changed

- `backend/app/worker.py`
- `backend/tests/test_worker_services.py`
- `docs/features/summary-worker-redis-reconnect.md`

## Validation

- Focused Summary worker regression test.

## Risks

- A permanently unavailable Redis instance leaves the worker retrying until infrastructure recovers; deployment health and restart policy remain operational concerns.

## Next action

Run the backend worker test suite and verify the reconnect warning in the local container logs during a Redis restart.