# Feature: Rebuild system monitor
Status: in progress
Last updated: 2026-10-04

## Objective

A page that shows at a glance whether the system is healthy: whether each worker is up, the state of every queue, and the latest meeting summaries and Brain searches. Until now this meant reading `docker compose logs` and querying PostgreSQL by hand. Read only: it does not retry or cancel anything.

## Scope

- **Heartbeat.** The loop shared by the workers (`backend/app/consumer.py`) writes `advera:heartbeat:<worker>:<host>` in Redis every 5 seconds with a 15-second expiry, with the host, process, start time and the job being processed. A clean stop deletes it. A failing Redis never stops the worker. The four loops are `transcription`, `summary`, `brain-index` and `brain-query` (the `brain-worker` container runs the last two).
- **`GET /api/monitor`** (`backend/app/monitor_api.py`): services (API, PostgreSQL, Redis with latency), the configured model, one status per worker (`up`, `down` or `unknown`), one per queue (`ok`, `busy`, `stalled` when work waits and its worker is down, `unknown`), counts and timings per kind of work, the last failures and the latest 15 jobs of each kind. A datastore that does not answer turns its part into `down`/`unknown`; the endpoint never answers an error for it.
- **Page `/system`** (`frontend/src/features/system/SystemPage.tsx`), menu entry with a pulse icon, refreshed every 5 seconds, in English, Spanish and Catalan. Every state is written in words, not only coloured.

Out of scope: container logs (decided with the operator: later, either logs sent to a bounded Redis stream or the Docker socket), actions on jobs, metric history.

## Acceptance criteria

1. A worker with a recent heartbeat is up, one without is down; if Redis cannot be read no worker is called down but unknown.
2. A queue with waiting work and a down worker is stalled.
3. A Redis or PostgreSQL outage leaves the page answering.
4. The heartbeat never stops a worker, and disappears when the worker stops cleanly.
5. Backend (at least 90% coverage), Playwright and `check_docs.py` pass.

## Implementation state

Backend, page and tests done on branch `feature/system-monitor`, not merged.

## Decisions

- An explicit heartbeat rather than deducing life from `XINFO CONSUMERS`: it also shows the job in progress and tells down from idle without guessing.
- A heartbeat says the process lives, not that it advances; that is why the stale-lease count (running without an update for longer than a lease) is shown.
- The text of a search is shown shortened to 80 characters (single-user, ADR 0015).

## Files changed

- `backend/app/consumer.py`, `backend/app/monitor_api.py` (new), `backend/app/job_queue.py` (group names), `backend/app/main.py`, `backend/app/{summary,brain,transcription}_worker.py`
- `backend/tests/test_monitor.py`, `backend/tests/integration/test_monitor.py`, `backend/tests/test_consumer.py`
- `frontend/src/features/system/SystemPage.tsx` (new), `frontend/src/App.tsx`, `frontend/src/i18n/*`, `frontend/src/theme.css`, `frontend/tests/e2e/system.spec.ts`

## Validation

- Unit and integration tests (real Redis and PostgreSQL): heartbeat contents and expiry, clean stop, Redis failure, up/down/unknown, stalled queue, recent work with meeting titles and a shortened search, Redis and PostgreSQL outages.
- Playwright (mocked): healthy system, stalled queue with a down worker, a service down with unknown workers, automatic refresh, load error.

## Risks

- The shared consumer loop changed; the workers must be rebuilt and restarted for the heartbeat to exist (until then every worker shows as down).
- Heartbeat keys of a container that died disappear after 15 seconds, so a restart cycle shows as short "down" periods.

## Next action

Verify on the running stack, then the operator decides on merging the branch.
