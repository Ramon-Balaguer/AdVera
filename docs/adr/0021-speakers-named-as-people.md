# ADR 0021: Speakers named as people of a shared directory

## Status

Proposed (2026-10-01); a new capability the documentation does not cover. Awaits human review.

## Context

Diarization labels speakers `SPEAKER_00`, `SPEAKER_01`… per track (`rebuild-local-diarization.md`). The operator wants to say who each one is, reuse the same person across meetings, and have the names used everywhere: transcript, Brain, Memory and the concept graph.

## Decision

**Person = concept.** A person is a concept of type `person` (identity `concept`, ADR 0019), so the person a speaker is named as and the person Brain extracts by the same name are one node. Naming a speaker sets the concept's type to `person`, and the shown type of a concept named as a speaker is never re-ranked by mentions.

**Assignment.** `meeting_speakers` maps (meeting, track, speaker label) to a person concept, unique per meeting, track and label, deleted with the meeting. `PUT /api/meetings/{id}/speakers` replaces the meeting's names under the concept lock (ADR 0019 revision) and prunes people left without speakers or mentions. `GET /api/people` suggests known people (most present first; accents and case ignored).

**Where names are used.**
- The transcript API adds `person` to each segment; the page shows the name, with the label in a tooltip.
- Brain sees `Ramón (SPEAKER_00)`, so owners and people come out by name. Names are part of Brain's analysis input (ADR 0020), so naming queues Brain again (never the audio).
- Memory chunks keep the label; names are resolved when a query is read, so renaming does not reindex.
- The graph counts a meeting for a person when one of its speakers is that person; the inspector says "habla en esta reunión".

## Consequences

- Two different people with the same name are one node, the same trade-off as concepts (ADR 0019).
- A label is per track: the same voice on the microphone and the system track is named twice.
- People are not recognized by voice across meetings; that would need speaker embeddings matched across meetings and is out of scope.

## Validation and rollback

Integration tests cover listing speakers, naming them, reuse of a person across meetings, suggestions, the graph node and inspector, the names in the Brain prompt, an unknown speaker refused, and people pruned after unnaming and deleting. Rollback: migration `0008_notes_speakers` downgrades; without names everything reads the labels as before.

## Related records

- [ADR 0019: Brain concept extraction and concept graph projection](0019-brain-concept-extraction-and-graph-projection.md)
- [ADR 0020: Meeting notes and @references](0020-meeting-notes-and-references-as-citable-annex.md)
- [Rebuild speakers named as people](../features/rebuild-speaker-people.md)
