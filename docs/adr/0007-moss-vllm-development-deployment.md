# ADR 0007: MOSS vLLM Development Deployment

## Status

Accepted for local development and canary evaluation; production enablement pending.

## Context

MOSS requires GPU serving and is not part of the backend process. The vLLM OpenAI-compatible server is the current local serving boundary, but the base image lacks the optional audio dependency required by vLLM's audio loader.

## Decision

Run MOSS as an opt-in Docker Compose service, exposed to the host on port 8001 and to the API as `moss-server:8000`. Build a small derived image from `vllm/vllm-openai` for NVIDIA or `vllm/vllm-openai-rocm` for AMD, selected explicitly by the matching Compose override, and install `soundfile`. Use a healthcheck compatible with the image's `python3` runtime. Keep the image, model, endpoint, token, timeouts and audio limits configurable through environment variables. The local development defaults are `VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=200`, `VLLM_MAX_AUDIO_DECODE_DURATION_S=7200`, `MOSS_MAX_MODEL_LEN=65536` and `MOSS_MAX_NEW_TOKENS=65536`.

MOSS remains disabled by default and requires a synthetic smoke test plus a licensed/public-corpus canary before production use. Logs must not contain audio or transcript payloads.

## Consequences

- Local deployment fixes vLLM audio loading without modifying the API client contract.
- GPU, model cache, vendor runtime compatibility and startup latency are operational prerequisites.
- File-size (`200 MiB`) and decoded-duration (`2 hours`) limits are separate from model context and generation limits; exceeding context or GPU capacity can still require chunking.
- The base vLLM image is an external dependency and should eventually be pinned and upgraded deliberately.
- A failed MOSS service must leave the explicit WhisperX fallback available.

## Validation and rollback

Validate Compose config, image build, `soundfile` import, `/health`, synthetic transcription smoke and fallback behavior. Rollback by setting `MOSS_SERVER_IMAGE` to a known compatible image and selecting WhisperX as the definitive provider.

## Related records

- `docs/features/moss-definitive-provider.md`
- `docs/features/development-workers-moss-startup.md`
- `docs/features/nvidia-cuda-asr-runtime.md`
- `docs/features/vllm-amd-nvidia-runtime-selection.md`
- `docs/features/moss-fallback-diagnostics.md`
