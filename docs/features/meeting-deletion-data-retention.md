# Meeting Deletion Data Retention
Status: complete
Last updated: 2026-10-01

## Objective

Delete all meeting-owned persisted data when a meeting is deleted, including its filesystem audio and transcript artifacts, while preserving global concepts that may be referenced by other meetings.

## Scope

- Delete the meeting row and database records linked to its `meeting_id` through existing cascade constraints.
- Delete `audio_storage_path/<meeting_id>` after the database deletion succeeds.
- Preserve global concept nodes, aliases and canonical relationships that other meetings still use; meeting-specific mentions, evidence, chunks and relationship occurrences are removed through their meeting or indexing-job links. A concept (or manual tag) left without any meeting is deleted with its aliases and relationships, and aliases taken from the deleted meeting's transcript are forgotten (operator decision, 2026-10-01; ADR 0019).
- Do not add deletion of unrelated query history or shared global graph records.

## Acceptance Criteria

- Deleting an existing meeting returns `204`.
- The meeting and its cascade-owned database records are no longer available.
- The meeting storage directory and its audio/transcript artifacts no longer exist.
- Deleting a meeting without a storage directory still succeeds.
- A storage cleanup failure is surfaced rather than silently ignored.

## Implementation State

Implemented in the meeting delete endpoint and covered by an integration regression test.

## Decisions

- Filesystem cleanup runs after the database transaction commits, so a successful response means the database deletion has completed.
- Cleanup is scoped to the UUID-derived meeting directory and uses recursive removal for all meeting-owned artifacts.
- Global concepts remain shared knowledge while a meeting still mentions or tags them; provenance records tied to the deleted meeting are removed, and concepts left without meetings are deleted.

## Files Changed

- `backend/app/meetings.py`
- `backend/tests/integration/test_meetings_api.py`
- `docs/features/meeting-deletion-data-retention.md`

## Validation

- `python -m pytest backend/tests/integration/test_meetings_api.py -q`

## Risks

- A filesystem permission or I/O failure after the database commit can leave orphaned meeting files; the endpoint reports the failure so it is observable and actionable.

## Next Action

Run the focused integration test and then the backend test suite if the local environment is available.