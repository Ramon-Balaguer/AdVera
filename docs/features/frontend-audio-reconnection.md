# Feature: Frontend audio reconnection
Status: in progress
Last updated: 2026-09-17

## Problem and target user

The backend can resume an audio session, but the React client currently closes the capture graph when the WebSocket disconnects and offers only a manual retry. Users can lose continuity during a temporary network interruption.

## Desired outcome

The browser keeps the microphone graph alive, queues a bounded number of PCM frames while reconnecting, resumes the backend session with its session cursor, and exposes a clear recovery state.

## Scope

- `reconnecting` transport state and user-visible status.
- Store `session_id` and `next_sequence` from `audio.ready`/`audio.received`.
- Automatic reconnect with bounded exponential delay.
- Bounded in-memory queue for frames generated while the socket is unavailable.
- Resume handshake using `resume: true`.
- Stop reconnecting on intentional stop, definitive completion or unrecoverable protocol error.

Out of scope: durable browser storage, replaying frames already acknowledged by the server, multi-tab coordination, authentication and service-worker offline support.

## Acceptance criteria

- A normal start still opens the microphone and sends a fresh session.
- A temporary WebSocket close changes the UI to reconnecting without stopping the microphone graph.
- Reconnect sends the existing session identifier and cursor.
- Queued frames are bounded and flushed after `audio.ready`.
- The UI returns to recording after a successful resume.
- Intentional stop does not schedule another reconnect.
- Reconnect exhaustion leaves an explicit disconnected/error state and preserves the backend session for manual recovery.

## States and failure behavior

- `connecting`: initial socket handshake.
- `recording`: socket ready and microphone active.
- `reconnecting`: socket lost while capture remains active.
- `disconnected`: retries exhausted; session remains recoverable on the backend.
- `stopping`, `stopped`, `error`: intentional stop or unrecoverable failure.

## Data and provenance constraints

- The backend session cursor remains authoritative.
- Provisional transcript remains presentation-only.
- The frame queue contains only in-memory PCM and is bounded.
- No secrets or meeting content are logged.

## Dependencies and assumptions

- Backend supports `session_id`, `resume` and `next_sequence` in the WebSocket start command.
- A browser session has one active recorder and one WebSocket.
- Frames accepted before disconnect are not replayed by the client; only frames generated while the socket is unavailable are queued.

## Implementation record

Product Owner brief recorded. The React client now retains the microphone graph, stores the backend session cursor, queues up to 64 unavailable frames, retries with bounded backoff and resumes with `resume: true`. The waveform is formed from the live PCM RMS level while recording. The user can abandon a reconnect attempt while leaving the backend session recoverable.

Files changed:

- `frontend/src/App.tsx`
- `docs/features/frontend-audio-reconnection.md`

## Validation

Frontend `npm run build` passes. A browser-level network interruption test remains pending.

## Risks and open questions

- Frames in flight at the instant of a network loss cannot be known to be acknowledged without a stronger transport protocol.
- Browser throttling can delay reconnect timers.
- A persistent queue may be needed for long offline periods in a future feature.

## Next action

Run a browser-level disconnect/resume smoke test. Frames already in flight at the instant of network loss remain a known transport limitation; a stronger acknowledgement protocol can address that later.
