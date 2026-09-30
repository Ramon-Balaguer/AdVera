# Feature: Monitor Job Error Reason
Status: complete
Last updated: 2026-09-25

## Objective

Show operators the safe persisted reason for a failed Redis job in addition to its monitor error code.

## Scope and acceptance criteria

- Failed queue entries expose a separate safe `job_error_reason` field.
- The Monitor renders the reason below the meeting/job label.
- Unknown stored errors use a generic safe fallback and never expose raw details.
- Existing queue status, labels and error codes remain unchanged.

## Decisions and constraints

PostgreSQL job errors remain authoritative. No schema or migration change is needed. The monitor allowlists known operator-safe reasons and falls back for other stored values.

## Files changed

- `backend/app/monitor.py`
- `backend/tests/test_monitor.py`
- `frontend/src/features/monitor/MonitorPage.tsx`

## Validation

Focused backend monitor tests are required after the edit. Frontend type/build validation should be run if available.

## Risks and next action

The safe reason list must be extended when a new operator-facing worker error is introduced. Validate the running Monitor against a failed transcription job.