# Post-recording failure classification
Status: complete
Last updated: 2026-09-22

## Objective
Prevent a successful audio capture from being presented as a capture failure when definitive transcription fails, and make concurrent session-manifest writes safe on Windows.

## Scope
- Keep concurrent `audio_session.json` writes atomic and temporary-file cleanup deterministic.
- Emit a stable, sanitized failure code and user-facing reason for definitive ASR failures.
- Show `TRANSCRIPCIÓN` instead of `CAPTURA` after audio is persisted and finalization fails.

## Acceptance criteria
- Concurrent manifest writes leave valid JSON and no temporary files.
- Definitive failures remain retryable and preserve PCM audio.
- Failure events do not expose raw provider exceptions, paths, tokens, or meeting content.
- The meeting view distinguishes definitive transcription failure from capture failure.
- Existing successful and live-transcription flows remain unchanged.

## Implementation state
Implemented.

## Decisions
- Keep the database meeting status as `failed` for compatibility; use the WebSocket failure stage for the user-facing distinction.
- Use controlled failure codes and messages while logging the exception type and stack trace server-side.
- Preserve the existing process-local manifest lock and unique same-directory temporary files.

## Files changed
- `backend/app/audio.py`
- `backend/tests/test_audio.py`
- `backend/tests/integration/test_audio_websocket.py`
- `frontend/src/App.tsx`

## Validation
- Focused backend audio tests pass (`8 passed`).
- Frontend source has no diagnostics in the changed file.
- Frontend build remains pending because the current terminal resolves npm from a package without the frontend build script.

## Risks
- A meeting loaded after reconnect does not yet persist the failure stage in the meeting API, so the header distinction applies to the active WebSocket session.
- The lock is process-local; deployments with multiple API worker processes still need a shared persistence coordinator if they write the same meeting session concurrently.

## Next action
Run the frontend build from the frontend package directory and perform the independent QA/security review.