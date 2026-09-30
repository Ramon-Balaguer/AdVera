# Incremental Development Scripts
Status: complete
Last updated: 2026-09-22

## Product Owner brief

Problem: Full Docker startup rebuilds or starts heavyweight services before a developer can validate a small API or frontend change.

Target user: AdVera developer working locally on Windows or Linux.

Desired outcome: Start only the infrastructure and processes needed for the current development slice.

Smallest useful increment: Provide equivalent scripts with commands for infrastructure, API, frontend, workers, full development support, and shutdown.

In scope: `scripts/dev.sh` and `scripts/dev.ps1`, local API reload, local frontend dev server, Docker PostgreSQL/Redis, optional workers.

Out of scope: Production deployment, secret management, automatic virtual-environment creation, and service orchestration across remote hosts.

Acceptance criteria:

- Linux and Windows expose the same development modes.
- API runs locally with reload while PostgreSQL and Redis remain in Docker.
- Workers are started only when explicitly requested or through the full development mode; the capture agent is started explicitly in its own terminal.
- Shutdown delegates to the existing Compose project.

States and failures: Missing Python falls back to `python3` on Linux or `python` on Windows; missing Docker, dependencies, or database availability fails with the underlying command error.

Data and provenance constraints: Scripts use the local development database and existing meeting-data directory; they introduce no credentials beyond the repository's development defaults.

Assumptions: Docker Compose, Python, Node.js, and frontend dependencies are already installed.

Open questions: Whether a future team workflow should use a process manager such as `tmux` or `just`.

## Implementation state

Implemented for local development.

## Decisions

- Keep PostgreSQL and Redis containerized because the Compose configuration already provides their health checks and persistent volumes.
- Keep API and frontend local for fast reload cycles.
- Keep workers optional because they are not required for endpoint-only changes.
- Add an `agent` mode that runs the tray client with the agent-specific virtual environment when available.

## Files changed

- `scripts/dev.sh`
- `scripts/dev.ps1`

## Validation

Static review completed. Runtime validation requires the developer's local Docker, Python, and Node.js installations.

## Risks

The scripts use the repository's development database credentials and assume local ports `5432`, `6379`, `8000`, and `5173` are available.

## Next action

Run the platform-specific script in `infra` mode, then start `api`, `frontend` or `agent` as needed. The agent mode runs `python -m agent --tray` from the `agent` directory.