# Definitive transcription progress
Status: complete
Last updated: 2026-09-19

## Objective
Show the user a trustworthy progress percentage in the Definitive transcript view after recording stops and while definitive ASR is processing.

## Scope
- Emit progress events from the definitive ASR WebSocket workflow.
- Switch the UI to Definitive when capture stops.
- Render staged progress for microphone and system tracks.
- Preserve the definitive transcript as the only source of truth.

## Acceptance criteria
- Stopping a recording selects the Definitive view and shows processing progress.
- Progress is emitted by the backend and remains between 0 and 100 percent.
- The UI shows the current stage and percentage without displaying provisional text as definitive.
- Completion replaces progress with the definitive transcript.
- Definitive ASR failures show the existing failure state and message.

## Implementation state
Implemented. The backend emits staged `transcript.progress` WebSocket events while processing the available microphone and system tracks. The frontend selects Definitivo after capture stops and renders the current stage, track count, progress bar, and percentage until the definitive transcript arrives.

## Decisions
- Progress represents verifiable pipeline stages, not internal WhisperX token progress.
- The two audio tracks are processed sequentially and contribute equally to the staged percentage.
- No speaker identity is inferred from microphone/system track names.

## Files changed
- `backend/app/audio.py`
- `backend/tests/integration/test_audio_websocket.py`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/features/definitive-transcription-progress.md`

## Validation
- Backend modules compile successfully with `compileall`.
- Frontend `npm run build` passes inside `docker-frontend-1`.
- The integration test file was updated to assert progress events, but local pytest execution is blocked because the selected local interpreter does not have `sqlalchemy` installed.

## Risks
The percentage is stage-based because the current ASR provider does not expose internal progress callbacks. A long individual track may appear stationary while its model call runs.

## Next action
Run the integration suite in the project test environment with backend test dependencies installed.
