# Feature: Stable audio pipeline with provisional and definitive transcript
Status: in progress
Last updated: 2026-09-17

## Problem and target user

The current audio flow can receive PCM and emit transcript events, but it lacks deterministic tests for the separation between provisional and definitive transcript data. Teams using self-hosted AdVera need the original audio preserved, visible provisional feedback, and a trustworthy final transcript without provisional data reaching intelligence.

## Desired outcome

A complete audio session preserves the original PCM, emits provisional transcript segments during capture, processes the complete recording at stop, persists a definitive transcript with provenance, and exposes explicit success or failure states.

## Scope

- Stabilize the WebSocket audio and transcript event contracts.
- Keep PCM signed 16-bit, mono, 16 kHz as the input format.
- Use a provider abstraction with a deterministic fake provider for tests.
- Emit provisional segments without diarization during capture.
- Process the complete original audio for definitive transcription with WhisperX and Pyannote as the production providers.
- Persist only the definitive document atomically.
- Cover frames, provisional events, finalization, provenance and ASR failure behavior with focused tests.

Out of scope: intelligence extraction, embeddings, search, knowledge graph, authentication, GPU optimization, production-grade VAD/stitching, and full relational transcript storage.

## Acceptance criteria

- Starting a meeting emits `audio.ready` and sets the meeting to `recording`.
- Accepted frames receive sequence and byte-count acknowledgements and the original PCM is preserved.
- Provisional segments can be emitted during capture and are never persisted as definitive knowledge.
- Stopping processes the complete audio, persists a definitive transcript with provenance and sets the meeting to `ready`.
- Definitive processing uses the original audio rather than provisional text.
- ASR failure preserves audio, sets the meeting to `failed`, emits `transcript.failed`, and does not publish a ready transcript.
- Tests use a fake provider and do not download models or contain real meeting content.

## States and failure behavior

- Meeting states: `scheduled`, `recording`, `processing`, `ready`, `failed`.
- Transcript states: provisional/partial, definitive, failed.
- Missing meetings reject the WebSocket session.
- Empty audio or unavailable ASR must not be represented as a successful definitive transcript.
- A disconnect must not automatically claim a successful transcript.

## Data and provenance constraints

- The original audio is the input for definitive processing and remains preserved.
- The definitive transcript is the only source allowed for intelligence, embeddings, search and knowledge.
- Provisional transcript is presentation-only.
- Definitive provenance records source audio, SHA-256, provider, model, language and PCM format.
- Tests and logs must not contain secrets, real meeting content or chain-of-thought.

## Dependencies and assumptions

- FastAPI WebSocket, SQLAlchemy, Pydantic and pytest remain the existing backend foundation.
- WhisperX is the production transcription provider and Pyannote is the production diarization provider.
- Model downloads, GPU resources and Hugging Face permissions are operational prerequisites for real inference, not normal test prerequisites.
- Local runs must set `ASR_PROVIDER=whisperx`; the default application setting `none` is an intentional no-ASR mode and returns no transcript segments. The development environment example enables WhisperX explicitly.
- PyTorch 2.6+ uses restricted checkpoint deserialization by default. The WhisperX provider registers the trusted OmegaConf checkpoint types required by its official VAD model before loading it.
- The development Compose service also sets `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` because the installed `pyannote` loader calls `torch.load` without an explicit mode; only trusted official ASR/VAD checkpoints should be used with this setting.
- The existing atomic JSON persistence is retained for this increment.

## Implementation record

## ADRs

- [ADR 0002: Definitive transcript as the intelligence boundary](../adr/0002-definitive-transcript-source-of-truth.md)
- [ADR 0004: Audio capture and live delivery contracts](../adr/0004-audio-capture-and-live-delivery.md)
- [ADR 0005: Independent microphone and system audio tracks](../adr/0005-dual-track-audio-processing.md)

Product Owner brief completed. The WebSocket lifecycle now rejects frames before `start`, handles malformed commands, preserves absolute live timestamps across buffers, and rejects an empty definitive ASR result. Integration tests inject a deterministic fake provider and cover the successful and failed finalization paths.

Files changed:

- `backend/app/audio.py`
- `backend/tests/integration/conftest.py`
- `backend/tests/integration/test_audio_websocket.py`
- `docs/features/stable-audio-transcription-pipeline.md`

## Validation

Focused integration tests and the full backend suite pass. Python compilation passes. Runtime inference with real WhisperX/Pyannote remains pending because it requires model downloads and Hugging Face permissions.

## Risks and open questions

- The current implementation still needs production-grade VAD, overlap handling and transcript stitching.
- The behavior when Pyannote credentials are absent must be decided for production deployment.
- Reconnection and resume after process restart remain outside this increment.

## Next action

Add production-grade VAD, overlap handling, transcript stitching, reconnection/resume behavior and a real WhisperX/Pyannote smoke test. Keep this feature `partial` until the live stability gate is met.
