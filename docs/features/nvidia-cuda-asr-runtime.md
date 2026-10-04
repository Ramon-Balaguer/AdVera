# Feature: NVIDIA CUDA runtime for ASR
Status: complete
Last updated: 2026-09-18

## Objective
Allow WhisperX live and definitive transcription to run on an NVIDIA GPU, initially targeting an RTX 3090, while keeping CPU as the default and leaving a clear runtime boundary for future AMD/ROCm support.

## Scope
- Validate requested CUDA availability before loading WhisperX.
- Reject the known incompatible `cuda` plus `int8` combination with an actionable error.
- Add `docker/compose.nvidia.yml` with `gpus: all`, `ASR_DEVICE=cuda` and `ASR_COMPUTE_TYPE=float16`.
- Keep `docker/compose.dev.yml` on CPU with `int8` for CI and hosts without GPU.
- Preserve independent live and definitive model selection.

## Acceptance criteria
- CPU Compose remains unchanged and continues using `cpu`/`int8`.
- NVIDIA Compose requests all available GPUs and configures `cuda`/`float16`.
- A CUDA provider fails clearly if `torch.cuda.is_available()` is false instead of silently falling back to CPU.
- A CUDA provider rejects `int8` before WhisperX model loading.
- Future ROCm support can use a separate image and dependency set without changing audio, transcript or model-selection contracts.

## Deployment

Requirements for the RTX 3090 path:

- Docker Desktop with the WSL2 engine enabled.
- Current NVIDIA Windows driver with Docker GPU support.
- A Docker installation that supports the Compose `gpus` service property.
- Sufficient VRAM for the selected live and definitive models.

Start with:

```powershell
docker compose -f docker/compose.dev.yml -f docker/compose.nvidia.yml up -d --build api
```

The resulting API configuration is `ASR_DEVICE=cuda` and `ASR_COMPUTE_TYPE=float16`. A host without a working NVIDIA runtime should fail provider initialization with a CUDA-unavailable error.

## Data and provenance constraints
GPU execution does not alter persisted PCM sources, transcript contracts, artifact filtering, or definitive provenance. No GPU diagnostics include meeting content or secrets.

## Decisions
- CPU remains the safe default in the base Compose file.
- NVIDIA is an explicit Compose override, not automatic fallback or autodetection.
- AMD/ROCm is intentionally not included in the CUDA image. It will use a separate compatible image and dependency matrix later; PyTorch ROCm commonly exposes the device through the `cuda` API, but that must be verified per supported stack.

## Files changed
- `backend/app/asr.py`
- `backend/tests/test_asr.py`
- `.env.example`
- `docker/compose.nvidia.yml`

## Validation
- `python -m compileall -q backend/app backend/tests` passed.
- NVIDIA smoke test passed on the RTX 3090: `torch 2.8.0+cu128`, CUDA `12.8`, `torch.cuda.is_available()=True`, and `NVIDIA GeForce RTX 3090` was detected.
- WhisperX `tiny` loaded with `cuda`/`float16` and ran a synthetic PCM window with CUDA brain allocated.
- The active API health endpoint remains available with the NVIDIA override.

## Risks and next action
The full CUDA image rebuild may download large PyTorch/NVIDIA packages. The RTX 3090 live-model smoke test passes; the remaining release check is a short real capture covering both live and definitive models.
