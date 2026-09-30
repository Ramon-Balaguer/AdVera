# Feature: Transcription relay reconnection fix
Status: complete
Last updated: 2026-09-17

## Problem and target user
A user recording through the native Windows agent can lose PCM frames after the frontend reconnects to the backend. Multiple agent PCM WebSockets may consume the same destructive frame queue, leaving the active backend socket without audio and making transcription appear to stop.

## Desired outcome
Only the current backend connection consumes native PCM frames, and stale socket callbacks cannot change the state of a newer recording connection.

## Scope
- Close old per-track agent PCM sockets before opening replacements after `audio.ready`.
- Ignore errors and close events from sockets no longer registered as active.
- Preserve the existing microphone/system envelope and backend transcription contract.
- Document the ASR provider prerequisite for local runs.

## Acceptance criteria
- Reconnection does not leave stale native PCM consumers running.
- A stale socket cannot set the active recording to error or overwrite its session message.
- Backend audio integration tests continue to pass.
- Native and browser capture behavior remains unchanged outside reconnection lifecycle.

## States and failure behavior
- During reconnection, old PCM sockets are closed before new sockets are registered.
- A current socket error reports a transport failure; an obsolete socket event is ignored.
- Backend ASR failure remains explicit as `transcript.failed` and does not publish an empty definitive transcript.
- Local backend runs with `ASR_PROVIDER=none` intentionally produce no transcript; Docker development configuration uses WhisperX.

## Data and provenance constraints
No audio, transcript, meeting ID or credentials are included in socket lifecycle messages or logs. PCM remains the backend source for ASR and the definitive transcript remains the source of truth.

## Implementation record
- Updated `frontend/src/App.tsx` to close stale native PCM sockets and guard `onerror`/`onclose` handlers by socket identity.
- Confirmed backend continues to persist PCM and finalize ASR through the existing provider abstraction.

## Validation
- Backend audio integration tests: `3 passed`.
- Frontend static diagnostics: no errors in `App.tsx`.
- Full frontend build remains unavailable because `npm` is not installed on this Windows environment.

## Risks and open questions
A real reconnect test with the Windows tray agent and a running backend is still desirable. Native system audio is stored separately and is not included in definitive ASR by design.

## Next action
Run the frontend E2E suite in an environment with Node.js and add a native-agent reconnect scenario.
