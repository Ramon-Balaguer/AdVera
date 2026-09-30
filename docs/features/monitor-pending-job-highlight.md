# Feature: Monitor Pending Job Highlight
Status: complete
Last updated: 2026-09-25

## Objective

Make Redis consumer-group pending jobs immediately identifiable on the Monitor page.

## Acceptance criteria

- Entries pending in any Redis consumer group expose `pending: true`.
- The frontend highlights pending entries and displays `Pendiente`.
- Confirmed entries retain the normal appearance.
- The change remains read-only and does not acknowledge, retry or mutate queue messages.

## Decisions and constraints

Pending means the Redis stream entry is present in a consumer group's pending entries list. PostgreSQL remains authoritative for job lifecycle; no schema or migration change is needed.

## Files changed

- `backend/app/monitor.py`
- `backend/tests/test_monitor.py`
- `frontend/src/features/monitor/MonitorPage.tsx`
- `frontend/src/styles.css`

## Validation

Run the focused monitor tests and static diagnostics. The frontend build may retain unrelated pre-existing errors.