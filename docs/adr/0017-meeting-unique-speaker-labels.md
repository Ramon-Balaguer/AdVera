# ADR 0017: Speaker labels are unique within a meeting across tracks

## Status

Accepted (2026-09-30).

## Context

ADR 0005 scopes speaker labels to each track and forbids assuming that a speaker on the microphone track and one on the system track are the same person. ADR 0011 derives `attendee_count` from the distinct non-empty `speaker` values of the definitive transcript. If each track numbered its own speakers from `SPEAKER_00`, a meeting with one microphone speaker and two system speakers would show `SPEAKER_00` on both tracks. Its attendee count would then be 2 instead of 3, and a reader could wrongly take the two `SPEAKER_00` labels as one person.

## Decision

Local diarization numbers speakers per track in order of first appearance. Each later track continues the numbering where the previous one ended: tracks are processed in the fixed order `microphone`, then `system`. For example, microphone speakers become `SPEAKER_00`, and system speakers become `SPEAKER_01` and `SPEAKER_02`. Labels are therefore unique within one meeting's definitive transcript and remain anonymous. Two different labels on different tracks may still belong to the same person, because no cross-track identity is inferred (ADR 0005). Speaker labels supplied by the ASR provider remain authoritative (ADR 0003) and are recorded in provenance with `status = "provider"`.

## Consequences

- `attendee_count` counts per-track speakers without collisions. It is an upper bound when one person is heard on both tracks, which is consistent with "labels are not people" (spec §8).
- Labels are stable only within one transcript version; reprocessing may renumber them.
- A future MOSS integration that returns per-track labels must apply the same offset before persisting.

## Validation and rollback

An integration test covers a microphone track with one speaker and a system track with two, and asserts the labels `SPEAKER_00`, `SPEAKER_01` and `SPEAKER_02` and an attendee count of 3. Rollback returns to per-track numbering and accepts the collision; transcripts already written keep their labels until they are reprocessed.

## Related records

- [ADR 0005: Independent microphone and system tracks](0005-dual-track-audio-processing.md)
- [ADR 0011: Derived meeting attendee count](0011-derived-meeting-attendee-count.md)
- [Rebuild local speaker diarization](../features/rebuild-local-diarization.md)
