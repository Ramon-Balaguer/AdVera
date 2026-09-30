# Feature: Outbound capture agent WebSocket
Status: complete
Last updated: 2026-09-19

## Problem and target user

The capture agent currently accepts inbound HTTP/WebSocket connections, which requires opening a port on the user's machine when the agent, backend and frontend are separate.

## Desired outcome

The agent connects outbound to the backend and no longer listens on a local HTTP port.

## Scope

- Agent-to-backend WebSocket registration, capabilities, session control, levels and PCM.
- Backend proxy endpoints for frontend control and stream forwarding.
- Frontend migration away from `127.0.0.1:8765`.
- Explicit connection and capture errors without logging audio or credentials.

## Acceptance criteria

- The agent does not start Uvicorn or bind a local port.
- The agent opens an outbound WebSocket to the configured backend.
- Frontend capture-agent requests are served by the backend.
- Microphone and system PCM remain separate and preserve the existing audio WebSocket envelope.
- Agent and backend tests cover registration, commands and disconnected-agent behavior.

## States and failure behavior

Disconnected agents produce an unavailable response; capture start fails explicitly and the frontend may use its browser fallback. A lost agent channel closes active proxy streams and does not silently mark a recording as complete.

## Data and provenance constraints

PCM is transported only over the authenticated backend WebSocket and is not logged. Track, session and sequence metadata remain explicit.

## Dependencies and assumptions

The backend URL is configured in the agent. The initial protocol uses a configurable agent id/token; TLS is recommended for remote deployments.

## Implementation record

The backend now owns the agent connection and proxies capabilities, session control, levels and PCM. The agent uses an outbound WebSocket client and the tray no longer starts Uvicorn. The frontend routes all agent operations through the backend.

Files changed:

- `agent/agent/remote.py`
- `agent/agent/main.py`
- `agent/agent/tray.py`
- `agent/agent/config.py`
- `agent/agent/wizard.py`
- `agent/pyproject.toml`
- `backend/app/capture_agent.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `frontend/src/App.tsx`
- `agent/README.md`
- `docs/features/outbound-capture-agent-websocket.md`

## Validation

Agent tests: 16 passed. Backend capture-agent tests and contracts: 4 passed. Static diagnostics are clean for changed Python/TypeScript files. Frontend build was not run because `npm` is unavailable in the environment.

## Risks and open questions

Token provisioning UI and reconnect buffering need a later hardening pass. The backend accepts an optional `CAPTURE_AGENT_TOKEN`; when configured, the outbound WebSocket must send the matching bearer token. The legacy local HTTP mode is removed by this change.

## Next action

Install Node.js/npm and run the frontend build and E2E checks.