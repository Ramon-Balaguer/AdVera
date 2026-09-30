# Feature: Reliable Brain Search Results via WebSocket
Status: complete
Last updated: 2026-09-20

## Problem and target user
Brain searches can remain without visible results because the frontend submits a query, receives `queued`, and relies on bounded polling. The target user is an AdVera user searching definitive meeting memory for decisions, actions, relationships, and cited evidence.

## Desired outcome
Users receive query progress and a final cited result through a query-scoped WebSocket, with explicit failure and reconnect behavior.

## Smallest useful increment
Keep HTTP query creation and the persisted `MemoryQueryRun` as durable boundaries, then add a WebSocket that emits state transitions and the final result. Replace frontend polling for Brain queries.

## Scope
In scope: query-scoped WebSocket contract; queued, retrieving, synthesizing, completed, empty, and failed states; frontend connection lifecycle; enqueue failure visibility; focused backend and end-to-end coverage.

Out of scope: replacing Redis workers, streaming partial answer tokens, changing retrieval or synthesis, provisional transcripts, or general WebSocket infrastructure.

## Acceptance criteria
- A submitted query displays progress without repeated browser polling.
- Completed, empty, and failed states are rendered from WebSocket messages.
- Disconnect and reconnect can recover the persisted final result.
- A failed enqueue does not remain silently queued.
- Existing definitive-transcript and provenance constraints remain intact.

## States and failure behavior
The client states are idle, connecting, queued, retrieving, synthesizing, completed, empty, failed, disconnected, and timed out. Unknown query IDs and backend failures are explicit errors. Terminal messages close the query stream; reconnect uses the durable HTTP status endpoint.

## Data and provenance constraints
The definitive transcript remains the source of truth. Existing query hashes, citations, evidence identifiers, provider, model, and model version are preserved. No secrets, real meeting content, or chain-of-thought are logged.

## Dependencies and assumptions
FastAPI WebSocket support is available. Redis remains the background-job transport. The database remains the source of truth for recovery. Authentication and origin policy continue to apply to the WebSocket deployment.

## Implementation record
Current flow reviewed: `BrainPage.tsx` polls `/api/memory/query/{id}` up to 20 times; `memory_api.py` creates and enqueues queries; `memory_worker.py` persists state transitions and results. The Product Owner recommends a query-scoped WebSocket and bounded recovery behavior.

## Validation
- `backend/tests/test_backend_services.py`: focused backend memory tests pass, including enqueue failure regression.
- `frontend/tests/e2e/brain.spec.ts`: 7 Brain Playwright tests pass, including queued-to-completed WebSocket delivery and backend failure.
- `npm run build`: frontend TypeScript and Vite build pass.
- `git diff --check`: no patch whitespace errors; Git reports only existing LF/CRLF normalization warnings.

## Risks and open questions
The first increment uses the persisted state as the durable delivery source; a future Redis pub/sub channel can remove server-side wait intervals if higher query volume requires it. WebSocket authentication and multi-tab fan-out remain deployment concerns.

## Files changed
- `backend/app/memory_api.py`
- `backend/tests/test_backend_services.py`
- `frontend/src/features/brain/brainApi.ts`
- `frontend/src/features/brain/BrainPage.tsx`
- `frontend/tests/e2e/brain.spec.ts`
- `docs/features/brain-query-results-websocket.md`

## Decisions and risks
The first increment uses the persisted query state as the durable delivery source and checks it from the WebSocket endpoint, so browser polling is removed while the server retains a bounded wait interval. A future Redis pub/sub channel can eliminate that server-side interval if query volume requires it. The existing runtime metrics WebSocket may log `ECONNABORTED` when Playwright closes a page, but this does not affect query delivery or test outcomes.

## Next action
Run the independent QA/Security review before release, with attention to WebSocket authentication, origin checks, reconnect policy, and higher-volume delivery.
