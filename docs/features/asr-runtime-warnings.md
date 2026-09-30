# ASR runtime warnings
Status: complete
Last updated: 2026-09-19

## Objective
Review WhisperX, Pyannote, TorchAudio, and SpeechBrain runtime warnings and keep CUDA diarization reproducible.

## Scope
- Verify the installed ASR dependency versions.
- Make the TF32 reproducibility policy explicit for CUDA inference.
- Document non-fatal dependency deprecations and the trusted-checkpoint compatibility workaround.
- Avoid global warning suppression.

## Acceptance criteria
- CUDA ASR disables TF32 for matmul and cuDNN before WhisperX/Pyannote inference.
- CPU behavior is unchanged.
- TorchAudio deprecation warnings remain visible and are documented as dependency-owned.
- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` remains limited to trusted official checkpoints and is documented as temporary.
- Existing ASR runtime tests continue to pass.

## Implementation state
Implemented. CUDA initialization now explicitly disables TF32 matmul and cuDNN operations before WhisperX inference.

## Decisions
- Prefer reproducibility over the small potential TF32 speedup for diarization.
- Do not migrate TorchAudio/Pyannote in this scoped change because that requires coordinated dependency and model validation.
- Do not filter warnings globally.

## Files changed
- `backend/app/asr.py`
- `backend/tests/test_asr.py`
- `docs/features/asr-runtime-warnings.md`

## Validation
- Focused ASR tests: `5 passed`.
- `compileall` passed for the provider and tests.
- The API container has `torch 2.8.0+cu128`, `torchaudio 2.8.0+cu128`, `pyannote 3.4.0`, and CUDA available.

## Risks
Disabling TF32 can reduce CUDA throughput slightly. Upgrading TorchAudio/Pyannote later may require a separate compatibility test with WhisperX VAD and diarization.

## Next action
Plan a separate coordinated WhisperX/Pyannote upgrade to remove the TorchAudio deprecation at the dependency boundary; do not suppress it globally.
