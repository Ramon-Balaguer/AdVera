# Capture Lock After Brain
Status: partial
Last updated: 2026-09-23

## Objective
Prevent new recordings once a meeting has a definitive transcript, completed Summary analysis, and completed Brain indexing for the same transcript hash.

## Scope
Expose a derived `capture_locked` state, disable the recording control, and reject direct WebSocket start requests for fully processed meetings.

## Acceptance Criteria
- Fully processed meetings expose `capture_locked=true`.
- The frontend disables capture for locked meetings after loading or refreshing.
- The audio WebSocket rejects `start` with a stable conflict code and does not mutate stored audio or transcript.
- Meetings with pending or failed Summary/Brain remain recoverable and unlocked.
- Summary and Brain must match the definitive transcript hash.

## Implementation State
In progress.

## Decisions
- Derive the lock from persisted transcript, Summary job, and Brain index job state; no migration is required.
- Use HTTP/WebSocket conflict code `MEETING_CAPTURE_LOCKED`.
- Provisional transcript data never closes capture.

## Files Changed
- Pending implementation.

## Validation
- Pending focused backend and frontend validation.

## Risks
- Existing clients may attempt to start through the WebSocket without consuming the meeting response field.
- A stale frontend can still attempt `start`; backend validation remains authoritative.

## Next Action
Implement the shared capture-lock predicate and cover API/WebSocket and UI behavior.
