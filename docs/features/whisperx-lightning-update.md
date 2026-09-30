# Feature: Actualizacion de WhisperX y Lightning
Status: complete
Last updated: 2026-09-19

## Objective

Make the current latest WhisperX and Lightning releases explicit and reproducible while preserving the working ASR container build.

## Scope

- Pin WhisperX to the latest available release, `3.8.6`.
- Pin Lightning to the latest available release, `2.6.6`.
- Keep the trusted checkpoint migration compatible with PyTorch 2.6+.
- Rebuild the API image and verify the effective runtime versions.

## Acceptance criteria

- `pyproject.toml` explicitly declares WhisperX `3.8.6` and Lightning `2.6.6` for the ASR extra.
- The API image builds successfully.
- WhisperX checkpoint migration completes during the build.
- The running container reports WhisperX `3.8.6`, Lightning `2.6.6`, and a working Torch runtime.
- Focused ASR tests pass.

## Implementation state

Product Owner discovery brief recorded. Implementation complete.

## Decisions

- PyPI currently reports WhisperX `3.8.6` and Lightning `2.6.6` as the latest releases.
- Pin only the requested top-level packages; their compatible Torch and pyannote dependencies remain resolved by the package metadata.
- Scope `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` to the trusted checkpoint migration command in the Dockerfile; the Compose runtime setting remains for the pyannote loader path.

## Files changed

- `backend/pyproject.toml`
- `backend/Dockerfile`
- `docs/features/whisperx-lightning-update.md`

## Validation

- `python -m pytest tests/test_asr.py tests/test_live_pipeline.py -q`: `9 passed`.
- `docker compose -f docker/compose.dev.yml build api`: completed successfully.
- Rebuilt image versions: WhisperX `3.8.6`, Lightning `2.6.6`, Torch `2.8.0`.
- Running API service is healthy.
- Container provider smoke test: `ASR_READY WhisperXProvider`.

## Risks and next action

WhisperX transitively controls a large CUDA/ASR dependency set. The latest available WhisperX release remains `3.8.6`, so this change makes the current compatible stack reproducible rather than moving to a newer WhisperX major release. The trusted checkpoint migration still requires the scoped PyTorch compatibility override.

Next action: validate a short real recording through the rebuilt frontend and confirm the definitive transcript event.
