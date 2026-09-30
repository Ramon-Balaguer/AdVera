# ADR 0011: Derived Meeting Attendee Count

## Status

Accepted (2026-09-26)

## Context
The meeting library previously displayed a hard-coded attendee count of zero. The definitive transcript already persists diarization speaker labels, while meetings do not maintain a separate participant roster.

## Decision
Expose `attendee_count` as a nullable derived field on meeting responses. Count distinct non-empty `speaker` values from the persisted definitive transcript only. Return `null` when the definitive transcript is absent, non-definitive, malformed or unreadable; return zero for a valid definitive transcript with no labeled speakers.

## Consequences
- Meeting list and detail responses remain compatible because the field is optional/nullable.
- Counts are regenerated from the source-of-truth transcript and require no migration.
- Diarization labels represent distinct speakers, not resolved people.
- Transcript file issues do not make the meeting list unavailable.

## Validation
Focused integration tests cover missing transcripts, repeated speakers, distinct speakers, detail/list responses and malformed transcripts. The frontend production build verifies rendering of numeric and unavailable states.

## Rollback
Remove the derived response field and restore the unavailable marker in the client. No database rollback is required.

## Related decisions
- [ADR 0002: Definitive Transcript as the Intelligence Boundary](0002-definitive-transcript-source-of-truth.md)

## Related records
- [Meeting attendee count accuracy](../features/meeting-attendee-count-accuracy.md)
