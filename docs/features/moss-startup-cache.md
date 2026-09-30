# Feature: MOSS Startup Cache and Prefetch
Status: complete
Last updated: 2026-09-30

## Product Owner brief

Problem: MOSS startup spends significant time loading the checkpoint and recompiling vLLM artifacts after the container is recreated.

Target user: AdVera developer running the local GPU-backed MOSS service.

Desired outcome: Reduce repeat startup time without changing the MOSS API contract or model behavior.

Smallest useful increment: Enable safetensors prefetch and persist vLLM's compilation cache in Docker Compose.

In scope: Local Compose startup configuration and operational documentation.

Out of scope: Model quantization, context-window changes, eager execution, and production deployment.

## Acceptance criteria

- MOSS starts with the vLLM safetensors prefetch strategy by default.
- `/root/.cache/vllm` survives MOSS container recreation through a named volume.
- The MOSS model cache remains persistent.
- The Compose configuration validates successfully.

## Implementation state

Implemented.

## Decisions

- The prefetch strategy is configurable through `MOSS_SAFETENSORS_LOAD_STRATEGY` and defaults to `prefetch`.
- vLLM's cache is stored in a separate named volume so it can be removed independently from the Hugging Face model cache.
- The volume is intentionally retained by normal `docker compose down`; `docker compose down -v` removes it and will require recompilation.

## Files changed

- `docker/compose.dev.yml`
- `docs/features/moss-startup-cache.md`

## Validation

- `docker compose -f docker/compose.dev.yml config --quiet`
- `git diff --check`

## Risks

- The first startup after this change still performs compilation and prefetch setup.
- Compiled artifacts may be invalidated by changes to the vLLM image, model, driver, or relevant runtime configuration.
- Prefetch uses additional host RAM and disk I/O during checkpoint loading.

## Next action

Recreate MOSS once, then restart it and compare the time until `GET /health` returns 200. Keep the named volume when stopping the stack.