# Feature: Dual-track playback and live capture metrics
Status: in progress
Last updated: 2026-09-17

## Problem and target user
Users could see only system audio during playback, could not select the provisional transcript, and saw inaccurate real-time frame, byte and duration values.

## Desired outcome
A completed recording preserves microphone and system PCM independently, plays both tracks together, exposes provisional transcript segments while recording, and shows backend-confirmed live metrics.

## Scope
- Persist and report microphone and system track bytes and frame counts.
- Expose each persisted PCM track as a browser-compatible WAV stream.
- Add synchronized playback controls for both tracks.
- Make provisional and definitive transcript views selectable.
- Show monotonic recording duration and confirmed frame/byte metrics.

## Acceptance criteria
- A dual-track session writes `original.pcm` and `system.pcm` independently.
- `audio.received` and `audio.stopped` report total and per-track metrics.
- Both audio endpoints return playable WAV data.
- The provisional transcript tab is enabled and displays `transcript.provisional` events.
- The duration clock advances during capture and survives reconnection from backend metrics.
- Each waveform shows a synchronized playback position line and keeps it visible when paused.
- Playback and capture use separate controls: play is enabled only with persisted audio, while the red REC control starts or stops capture.
- Provisional and definitive ASR process both persisted tracks when system audio is available.
- Known subtitle watermark text from Amara is discarded before provisional emission or definitive persistence.
- Playback URLs are refreshed after persistence so an initial 404 from empty in-progress tracks cannot poison the audio elements.
- Backend focused and full tests pass.

## States and failure behavior
Missing system audio returns a clear unavailable response from its endpoint; microphone playback remains independently persisted. A failed audio stream does not mark the transcript definitive. If frontend build tooling is unavailable, QA reports the feature as unverified rather than approving it.

## Data and provenance constraints
Microphone and system tracks remain separate. Definitive ASR continues to use the microphone source of truth. Tests use synthetic PCM only and do not log real meeting audio or credentials.

## Dependencies and assumptions
The capture agent sends `ADVA` envelopes with track `1` for microphone and `2` for system. PCM is mono, signed 16-bit, 16 kHz.

## Implementation record
- Added per-track metrics and persisted cursors in `backend/app/audio.py`.
- Added WAV playback endpoints in `backend/app/meetings.py`.
- Added frontend playback, transcript view selection, duration and metrics display in `frontend/src/App.tsx`.
- Added synchronized playback position indicators over both waveforms in `frontend/src/App.tsx` and `frontend/src/styles.css`.
- Separated persisted playback from capture controls and added the red REC state in `frontend/src/App.tsx` and `frontend/src/styles.css`.
- Added track-aware provisional and definitive ASR processing in `backend/app/audio.py`, `backend/app/asr.py`, `backend/app/live_pipeline.py`, `backend/app/contracts.py` and `backend/app/transcripts.py`.
- Added integration coverage for both tracks and WAV responses.

## Validation
- Backend integration audio tests: `4 passed`.
- Backend full suite: `17 passed`.
- Frontend build: `npm run build` passed in the frontend container.
- Mobile layout verification confirmed each track label remains adjacent to its waveform.
- Backend syntax compilation passed with `python -m compileall -q backend/app backend/tests`.
- The dual-track integration test now asserts definitive segments from both `microphone` and `system`.

## Risks and open questions
- Browser playback starts both elements concurrently but device scheduling can still introduce minor drift over long recordings.
- System track playback is unavailable when the agent did not capture a system track.
- Browser-level playback verification is partial: the current meeting has no system track, and the shared page entered an active capture state before the playback check.
- Pytest execution is currently blocked because `pytest` is not installed in the local or API container environments.
- Current browser verification confirmed both persisted tracks play simultaneously through the frontend proxy.
- Direct ASR artifact checks recognize both Amara variants and preserve normal transcript text.

## Next action
Run the frontend E2E suite with a completed dual-track recording, then perform the final QA decision.
