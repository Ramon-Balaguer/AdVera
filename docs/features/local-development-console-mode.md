# Feature: Local development console mode
Status: complete
Last updated: 2026-09-25

## Problem and target user

Windows development currently requires separate manual commands for Docker services, API, frontend and capture agent.

## Desired outcome

One command starts infrastructure and workers in Docker while API, frontend and agent run locally in visible consoles at the same time.

## Scope

- Add a `local` development mode to the scripts.
- Keep PostgreSQL, Redis and workers containerized.
- Start API, frontend and agent using local interpreters/processes.
- Open three local consoles on Windows and preserve manual GPU selection for MOSS.

## Acceptance criteria

- `scripts/dev.ps1 local` starts PostgreSQL, Redis and workers in Docker.
- API, frontend and agent are started locally in three separate consoles.
- `-Gpu nvidia|amd` remains available when MOSS is requested.
- The existing individual modes continue to work.
- PowerShell syntax and Compose configuration validate without starting long-lived local processes.

## States and failure behavior

Docker startup failure stops the command before local processes are opened. A missing local executable reports the failing component in its own console. The parent command reports which consoles were opened.

## Data and provenance constraints

This is development orchestration only. It does not change application contracts, meeting data, or secrets.

## Dependencies and assumptions

Windows has PowerShell and Docker Desktop. Separate PowerShell consoles are acceptable when Windows Terminal is unavailable.

## Implementation record

- Added `local` mode to `scripts/dev.ps1` and `scripts/dev.sh`.
- Windows PowerShell starts PostgreSQL, Redis and workers in Docker, then opens local API, frontend and agent consoles.
- Local mode starts the GPU-selected MOSS container and configures the API and transcription worker to use it by default. `-UseMoss` remains accepted for compatibility.

## Validation

- PowerShell parser reports `dev.ps1 syntax OK`.
- `docker compose -f docker/compose.dev.yml config --quiet` passes.
- VS Code diagnostics report no errors in the changed scripts.

## Risks and open questions

The parent process does not supervise or automatically terminate the three local child consoles. Docker services can be stopped with the existing `down` mode.

## Next action

Run the PowerShell command `dev.ps1 local` from the repository root to open the three local consoles, and use `dev.ps1 down` to stop Docker services.
