# Frontend API Health Gate
Status: complete
Last updated: 2026-09-26

## Objective

Keep the AdVera frontend unavailable until the backend API is ready after a browser refresh, while showing clear startup feedback to the user.

## Product Owner Discovery Brief

### Problem

The frontend can load while the API is still starting, causing initial requests to fail and leaving the application in an error state.

### Target user

Local AdVera operators opening or refreshing the frontend while the backend services are starting.

### Desired outcome

The user sees that AdVera is starting and the application becomes usable automatically once the API is healthy.

### Smallest useful increment

Check `/api/health` on frontend startup, block the application until it responds successfully, and retry every five seconds.

### Scope

- In scope: startup health check, blocking startup view, five-second retries, cleanup, and browser coverage.
- Out of scope: changing the backend health contract, adding authentication, or changing runtime health indicators after startup.

### Acceptance criteria

1. On refresh, the frontend requests `/api/health` before rendering the application.
2. A failed or non-successful health response shows a startup message and prevents normal interaction.
3. The frontend retries health checks every five seconds while unavailable.
4. After a successful health response, the normal application renders and can load its data.
5. The retry timer is cleaned up when the startup gate unmounts.

### States and failures

- Checking: the initial health request is in progress.
- Starting: the API is unavailable and the next check is scheduled.
- Ready: the API responded successfully and the application is usable.
- Network errors and non-2xx responses remain in Starting and do not expose the application.

### Data and provenance constraints

The gate uses only the API health response status. It does not inspect, persist, log, or transform meeting content or other sensitive data.

### Assumptions

- The existing backend contract is `GET /api/health`.
- The Vite proxy and deployed frontend route `/api` to the backend.
- A successful HTTP response indicates that the frontend may proceed.

### Open questions

None for this increment.

## Implementation state

Implemented.

## Decisions

The health gate lives at the frontend mount boundary so meeting and settings requests are not started until `GET /api/health` returns a successful response. The gate retries with one five-second timer after network errors or non-2xx responses. The application remains wrapped in React StrictMode after the gate becomes ready; the gate itself is outside StrictMode to avoid duplicate startup requests during development.

## Files changed

- `frontend/src/main.tsx`
- `frontend/src/styles.css`
- `frontend/tests/e2e/api-health-gate.spec.ts`
- `docs/features/frontend-api-health-gate.md`

## Validation

 - `npm run test:e2e -- tests/e2e/api-health-gate.spec.ts` passed.
 - `get_errors` reports no errors in the changed TypeScript source or E2E test.
 - `npm run build` reaches one pre-existing error in `frontend/src/App.tsx:1288`: `setTrackMetrics` is undefined. No build error remains in the changed files.

## Risks

The frontend remains blocked if the backend health endpoint is intentionally unavailable; this is the desired fail-closed behavior during startup. The repository-wide frontend build remains blocked by the unrelated existing `setTrackMetrics` error.

## Next action

Run the broader frontend E2E suite after the existing `setTrackMetrics` build error is resolved, then complete QA/security review before release.