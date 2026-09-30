# Feature: Rebuild measured progress inside a track
Status: complete
Last updated: 2026-09-30

## Objective

Show transcription progress while a track is being processed, instead of only at track boundaries. A one-track, 46-minute import sat at 0% for 14 minutes because progress moved only when a whole track finished.

## Scope

- The ASR boundary accepts an optional `on_progress(fraction)` callback.
- The `faster-whisper` provider (ADR 0018) reports measured progress: seconds of speech found by VAD that are already processed, over the total. Language detection covers the first 20%, decoding the rest.
- WhisperX, which exposes no reliable internal progress, keeps advancing per track.
- The worker persists `progress = (track index + 0.9 × track fraction) / tracks`. Diarization and finalizing complete each track.
  - Writes happen at most every 2 s and only when progress grew by at least 1%.
  - Writes are monotonic and fenced by the lease; each one also refreshes it.
  - A fallback restarts the track fraction at zero.
- The meeting page shows the stage, the current track ("pista Sistema, 1 de 2") and the percentage.

## Acceptance criteria

1. A one-track job reports several intermediate values between 0 and 0.9, then 1.0 at completion.
2. Progress never decreases, and is never written without the lease.
3. The number is measured from processed audio, never a timer or a guess.

## Implementation state

Implemented.

## Decisions

`incremental-transcription-worker-progress.md` decided not to estimate progress inside a single ASR call, because the provider exposed no stable progress. The `faster-whisper` provider processes known VAD chunks, so progress inside the call is now a measurement rather than an estimate, and that record's constraint still holds. Its per-track fields (`track`, `processed_tracks`, `total_tracks`) keep their meaning.

## Files changed

- `backend/app/{asr,asr_whisperx,asr_fasterwhisper,transcription_worker}.py`
- `backend/tests/{fakes,test_fasterwhisper}.py`, `backend/tests/integration/test_import_transcription.py`
- `frontend/src/features/meeting/MeetingPage.tsx`, `frontend/tests/e2e/import-transcript.spec.ts`

## Validation

- Unit: over 2 s, 6 s and 2 s of speech, the provider reports `0.04, 0.16, 0.2` during detection and `0.36, 0.84, 1.0` during decoding.
- Integration against real PostgreSQL and Redis: a one-track job persisted at least three intermediate values, all at or below 0.9, monotonic, ending at 1.0.
- E2E: the meeting page shows "pista Sistema (1 de 1) · 37 %" while the job runs.

## Risks

Diarization runs after decoding, inside the last 10% of each track; on long tracks that 10% can take a noticeable time.

## Next action

None.
