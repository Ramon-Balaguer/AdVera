# Feature: Drop WhisperX
Status: in progress
Last updated: 2026-10-06

## Objective
Remove WhisperX, which the operator does not use: the definitive transcript comes from faster-whisper (ADR 0018) and WhisperX only stayed as the default of the "live" and "fallback" roles. It also kept the backend image on Python 3.12: recent WhisperX versions do not support 3.14, so `pip` went back to an old one that pins `ctranslate2==4.4.0`, which has no 3.14 wheel.

## Scope
- `asr_whisperx.py` and the `whisperx` provider of `build_engine` are deleted; `faster-whisper` is the only provider (`MOSS` stays opt-in and unavailable).
- The `asr` extra declares `faster-whisper>=1.0` instead of `whisperx>=3.1`. `ctranslate2` stays: it is faster-whisper's engine.
- `ASR_LIVE_PROVIDER` defaults to `faster-whisper` (nothing reads it today) and `ASR_FALLBACK_PROVIDER` to empty: with one provider there is no fallback, and a job whose definitive provider fails ends as `ASR_FAILED`. The fallback mechanism itself is unchanged and is still tested with a second, scripted provider.
- `.env.example` and `docker/compose.dev.yml` follow; the NVIDIA override comment names faster-whisper.
- Tests: the WhisperX unit test is gone, the scripted engines are named `faster-whisper`.

## Decisions
- A deployment that still sets `ASR_FALLBACK_PROVIDER=whisperx` keeps working until a definitive failure, when the fallback raises `UNKNOWN_PROVIDER` and the job fails with `ASR_FAILED`. Clear the variable.
- Historical records (ADRs and earlier feature records) keep their WhisperX text: they describe what was true then.

## Validation
- Backend: ruff, format and the full suite with PostgreSQL and Redis; coverage 91.9% (it rises because the 55 uncovered statements of `asr_whisperx.py` are gone).
- Image: on Python 3.14.7 (the base image of `backend/Dockerfile`) the `asr,brain` worker image builds, weighs 10.8 GB instead of 13.2 GB, and imports `faster_whisper` 1.2.1, `ctranslate2` 4.8.2, `torch` 2.14.1 (CUDA 13), `speechbrain` and `sentence_transformers`; `build_engine("faster-whisper", ...)` returns the provider. With WhisperX it did not build on 3.14.

## Next action
Run a real transcription and a diarization on the GPU with the new worker image before publishing it (the CPU smoke test above does not load a model).
