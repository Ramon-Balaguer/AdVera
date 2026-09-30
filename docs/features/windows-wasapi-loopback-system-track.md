# Feature: Windows WASAPI loopback system track
Status: complete
Last updated: 2026-09-17

## Problem and target user
Meeting participants need the agent to capture playback from conferencing applications and the microphone as independent sources on Windows.

## Desired outcome
The Windows agent exposes a verified `system` track when the default playback device has a WASAPI loopback endpoint, and the frontend can relay that track without mixing it with microphone audio.

## Scope
- Detect the default Windows speaker loopback endpoint with SoundCard.
- Capture system playback as mono 16 kHz signed PCM.
- Expose per-track levels and PCM WebSockets.
- Relay and persist microphone and system tracks separately.

Out of scope: system-track definitive transcription, device selection UI, direct agent-to-backend transport, macOS/Linux loopback and track mixing.

## Acceptance criteria
- `GET /capabilities` reports microphone and system track states independently.
- `POST /sessions` accepts `microphone`, `system` or both and rejects unavailable tracks with a structured 503 response.
- The system levels endpoint returns `source: system` and the system PCM endpoint returns binary PCM frames.
- Backend storage keeps microphone data in `original.pcm` and system data in `system.pcm`.
- Existing microphone-only clients remain compatible through the legacy endpoint aliases.

## States and failure behavior
- `available`: the required device and adapter are present.
- `unsupported`: SoundCard/numpy or the platform adapter is unavailable.
- `device_unavailable`: no suitable loopback endpoint is present.
- `error`: the recorder failed while starting or reading.
- Session creation returns `503 CAPTURE_ADAPTER_UNAVAILABLE` with the unavailable track list; no partial session remains active.

## Data and provenance constraints
Frames are PCM only and are tagged with an `ADVA` envelope byte identifying `microphone` or `system`. The backend does not use provisional data to build definitive intelligence. No raw audio is logged by the agent or tests.

## Dependencies and assumptions
- Windows exposes the default speaker as a SoundCard loopback microphone.
- `SoundCard>=0.4` and `numpy>=2` are installed in the agent environment.
- COM is initialized in threads that access Media Foundation/SoundCard.

## Implementation record
- `SystemAudioCapture` uses SoundCard's loopback microphone and a worker thread.
- Stereo device frames are downmixed to mono before conversion to signed `int16` PCM.
- Frontend waveform and relay state are maintained independently per track.
- Backend routes the envelope to separate files; definitive ASR remains microphone-only by design.

## Validation
- Agent suite: `13 passed`.
- Windows capability probe reports an available LG ULTRAGEAR loopback device.
- FastAPI smoke test created a dual-track session, received a system level event and received a 2048-byte system PCM frame.
- Static diagnostics reported no errors in touched agent, frontend and backend files.

## Risks and open questions
- Some Windows audio drivers do not expose loopback endpoints or may change the default device while a session is active.
- System audio is stored but not yet included in definitive transcription.
- Frontend E2E and the full backend test suite still need to run in the repository's configured environments.

## Next action
Add explicit backend tests for envelope routing and separate track persistence, then decide whether system audio should receive its own transcription workflow.
