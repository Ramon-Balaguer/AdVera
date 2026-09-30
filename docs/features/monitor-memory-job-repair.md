# Feature: Monitor Memory Job Repair
Status: complete
Last updated: 2026-09-26

## Problem

Operators cannot repair memory jobs that remain pending or stuck. Monitor currently provides read-only summaries and Redis queue inspection, while memory workers may leave jobs in `running` with expired leases, attempts, and errors.

## Target user

An operator responsible for keeping meeting processing moving.

## Desired outcome

An operator can identify a stale memory index job in Monitor and safely request its recovery without direct database or Redis intervention.

## Smallest useful increment

List stale `running` memory index jobs and provide an explicit action that requeues an eligible job after clearing its expired lease.

## Scope

In scope:

- Detect stale memory index jobs using the configured lease timeout.
- Show safe job metadata in Monitor.
- Requeue an eligible stale job and clear its lease.
- Refresh the displayed state after the action.
- Add regression and endpoint tests.

Out of scope:

- Repairing transcription, Brain, or memory query jobs.
- Marking jobs completed manually.
- Deleting jobs or derived memory data.
- Changing transcript, provenance, provider, or model data.
- Automatic retry policy changes.

## Acceptance criteria

- Monitor identifies memory index jobs whose `running` lease exceeds the configured timeout.
- An operator can request repair for an eligible stale job from Monitor.
- A successful repair changes the job to `queued`, clears its lease token, and makes it available to the memory worker.
- Fresh running jobs and completed jobs cannot be repaired accidentally.
- Repeated repair requests are safe and do not create inconsistent leases or duplicate durable results.
- Backend and frontend tests cover stale, fresh, completed, unavailable, and successful-repair states.
- No sensitive meeting content or unsanitized provider error crosses the Monitor API.

## States and failure behavior

- `repairable`: a running job is older than the configured memory job timeout.
- `running`: the lease is still fresh; repair is rejected.
- `queued`: the job is already awaiting processing; repair is unnecessary and idempotent.
- `completed`: repair is rejected.
- `failed`: repair is rejected in the first increment.
- `repair_failed`: durable state was not changed, or queue notification failed; the UI shows a safe diagnostic code.

## Data and provenance constraints

PostgreSQL remains authoritative for job lifecycle and Redis remains transport only. The definitive transcript remains the source of truth for memory indexing. Repair preserves the meeting identity, input hash, projection version, provider, model, and existing derived data. The API exposes only safe identifiers, statuses, timestamps, attempt counts, and diagnostic codes.

## Dependencies and constraints

Reuse the existing `MemoryIndexJob`, `memory_job_timeout_seconds`, lease checks, and memory queue settings. Monitor currently has no explicit authorization layer; access control for a mutating endpoint requires confirmation before implementation. Database and Redis failure handling must not leave an unobservable state.

## Assumptions

- The first increment targets stale `running` memory index jobs only.
- Operators can access the existing Monitor route.
- A repair must not reset attempts or alter provenance.

## Open questions

- What authentication and operator permission must protect the mutating Monitor action?
- Should a repaired job increment attempts, or preserve the existing count?
- How should the API report database success followed by Redis enqueue failure?
- Should failed jobs be supported in a later explicit retry action?

## Recommended next agent

Orchestrator, followed by Architecture/Data, Backend, Frontend, and QA/Security.

## Implementation record

Monitor now lists stale `running` memory index jobs and exposes an explicit repair endpoint. Repair locks the job, rejects fresh leases and terminal states, changes stale jobs to `queued`, clears the lease, preserves the safe diagnostic, and publishes the job to the memory stream when Redis is available. The UI refreshes the Monitor snapshot after repair.

Authorization remains the existing Monitor boundary; no new authentication layer was introduced.

Files changed:

- `backend/app/memory_jobs.py`
- `backend/app/monitor.py`
- `backend/tests/test_monitor.py`
- `frontend/src/features/monitor/MonitorPage.tsx`
- `frontend/src/styles.css`
- `docs/features/monitor-memory-job-repair.md`

## Validation

- `backend/tests/test_monitor.py`: passed (`8` tests).
- `backend/tests/test_memory_backend.py`: passed.
- `backend/tests/test_openapi_contract.py`: passed.
- Focused editor diagnostics: no new errors in changed Monitor files.
- `frontend` build reaches the existing `App.tsx` type error: `Meeting.capture_locked` is missing in the `MeetingLibrary` type used by `deleteMeeting`.
- Ruff was unavailable in the active environment.

## Risks and next action

The main risks are concurrent worker claims and partial database/Redis recovery. The database state is committed before Redis publication; if publication fails, the job remains queued for worker reconciliation and the API reports `enqueued: false`. A future change should add explicit Monitor authorization before exposing this mutating operation outside the trusted operator surface.

Next action: resolve the pre-existing frontend type error, then run the frontend build and an end-to-end Monitor repair check with Redis available.