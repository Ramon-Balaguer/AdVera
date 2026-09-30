# Feature: Frontend audio reconnection E2E coverage
Status: complete
Last updated: 2026-09-17

## Problem and target user

The frontend reconnection path can regress at the browser boundary even when TypeScript and backend tests pass. The team needs a repeatable check that exercises the recording UI, microphone setup, WebSocket lifecycle and resume handshake.

## Desired outcome

A Playwright test verifies that a recording starts, survives a WebSocket interruption and reconnects with the backend session cursor without requiring a real microphone, ASR model or database.

## Scope

- Playwright configuration for the Vite frontend.
- Browser-level test for initial recording and reconnect handshake.
- Deterministic browser fakes for microphone/audio processing and WebSocket transport.
- Test script suitable for local and CI execution.

Out of scope: real-device microphone permissions, browser compatibility matrix, model latency and backend persistence validation already covered by integration tests.

## Acceptance criteria

- The test starts the Vite app and loads a meeting.
- The first socket receives a fresh `start` command.
- The recording UI reaches the active capture state.
- A transport interruption triggers reconnecting state.
- The next socket receives `resume: true`, the same `session_id` and the latest `next_sequence`.
- The UI returns to active capture after `audio.ready` with `resumed: true`.
- The test passes in a clean Chromium installation without external services.

## States and failure behavior

- Missing browser binary: setup instructions must identify `npx playwright install chromium`.
- Unexpected handshake: the test fails with the received payload.
- Reconnect timeout: the test fails while the UI remains in recovery state.

## Data and provenance constraints

- Test meeting metadata and transcript text are synthetic.
- No credentials, production endpoints or real meeting content are used.
- The test validates the client protocol, not definitive transcript generation.

## Dependencies and assumptions

- Node dependencies are installed in `frontend`.
- Vite serves the app on an isolated test port.
- Browser APIs are mocked only at the test boundary.

## Implementation record

Product Owner brief recorded. Added Playwright configuration and a deterministic Chromium test under `frontend/tests/e2e`. The test mocks only browser-boundary APIs, forces a WebSocket interruption after capture begins, waits for the recovered UI and verifies the resume command contract.

Files changed:

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/playwright.config.ts`
- `frontend/tests/e2e/audio-reconnection.spec.ts`
- `docs/features/frontend-audio-reconnection-e2e.md`

## Validation

Playwright Chromium E2E passes. Frontend production build also passes.

## Risks and open questions

- The deterministic transport fake does not prove browser-specific WebSocket implementation behavior.
- A future second test should cover stop during reconnect and bounded queue behavior.

## Next action

Add a second browser-level test for stopping during reconnect and bounded queue behavior when that interaction is prioritized.
