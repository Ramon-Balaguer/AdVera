# Feature: System Monitor
Status: complete
Last updated: 2026-09-21

## Objective
Provide operators with one read-only view of runtime resources, Brain and Memory job state, Capture Agent connectivity, and knowledge graph counts.

## Scope
- Aggregated backend monitor endpoint.
- CPU/GPU runtime metrics.
- Brain and Memory job counts and latest activity.
- Capture Agent connection, session and track activity state.
- Brain and Memory overview counts.
- Auto-refreshing frontend Monitor page.

Out of scope: worker control, job cancellation, worker heartbeats, historical charts, logs, secrets and meeting content.

## Acceptance criteria
- Monitor is reachable from the main navigation.
- The page distinguishes queued, running, completed and failed jobs.
- Capture Agent distinguishes disconnected, connected without a session and active session.
- Brain and Memory show current counts and latest processing state.
- Partial backend failures render as unavailable/degraded sections without hiding the rest.
- No tokens, raw provider errors, prompts, audio or transcript content are exposed.
- The page refreshes automatically and displays observation time.

## States and failures
- Loading: initial request is pending.
- Healthy: component returned valid current data.
- Degraded: component returned partial data or has failed jobs.
- Unavailable: component could not be read.
- Capture Agent: disconnected, connected, session active, or transmitting when recent activity is observable.

## Data and provenance constraints
Brain and Memory counts must derive from definitive transcript processing and persisted records. Responses contain only sanitized status, counts, timestamps and diagnostic codes.

## Decisions
- Reuse existing system metrics, Capture Agent connection state and Memory overview query patterns.
- Use a polling endpoint for the first increment; a dedicated Monitor WebSocket is deferred.
- Worker liveness is not asserted from an empty queue; independent heartbeat instrumentation is deferred.

## Files changed
- `backend/app/monitor.py`
- `backend/app/main.py`
- `backend/app/capture_agent.py`
- `backend/tests/test_monitor.py`
- `frontend/src/App.tsx`
- `frontend/src/features/monitor/MonitorPage.tsx`
- `frontend/src/styles.css`
- `docs/features/system-monitor.md`

## Validation
- `pytest backend/tests/test_monitor.py`: 2 passed.
- `pytest backend/tests/test_capture_agent.py backend/tests/test_system.py`: 17 passed.
- Temporary API instance returned `GET /api/monitor` with HTTP 200.
- Static diagnostics are clean for changed Python and TypeScript files.
- Frontend build reaches only pre-existing `cytoscape` errors in `ConceptGraph.tsx`.

## Risks and next action
Counts may become expensive as data grows and worker idle status is not proof of worker health. Add independent worker heartbeat instrumentation and historical metrics in a later increment. Restart the API process on port 8000 to expose the new route in the current development environment.
