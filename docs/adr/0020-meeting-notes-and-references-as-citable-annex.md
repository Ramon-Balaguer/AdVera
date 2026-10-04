# ADR 0020: Meeting notes and @references as a citable annex to the transcript

## Status

Proposed (2026-10-01); a new capability the documentation does not cover. Awaits human review.

## Context

The operator wants to take notes during a recording (and after) and have them used, like the transcript, by every later stage: Summary, the concept graph and Brain. Inside the notes they want to reference another meeting, or one moment of it, with `@`, and those references must feed Summary and Brain too. The documents define the definitive transcript as the only extraction source (ADR 0002) and say nothing about notes or links between meetings.

## Decision

**Editor and storage.** Notes are plain Markdown, one document per meeting (`meeting_notes`, at most 50,000 characters). The editor (CodeMirror 6) shows the formatting while typing — headings large, bold, italic, strikethrough, lists — with the Markdown signs visible in grey while editing and hidden when the editor is not being edited. There is no separate preview. Notes are saved with a button; an unsaved draft is kept in the browser and leaving with unsaved changes warns.

**Citable blocks.** The Markdown is split into blocks (blank lines separate them; a heading alone joins the block after it), with ids stable for the same text: `note-001`, `note-002`… A block behaves like a transcript segment of the track `notes` with no time and no speaker. Summary may cite it like a segment, Brain indexes it, and its evidence has `track: "notes"` and `start: null`. Notes are user data, never instructions (the same rule as transcripts).

**@references.** A reference is a Markdown link the editor writes, labelled `@Title` (or `@Title · 12:30`) and pointing to `/meetings/<id>` for a meeting or `/meetings/<id>?segment=<segment id>` for one segment: the same route that opens the meeting at that moment. `@` offers the other meetings by title; `:` right after a reference offers that meeting's segments by number, time or words. The editor shows a reference as a chip that is deleted as one unit; a reference to a deleted meeting shows as broken. References are stored in `meeting_references` on every save (deleted with either meeting) and listed as "Referenciada desde" on the referenced meeting.

**What the analysis reads.** When the analysis runs, each reference is expanded under its block: a segment reference becomes the referenced meeting's title, time, speaker (or person, ADR 0021) and words; a meeting reference becomes its title and the summary of its latest Summary extraction. Summary gets the notes as an annex after the transcript and is told that referenced content is context: it can name concepts and relationships (which joins both meetings in the graph, as concepts are identified by name), but it is never a decision, action, question or risk of this meeting. Brain indexes each block with its expansions, so a search finds the note through what it references. Summary prompt version: `brain-extraction-v8`. v7 states that what the notes say is part of the meeting's record and must be extracted (v6 only allowed citing them, and on a real run the model left them out). v8 gives what the notes reference in a separate section, "Context from other meetings", instead of inside the notes: on a real run a short meeting whose note referenced a whole meeting was summarized with that meeting's Catalan summary and its speaker labels. It also requires the output language (translating) and this meeting's named people as owners.

**Analysis input.** The text stages are keyed by what they read (`backend/app/analysis_input.py`): Summary and its concept projection by transcript + notes + speakers' names, Brain chunks by transcript + notes. Without notes and names the key is exactly the transcript's `segments_sha256`, so every job and extraction made before stays valid. Saving notes that changed queues Summary and Brain again (never the audio); while the meeting has no definitive transcript the notes are only saved, and the first analysis reads them. A job made for older input fails as `INPUT_CHANGED`.

## Consequences

- Notes can put facts into Summary and Brain that were never said; they are cited as "Apuntes ¶n" so the reader sees where a fact comes from.
- What a reference points to is read when the analysis runs; if the referenced meeting changes, it is picked up the next time the notes are saved.
- A note has no time, so its evidence opens the notes, not the audio.

## Validation and rollback

Unit tests cover the block split and ids, the reference format, the analysis key (equal to the transcript hash without notes), the prompt annex and note citations. Integration tests cover saving (queued, unchanged, waiting for the transcript, too long), backlinks, a Summary run that reads an expanded segment reference and cites a note, a stale job, and a Brain search that finds a note through what it references. Rollback: migration `0008_notes_speakers` downgrades; without notes the analysis is exactly what it was.

## Related records

- [ADR 0002: Definitive transcript as the intelligence boundary](0002-definitive-transcript-source-of-truth.md)
- [ADR 0019: Summary concept extraction and concept graph projection](0019-summary-concept-extraction-and-graph-projection.md)
- [ADR 0021: Speakers named as people](0021-speakers-named-as-people.md)
- [Rebuild meeting notes and @references](../features/rebuild-meeting-notes.md)
