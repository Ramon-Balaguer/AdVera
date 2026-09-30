# TorchCodec ASR migration
Status: complete
Last updated: 2026-09-19

## Objective
Migrate the WhisperX/Pyannote runtime to the TorchCodec-based audio stack so supported audio decoding does not rely on deprecated TorchAudio backend discovery.

## Scope
- Upgrade WhisperX to 3.8.6 and Pyannote Audio to 4.x.
- Add TorchCodec and FFmpeg to the API runtime.
- Update the diarization model and WhisperX token argument for the new API.
- Keep warnings visible; do not suppress dependency warnings.

## Acceptance criteria
- The API image installs `whisperx 3.8.6`, `pyannote.audio 4.0.7` and `torchcodec 0.7.0`.
- FFmpeg is available in the API image and `import torchcodec` succeeds.
- The ASR-focused tests and Python compilation pass.
- No application-owned TorchAudio decoder remains to migrate.

## Implementation state
Implemented and runtime-verified in the development API container. A full model inference smoke test still requires a configured Hugging Face token and accepted model terms.

## Decisions
- Use `pyannote/speaker-diarization-community-1`, the Pyannote 4 compatible community pipeline.
- Use `token=` instead of the removed `use_auth_token=` argument.
- Pin TorchCodec to `>=0.6,<0.8` to match WhisperX 3.8.6 compatibility guidance.
- Install Debian FFmpeg because TorchCodec loads its shared decoder libraries through FFmpeg.

## Files changed
- `backend/pyproject.toml`
- `backend/Dockerfile`
- `backend/app/asr.py`
- `backend/app/config.py`
- `docker/compose.dev.yml`

## Validation
- `agent/.venv/Scripts/python.exe -m pytest backend/tests/test_asr.py -q` -> 5 passed.
- `python -m compileall app/asr.py app/config.py tests/test_asr.py` -> passed.
- `docker compose -f docker/compose.dev.yml config --quiet` -> passed.
- API image build -> passed.
- Runtime check -> `/usr/bin/ffmpeg`, TorchCodec 0.7.0 and `import torchcodec` succeeded.

## Risks
- Pyannote 4 uses a newer diarization pipeline and requires model access/terms acceptance.
- Full definitive transcription remains unverified until `HF_TOKEN` is configured and a real model run is performed.
- The existing trusted-checkpoint compatibility setting remains unchanged and should be reviewed separately.

## Next action
Run one real definitive transcription with a configured Hugging Face token and verify diarization output and alignment quality.
