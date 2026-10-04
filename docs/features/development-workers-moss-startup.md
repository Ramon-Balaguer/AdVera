# Development Workers and MOSS Startup
Status: complete
Last updated: 2026-09-26

## Product Owner brief

Problem: The development scripts need one explicit workflow for backend workers and the MOSS definitive transcription server.

Target user: AdVera developer running the local stack on Windows or Linux.

Desired outcome: Start infrastructure and workers consistently, with a separate opt-in command for the GPU-backed MOSS server.

Smallest useful increment: Add equivalent `moss` modes to `scripts/dev.ps1` and `scripts/dev.sh`.

In scope: Worker startup and opt-in MOSS Compose startup in both development scripts.

Out of scope: Making MOSS the default provider, production deployment, model evaluation, and API process management.

## Acceptance criteria

- `all` starts PostgreSQL, Redis, `summary-worker`, and `brain-worker` without starting MOSS.
- `moss` starts PostgreSQL, Redis, both workers, the NVIDIA-backed `moss-server` profile, and the local API configured for MOSS definitive transcription.
- Windows and Linux expose equivalent commands.
- The scripts configure the local API with MOSS definitive transcription, WhisperX live/fallback transcription, and the local MOSS URL.
- Existing shutdown and lightweight development modes remain unchanged.

## Implementation state

Implemented.

## Decisions

- MOSS remains opt-in because its model image and GPU runtime are heavyweight.
- The scripts use `http://localhost:8001` for the locally run API to reach the published MOSS port.
- The Compose-internal `http://moss-server:8000` URL remains for API containers.
- The `moss` mode owns the API process after starting the supporting services; it is the one-command local MOSS workflow.

## Files changed

- `scripts/dev.ps1`
- `scripts/dev.sh`
- `docs/features/development-workers-moss-startup.md`

## Validation

- PowerShell parser validation.
- Bash syntax validation is pending on a Linux/WSL environment; Bash is not installed on the current Windows host.
- Both development Compose configurations validate successfully.

## Risks

- MOSS startup still requires a compatible NVIDIA Docker runtime and may take time to download the image and model.
- The local API starts with `ASR_DEFINITIVE_PROVIDER=moss` and `MOSS_BASE_URL=http://localhost:8001` by default.

## Next action

Run `scripts/dev.ps1 -Mode moss` on Windows or `./scripts/dev.sh moss` on Linux. After the MOSS server becomes healthy, exercise a definitive transcription or run the MOSS smoke command from another terminal.
