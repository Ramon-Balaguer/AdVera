# Feature: VAD, windowing and transcript stitching
Status: in progress
Last updated: 2026-09-17

## Problem and target user

The live audio path currently transcribes and clears each buffer, so adjacent ASR windows have no overlap and can produce duplicated or clipped text. Meeting participants need provisional transcript feedback that remains continuous while the original audio stays authoritative.

## Desired outcome

Use configurable voice-activity detection and overlapping PCM windows during live capture, then stitch ASR segments into a deduplicated provisional stream with absolute timestamps.

## Scope

- RMS-based VAD for PCM signed 16-bit mono audio.
- Configurable window and overlap durations.
- Window buffering with bounded overlap and absolute offsets.
- Deduplication of overlapping ASR segments by time and normalized text.
- Live WebSocket integration with provisional events.
- Deterministic unit tests using fake ASR segments.

Out of scope: production-grade neural VAD, definitive transcript changes, PostgreSQL segment persistence, intelligence, speaker identity and reconnection after process restart.

## Acceptance criteria

- Silent windows are not sent to the live provider.
- Active windows include the configured overlap and expose their absolute offset.
- Repeated text from overlapping windows is emitted once by the stitcher.
- Provisional event timestamps remain absolute across windows.
- The definitive pipeline still processes the complete original audio independently.
- Tests do not download models or contain real meeting content.

## States and failure behavior

- Empty or silent live windows are skipped without failing the meeting.
- Invalid PCM alignment is ignored or rejected explicitly without corrupting the audio file.
- Provider failures emit a retryable transcript failure while preserving the original audio.
- Definitive transcription remains the only source for intelligence.

## Data and provenance constraints

- Original PCM is always persisted before live processing.
- Provisional segments are presentation-only and never become definitive knowledge.
- Segment timestamps are relative to the original recording timeline.
- No secrets, real meeting content or chain-of-thought are stored in tests or logs.

## Dependencies and assumptions

- Input remains PCM signed 16-bit, mono, 16 kHz.
- WhisperX remains the production live provider and Pyannote remains part of definitive processing.
- A simple RMS VAD is sufficient for this first executable increment; a neural VAD can replace it behind the same boundary later.

## Implementation record

Product Owner brief recorded. Implementation adds isolated live pipeline primitives and connects them to the existing audio WebSocket without changing definitive full-audio processing.

Files changed:

- `backend/app/live_pipeline.py`
- `backend/app/audio.py`
- `backend/app/config.py`
- `backend/tests/test_live_pipeline.py`
- `backend/tests/integration/conftest.py`
- `backend/tests/integration/test_audio_websocket.py`
- `docker/compose.dev.yml`
- `docs/features/vad-windowing-and-transcript-stitching.md`

## Validation

The focused live pipeline and WebSocket tests pass. The full backend suite passes and Python compilation passes. Real model latency and VAD calibration remain pending.

## Risks and open questions

- RMS thresholding is sensitive to microphone gain and background noise.
- Stitching based on normalized text and timestamps is conservative and may need language-aware matching.
- Real-time latency and GPU usage still require a model-backed smoke test.

## Next action

Run a real WhisperX/Pyannote smoke test with Spanish audio, calibrate `VAD_THRESHOLD`, `LIVE_WINDOW_SECONDS` and `LIVE_OVERLAP_SECONDS`, and add reconnection/resume behavior in a separate feature.
