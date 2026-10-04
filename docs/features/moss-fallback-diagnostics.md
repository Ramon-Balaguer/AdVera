# MOSS rejection diagnostics and fallback visibility
Status: complete
Last updated: 2026-09-27

## Objective
Make MOSS transcription rejections visible in the worker console and meeting screen, and clearly announce when WhisperX takes over as the definitive transcription fallback.

## Scope
- Preserve MOSS HTTP status and a short sanitized response detail in backend diagnostics.
- Log audio byte count, generated WAV byte count and duration without logging audio or transcript content.
- Publish the existing transcription job state as `fallback` while WhisperX runs.
- Show the fallback state during polling and retain the notice after successful definitive transcription.
- Keep MOSS context and generation limits configurable without increasing production defaults.

## Acceptance criteria
- A MOSS HTTP 400 logs its status and audio metadata without exposing audio bytes, credentials or transcript content.
- The transcription status endpoint reports `stage=fallback` and a safe user-facing message before WhisperX starts.
- The meeting screen displays that MOSS was rejected and that WhisperX fallback is running.
- A completed transcript retains the fallback notice while provenance continues to identify WhisperX as the provider.
- Regression tests cover the provider, reprocessing callback and worker persistence.
- Development MOSS accepts audio files up to 200 MiB through `VLLM_MAX_AUDIO_CLIP_FILESIZE_MB` and durations up to two hours through `VLLM_MAX_AUDIO_DECODE_DURATION_S=7200`; production deployments must set these explicitly and validate capacity.

## Decisions
- Reuse `TranscriptionJob.stage` and `TranscriptionJob.error`; no schema migration is required.
- Do not expose the remote response body in the UI. The UI receives only the sanitized status-based fallback message.
- Raise the development file-size limit to 200 MiB and the decode-duration limit to two hours through `VLLM_MAX_AUDIO_CLIP_FILESIZE_MB` and `VLLM_MAX_AUDIO_DECODE_DURATION_S`. Do not raise `MOSS_MAX_MODEL_LEN` or `MOSS_MAX_NEW_TOKENS`: a long audio request can still exceed the model context window and cause GPU out-of-brain failures. Chunking or a measured capacity test is still required for longer recordings.
- The TorchAudio deprecation warning remains dependency-owned and unrelated to the MOSS HTTP 400.

## Files changed
- `backend/app/moss_asr.py`
- `backend/app/reprocessing.py`
- `backend/app/transcription_worker.py`
- `backend/tests/test_moss_asr.py`
- `backend/tests/test_reprocessing.py`
- `backend/tests/test_transcription_worker.py`
- `frontend/src/App.tsx`
- `docker/compose.dev.yml`
- `.env.example`
- `docs/features/moss-fallback-diagnostics.md`

## Validation
- `backend/tests/test_moss_asr.py`, `test_reprocessing.py`, `test_transcription_worker.py`: 26 passed.
- `frontend`: `npm run build` passed.
- The affected meeting audio was measured at 597,507,414 PCM bytes, approximately 5h11m at 16 kHz mono 16-bit.
- MOSS logs confirmed HTTP 400 but did not provide a body-level reason before this change.
- Compose now renders `VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=200` by default for the development MOSS server.
- Compose now renders `VLLM_MAX_AUDIO_DECODE_DURATION_S=7200` by default for the development MOSS server.
- README, the processing flow and ADR 0007 document the four MOSS/vLLM limits and distinguish upload/decoding limits from model context.

## Risks
- The remote MOSS response detail is logged with a short length limit but remains provider-controlled text.
- The job error field now carries a fallback notice after a successful fallback, so consumers should treat it as a warning when `status=completed`.
- A 200 MiB file can still exceed context or GPU capacity; very long recordings require chunking or a capacity-tested MOSS configuration.

## Next action
Run a controlled MOSS capacity test with synthetic audio and GPU monitoring. If the context limit is confirmed, implement bounded chunking with timestamp offsets rather than raising limits globally.
