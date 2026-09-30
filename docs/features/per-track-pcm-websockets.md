# Feature: Per-track PCM WebSockets
Status: complete
Last updated: 2026-09-19

## Problem and target user

The outbound capture agent multiplexes microphone and system PCM on the control WebSocket. Track attribution depends on a JSON marker immediately preceding each binary frame, which is fragile under concurrent sends and makes failures harder to isolate.

## Desired outcome

The control WebSocket remains responsible for agent registration and session commands, while each active audio track sends PCM through its own authenticated WebSocket.

## Smallest useful increment

Negotiate `pcm_transport: per-track` on `agent.welcome`; open one PCM WebSocket per requested track after `capture.start`; complete a track handshake; send binary PCM only on that channel; close all track channels on stop or control disconnect. Keep the legacy multiplexed receiver for compatibility.

## Scope

- Agent per-track PCM WebSocket connections.
- Backend per-track PCM WebSocket endpoint and validation.
- Existing control, level and public proxy endpoints.
- Regression tests for negotiation, routing and lifecycle cleanup.

Out of scope: PCM format changes, reconnection replay, sequence numbering and new audio tracks.

## Acceptance criteria

- A microphone-only session opens one PCM channel and routes frames only to `microphone`.
- A dual-track session opens independent PCM channels for `microphone` and `system`.
- Binary frames are accepted only after a valid track handshake and active session validation.
- Track channels use the capture-agent bearer token and reject invalid agent, session or track values.
- Control commands and levels continue to use the existing control WebSocket.
- Stopping or losing control closes the per-track channels without leaving active state.
- Legacy multiplexed binary handling remains available for older agents.

## States and failure behavior

Control connection, session starting, track channel connecting, recording, stopping and disconnected. A failed track channel fails the active remote capture session and triggers the agent reconnect loop; PCM content is never logged.

## Data and provenance constraints

PCM remains authenticated transport data and is not logged. Track, capture session, recording and format metadata remain associated with the session. Definitive intelligence continues to use the definitive transcript pipeline only.

## Implementation state

Completed: the agent negotiates `per-track`, opens one authenticated PCM WebSocket per requested track before `capture.ready`, and the backend routes each binary frame directly to its track queue. The legacy multiplexed receiver remains available for older agents.

## Decisions

- Use the existing control WebSocket for negotiation and lifecycle.
- Use `/ws/capture-agents/{agent_id}/sessions/{capture_session_id}/tracks/{track}/pcm` for track data.
- Send a JSON track handshake, then binary PCM frames only.

## Files changed

- `agent/agent/remote.py`
- `backend/app/capture_agent.py`
- `agent/tests/test_agent.py`
- `backend/tests/test_capture_agent.py`
- `docs/features/per-track-pcm-websockets.md`

## Validation

- Agent suite: 16 passed.
- Backend capture-agent and contract tests: 7 passed.
- Static diagnostics: no errors in changed Python files.
- End-to-end test covers a system frame from the dedicated agent channel through the public backend proxy.

## Risks and next action

The per-track transport requires the backend and agent to deploy together for the new path; the legacy receiver remains temporarily to reduce rollout risk. Replay, sequence numbering and individual channel reconnection remain future hardening work.
