# Feature: Agent PCM E2E delivery fix
Status: complete
Last updated: 2026-09-19

## Problem and target user

The outbound capture agent connected successfully, but no PCM bytes reached the backend when using the negotiated per-track transport. The frontend then used browser microphone capture as a fallback. A second failure surfaced when the microphone callback supplied a buffer object that `websockets` rejected as a frame payload.

## Desired outcome

A real outbound agent session opens its track channel during `capture.start` and delivers PCM bytes to the backend proxy before the session is exposed as ready to the frontend.

## Smallest useful increment

Register the reserved capture session and requested tracks in the backend before sending `capture.start`, allowing the agent's per-track handshake to pass before `capture.ready`.

## Scope

- Backend remote capture session initialization order.
- Normalize device buffer objects to concrete `bytes` before queueing and WebSocket sends.
- E2E regression test with a real ASGI server, real `run_remote`, HTTP session start and WebSocket PCM delivery.
- No changes to browser fallback behavior or PCM format.

## Acceptance criteria

- The backend accepts a per-track PCM handshake after sending `capture.start` and before receiving `capture.ready`.
- The real outbound agent can send a PCM frame to the backend.
- Buffer-like microphone frames are converted to valid WebSocket binary payloads.
- The public backend PCM proxy returns the same frame.
- Failed start or mismatched session IDs clear the reserved session state.
- Existing capture-agent and agent suites remain green.

## States and failure behavior

The session is internally reserved while starting, but only returned as ready after the agent responds. Capture errors and session ID mismatches clear `session_id`, `recording_id` and `tracks` so a later session can start cleanly.

## Data and provenance constraints

The E2E uses synthetic PCM bytes only. No real audio, credentials or meeting content is logged or persisted.

## Implementation state

Completed by initializing `AgentConnection.session_id`, `recording_id` and `tracks` before issuing `capture.start`, then clearing them on failure.

## Files changed

- `backend/app/capture_agent.py`
- `backend/tests/test_capture_agent.py`
- `agent/agent/capture.py`
- `agent/agent/remote.py`
- `agent/tests/test_capture.py`
- `docs/features/agent-pcm-e2e-delivery-fix.md`

## Validation

- Integrated E2E: 1 passed.
- Buffer normalization regression: passed.
- Backend capture-agent and contract tests: 8 passed.
- Capture agent suite: 20 passed.

## Risks and next action

The running Docker API process must be restarted because the development compose mounts source files but Uvicorn does not enable reload. Restart the tray agent as well before testing with the physical microphone and WASAPI loopback.
