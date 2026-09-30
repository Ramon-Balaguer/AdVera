# vLLM AMD and NVIDIA Runtime Selection
Status: complete
Last updated: 2026-09-25

## Objective

Select the vLLM base image and container GPU runtime explicitly for the host GPU: `vllm/vllm-openai` for NVIDIA and `vllm/vllm-openai-rocm` for AMD.

## Scope

- Parameterize the MOSS vLLM image in `docker/moss.Dockerfile`.
- Add an AMD ROCm Compose override alongside the existing NVIDIA override.
- Allow the development scripts to select `nvidia` or `amd` for MOSS.
- Preserve the MOSS endpoint, model, healthcheck, cache, and API contract.

Out of scope: ASR provider behavior, transcript contracts, model tuning, production certification, and automatic GPU detection.

## Acceptance Criteria

- NVIDIA builds from `vllm/vllm-openai` and uses the NVIDIA Compose GPU runtime.
- AMD builds from `vllm/vllm-openai-rocm` and exposes the ROCm device nodes required by vLLM.
- `scripts/dev.ps1 moss -Gpu amd` and `MOSS_GPU=amd ./scripts/dev.sh moss` select the AMD override.
- The default development path remains NVIDIA-compatible.
- Both merged Compose configurations validate successfully without changing the MOSS HTTP contract.

## Implementation State

Implemented for local development and canary evaluation.

## Decisions

Runtime selection is explicit rather than silently autodetected. CUDA and ROCm overrides remain separate so their device configuration and dependencies cannot be mixed.

## Files Changed

- `docker/moss.Dockerfile`
- `docker/compose.nvidia.yml`
- `docker/compose.amd.yml`
- `scripts/dev.ps1`
- `scripts/dev.sh`
- `docs/adr/0007-moss-vllm-development-deployment.md`
- `docs/meeting-processing-flow.md`

## Validation

Both merged Compose configurations pass `docker compose config`. Runtime image pulls, GPU driver compatibility, and synthetic transcription remain hardware-dependent checks.

## Risks

The ROCm image, host driver, GPU architecture, and model support must be compatible. AMD hardware validation is required before production use.

## Next Action

Validate the AMD image and MOSS synthetic smoke test on a ROCm host before production enablement.
