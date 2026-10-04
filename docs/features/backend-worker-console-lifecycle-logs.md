# Feature: Backend worker console processing logs
Status: partial
Last updated: 2026-09-28

## Problem and target user
Operators cannot readily tell from the console when backend workers begin processing a queued request.

## Desired outcome
Make processing starts visible in worker console output without exposing meeting content or request payloads.

## Scope
Add concise start events for transcription, summary extraction, brain indexing and brain query jobs. Include only the job type and opaque job ID, with the meeting ID where already available as an operational identifier. Preserve existing completion and failure events.
Out of scope: frontend changes, monitoring UI, payload logging, and changes to processing or retry behavior.

## Acceptance criteria
- A job accepted for processing emits one console-visible INFO event naming its worker/job type and opaque job ID.
- Duplicate, completed, missing, or actively leased jobs that are not processed do not emit a start event.
- Events contain no transcript, audio, meeting title, query text, prompt, credentials, or request payload.
- Logging does not change job processing, retry, or persistence behavior.
- Acceptance check: focused worker tests capture start logs across worker types, verify safe identifiers, and assert sensitive fixture content is absent.

## States and failure behavior
An event is emitted after the job is claimed and its running state is persisted. A worker interruption may leave a start event without a completion event. Existing retry and failure behavior remains unchanged.

## Data and provenance constraints
Logs are operational metadata, not transcript-derived intelligence. Include only job type and opaque identifiers; never log meeting content or secrets.

## Dependencies and assumptions
Assume “request” means a queued backend job consumed by one of the three backend worker services. Existing worker INFO logging is routed to the console by local and container execution.

## Implementation record
Added INFO start events after a successful claim for transcription, summary extraction, brain indexing, and brain query jobs. Events include opaque job ID, applicable meeting ID, and attempt count; query text, transcript content, prompts, titles, and credentials are not logged. Added regression assertions for event identity, sensitive-content absence, and no start event for duplicate, active-lease, or failed-claim paths. No processing behavior or architectural boundary changed; no ADR was needed.

Files changed:
- `backend/app/transcription_worker.py`
- `backend/app/worker.py`
- `backend/app/brain_worker.py`
- `backend/tests/test_transcription_worker.py`
- `backend/tests/test_summary_worker.py`
- `backend/tests/test_brain_backend.py`
- `docs/features/README.md`
- `docs/features/backend-worker-console-lifecycle-logs.md`

## Validation
- `& .\.venv\Scripts\python.exe -m pytest backend/tests/test_transcription_worker.py backend/tests/test_summary_worker.py backend/tests/test_brain_backend.py -q` -> 28 passed.
- `& .\.venv\Scripts\python.exe -m ruff check backend/app/transcription_worker.py backend/app/worker.py backend/app/brain_worker.py backend/tests/test_transcription_worker.py backend/tests/test_summary_worker.py backend/tests/test_brain_backend.py` -> all checks passed.
- Independent QA confirmed safe event fields and claim-boundary behavior, but did not approve release: focused module coverage was reported below the 90.1% backend gate, and backend-wide coverage was not completed.

## Risks and open questions
Each processed job adds one concise INFO line, increasing console volume proportionally to job throughput. The request is interpreted as queued jobs, not synchronous API requests. Release remains blocked until the applicable backend coverage gate is met and QA re-review is complete; no service/container smoke test was run.

## Next action
QA and Security: resolve or confirm the required coverage gate for this slice, complete backend-wide coverage validation, and re-review before release. Operations: observe the start events in local worker console output during a normal queued-job run.