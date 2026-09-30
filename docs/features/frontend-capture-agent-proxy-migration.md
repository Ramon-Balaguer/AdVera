# Feature: Frontend capture-agent proxy migration
Status: complete
Last updated: 2026-09-19

## Problem and target user

The frontend still called the removed local capture-agent API at `127.0.0.1:8765`. Although the tray agent connected outbound to the backend, starting a recording from the frontend reported no agent session and fell back to browser microphone capture.

## Desired outcome

The frontend discovers and controls the outbound agent through backend proxy endpoints, so recording uses the registered desktop agent and its microphone/system tracks.

## Smallest useful increment

Replace local capability/session HTTP calls and local level/PCM WebSockets with the backend proxy routes already exposed by `capture_agent.py`.

## Scope

- Frontend capture-agent capability discovery.
- Frontend session start, reuse and stop.
- Frontend per-track level and PCM proxy WebSockets.
- No changes to browser fallback behavior.

## Acceptance criteria

- Frontend capabilities request uses `/api/capture-agent/capabilities`.
- Frontend session start/current/stop uses `/api/capture-agent/sessions` routes.
- Frontend level and PCM sockets use `/ws/capture-agent/{session}/{track}/...`.
- A registered outbound agent can be selected for recording instead of falling back because the local port is absent.
- Frontend build and backend capture-agent E2E remain passing.

## States and failure behavior

If the backend has no registered agent, the existing fallback message remains. If the agent is registered, the frontend waits for the backend proxy session response and attaches per-track sockets through the same origin.

## Data and provenance constraints

No credentials, PCM or diagnostic telemetry is moved into the frontend code. Audio continues to flow through the existing backend audio session and proxy paths.

## Implementation state

Completed: all local `127.0.0.1:8765` capture-agent references in `App.tsx` were replaced with same-origin backend API and WebSocket proxy routes.

## Files changed

- `frontend/src/App.tsx`
- `docs/features/frontend-capture-agent-proxy-migration.md`

## Validation

- Frontend container build: passed (`tsc -b && vite build`).
- Frontend source diagnostics: no errors.
- No local capture-agent URL references remain under `frontend/src`.
- Backend agent E2E: passed.

## Risks and next action

The frontend dev proxy must remain configured for `/api` and `/ws`, as it is in `vite.config.ts`. Restart the tray agent after code changes and start a fresh meeting to validate physical microphone and system loopback traffic.
