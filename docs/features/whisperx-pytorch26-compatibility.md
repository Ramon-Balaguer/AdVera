# Feature: WhisperX compatibility with PyTorch 2.6+
Status: complete
Last updated: 2026-09-17

## Problem and target user
The API accepted audio but did not produce a transcript because WhisperX failed while loading the bundled pyannote VAD checkpoint with PyTorch's restricted checkpoint deserialization.

## Desired outcome
The development API initializes the configured WhisperX provider and can proceed from persisted PCM to definitive transcript events.

## Scope
- Diagnose the PyTorch 2.6 `weights_only` failure in the WhisperX/pyannote dependency chain.
- Allow trusted official ASR/VAD checkpoints in the development Compose service.
- Keep the provider abstraction and test fake provider unchanged.

Out of scope: model upgrades, GPU optimization, arbitrary checkpoint trust, or changing transcript contracts.

## Acceptance criteria
- The API container starts with `ASR_PROVIDER=whisperx`.
- Creating the configured WhisperX provider completes without the OmegaConf unpickling error.
- Existing backend audio integration tests continue to pass.
- The frontend can receive the existing `transcript.provisional`, `transcript.definitive` and `transcript.failed` events.

## States and failure behavior
- Provider initialization failure remains a `transcript.failed` event during a live session.
- `ASR_PROVIDER=none` remains an intentional no-ASR mode and does not generate transcript segments.
- The development Compose service enables unrestricted checkpoint loading only for trusted official model assets.

## Data and provenance constraints
No transcript, audio, secret or meeting content is logged by the compatibility change. Definitive transcription still uses persisted microphone PCM and the existing provenance document.

## Dependencies and assumptions
The development service uses WhisperX and pyannote assets installed from the backend ASR extra. The checkpoint assets are trusted official dependencies.

## Implementation record
- Registered OmegaConf checkpoint classes before WhisperX model initialization.
- Set `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` in `docker/compose.dev.yml` because the installed pyannote loader does not pass `weights_only` explicitly.
- Recreated the API container with the current source and verified `ASR_READY WhisperXProvider`.

## Validation
- Backend suite: `16 passed`.
- Container provider smoke test: `ASR_READY WhisperXProvider`.
- Docker API and frontend services rebuilt/restarted successfully.
- Frontend source diagnostics remain clean.

## Risks and open questions
The environment variable allows full checkpoint unpickling and must not be used with untrusted model files. The container reports compatibility warnings because the bundled VAD checkpoint was trained against older pyannote and torch versions; a future dependency pin or model upgrade may remove them.

## Next action
Run a real short Spanish recording through the rebuilt frontend and confirm the definitive event and transcript document are visible in the meeting UI.
