# Audio WebSocket close safety
Status: complete
Last updated: 2026-09-19

## Objective
Prevent unhandled Starlette errors when live ASR finishes or fails after the audio WebSocket has already closed.

## Scope
- Guard live provisional and failure event sends.
- Treat a send race after close as an expected disconnect.
- Log skipped sends with safe event metadata.
- Add a regression for Starlette's close-state RuntimeError.

## Acceptance criteria
- A live ASR error after WebSocket close does not produce an unhandled RuntimeError.
- Events still reach connected clients normally.
- Closed-channel sends are logged without audio or transcript content.
- The existing `transcript.failed` contract remains unchanged while the socket is connected.

## Implementation state
Implemented. All audio WebSocket event sends now use a guarded helper that catches `RuntimeError` and `WebSocketDisconnect` and records the skipped event.

## Decisions
- The close race is treated as a transport lifecycle event, not an ASR failure to report to a disconnected client.
- The guard is applied at every audio event boundary, including capture, live summary, progress, definitive transcript, and failure events.

## Files changed
- `backend/app/audio.py`
- `backend/tests/test_audio.py`
- `docs/features/audio-websocket-close-safety.md`

## Validation
- `compileall` passes for the backend module and regression.
- The focused test is present but local execution is blocked because the selected interpreter lacks `sqlalchemy`.

## Risks
A client that disconnects immediately after a live ASR failure will not receive `transcript.failed`, which is expected because the channel is already closed.

## Next action
Run the backend test suite in the project environment with its dependencies installed.
