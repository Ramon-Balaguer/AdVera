# Meeting attendee count accuracy
Status: complete
Last updated: 2026-09-26

## Objective
Make the meetings library show the number of distinct speakers present in the definitive transcript instead of a hard-coded value.

## Product brief
- **Problem:** The meetings table displays `0` for every meeting, so users cannot trust the attendee information.
- **Target user:** Meeting reviewers using the meetings library.
- **Desired outcome:** The attendee count reflects distinct speakers identified in the definitive transcript, with an explicit unavailable state when reliable data does not exist.
- **Smallest useful increment:** Expose a nullable attendee count on meeting responses, derived from definitive transcript speaker metadata, and render it in the meetings table.
- **In scope:** Meeting-list/detail response contract, distinct definitive speaker counting, meetings-library rendering, regression coverage.
- **Out of scope:** Manual participant management, speaker-name correction, provisional transcript data, cross-meeting identity resolution.

## Acceptance criteria
- A meeting with three distinct definitive speakers displays `3`.
- Repeated segments from one speaker count once.
- Meetings without a definitive transcript display an unavailable marker, not a misleading `0`.
- Provisional transcript data never affects the count.
- Meeting API failures keep their existing error behavior.

## States and failure behavior
- Definitive transcript with speaker labels: return and display the distinct speaker count.
- Definitive transcript unavailable or unreadable: return `null` and display `—`.
- Empty definitive speaker set: return `0`.

## Data and provenance constraints
The definitive transcript is the source of truth. Counts use persisted definitive transcript segment `speaker` values only; no title, description, creator, audio track, provisional text, or inferred identity is used.

## Dependencies and assumptions
Transcript documents use the existing `segments` array and optional `speaker` field. Diarization labels count as distinct attendees until identity resolution is introduced.

## Open questions
None for this increment.

## Implementation state
Implemented.

## Decisions
No API or persistence migration is needed. The count is a derived response field from the definitive transcript document. `attendee_count` is nullable so missing, non-definitive or invalid transcript data is not presented as zero. The contract decision is recorded in [ADR 0011](../adr/0011-derived-meeting-attendee-count.md).

## Files changed
- `backend/app/meeting_contracts.py`
- `backend/app/meetings.py`
- `backend/tests/integration/test_meetings_api.py`
- `frontend/src/features/meetings/MeetingLibrary.tsx`
- `frontend/src/App.tsx`
- `docs/adr/0011-derived-meeting-attendee-count.md`
- `docs/adr/README.md`
- `docs/features/meeting-attendee-count-accuracy.md`

## Validation
- `python -m pytest tests/integration/test_meetings_api.py -q` from `backend`: 7 passed.
- `npm run build` from `frontend`: passed; Vite emitted only the existing chunk-size warning.

## Risks
Unreadable transcript files should not make the meeting list unavailable; they are represented as an unavailable count.

## Next action
QA/security review before release; no migration or deployment action is required.
