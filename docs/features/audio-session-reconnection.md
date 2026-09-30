# Feature: Audio session reconnection
Status: in progress
Last updated: 2026-09-17

## Problem and target user

A browser or network interruption currently ends the WebSocket session without a protocol for continuing the same recording. Meeting participants need to recover capture without losing or duplicating the audio already stored.

## Desired outcome

A recording session has a durable identifier and frame cursor. A reconnecting client can resume that session, append audio to the existing PCM file, continue sequence numbers, and explicitly stop or leave the session recoverable.

## Scope

- Durable audio session manifest per meeting.
- Resume handshake with session identifier and next sequence.
- Server-side protection against stale resume cursors.
- Preserve `original.pcm` during resume; truncate only for a new session.
- Explicit `audio.ready` response indicating whether the session was resumed.
- Backend integration coverage for disconnect and resume.

Out of scope: authentication, multi-client concurrency, process-restart job recovery, frontend offline audio queue, and intelligence.

## Acceptance criteria

- A new `start` creates a session identifier and returns it in `audio.ready`.
- A disconnected client can resume with that identifier and the server returns the next expected sequence.
- Resuming never truncates the existing PCM file.
- Frames after resume continue from the persisted sequence.
- A stale or unknown resume request is rejected without modifying stored audio.
- A normal stop still runs definitive processing exactly once.
- Tests use fake ASR and no real meeting content.

## States and failure behavior

- `recording`: session is active or recoverable after a disconnect.
- `processing`: stop accepted and definitive ASR running.
- `ready`: definitive transcript persisted.
- `failed`: processing failed while original audio remains available.
- A disconnect does not claim `ready` or `failed`; it leaves the session recoverable.
- Resume with a lower client cursor is rejected to prevent duplicate frames.

## Data and provenance constraints

- The original PCM remains the source for definitive processing.
- Session metadata contains only identifiers, sequence counters and status.
- Provisional transcript remains presentation-only.
- No secrets, real meeting content or chain-of-thought are stored.

## Dependencies and assumptions

- PCM remains signed 16-bit, mono, 16 kHz.
- One active recorder client is supported for the first increment.
- The client can retain the session identifier and next sequence in memory during a browser session.

## Implementation record

Product Owner brief recorded. The backend now persists an audio session manifest, returns a session cursor during `audio.ready`, validates resume cursors, appends PCM on resume, and leaves disconnected sessions recoverable.

Files changed:

- `backend/app/audio.py`
- `backend/app/live_pipeline.py`
- `backend/tests/integration/test_audio_websocket.py`
- `docs/features/audio-session-reconnection.md`

## Validation

The focused reconnect integration test passes. The full backend suite passes with 13 tests, and Python compilation passes.

## Risks and open questions

- A process restart can leave a manifest and PCM requiring explicit cleanup or recovery policy.
- The current browser client does not yet replay an in-memory audio queue after a network interruption.
- Multi-client races require authentication and a lease/owner mechanism later.

## Next action

Add browser reconnect orchestration, a bounded outgoing audio queue and UI recovery state in a separate frontend increment. The backend protocol is validated but does not yet replay audio that was buffered only in the browser.
