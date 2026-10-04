# Feature: Rebuild meeting notes and @references
Status: complete
Last updated: 2026-10-01

## Objective

Take notes during a recording (and after) in a Markdown editor that shows its formatting while typing, reference other meetings or their moments with `@`, and have the notes and what they reference used by Summary, the concept graph and Brain (ADR 0020).

## Scope

In scope:
- Notes per meeting (`meeting_notes`), saved with a button; draft kept in the browser; warning on leaving with unsaved changes.
- CodeMirror 6 editor: headings, bold, italic, strikethrough, code and lists styled in place; Markdown signs grey while editing, hidden otherwise; small format bar.
- `@` references to meetings and `:` to their segments, shown as chips, stored as Markdown links; backlinks ("Referenciada desde").
- Notes as citable blocks (`note-001`…) for Summary (prompt `brain-extraction-v8`, referenced content in a separate "other meetings" section) and Brain, with references expanded.
- Analysis keyed by transcript + notes (+ names, ADR 0021); saving changed notes queues Summary and Brain again.
- Citations of notes shown as "Apuntes ¶n" and opening the notes at that block (meeting page, Summary panel, Brain sources, concept inspector).

Out of scope: collaborative editing, images or attachments, notes history.

## Acceptance criteria

1. While editing, a heading shows large and bold text bold, with their signs grey; after saving the signs are hidden.
2. `@` offers other meetings; `:` after a reference offers its segments; the reference is stored as a link and shown as a chip.
3. Saving changed notes queues Summary and Brain; while recording they wait for the transcript.
4. Summary can cite a note block; Brain finds a note through what it references.
5. An analysis made for older notes is not stored over the new one (`INPUT_CHANGED`).

## Implementation state

Backend, frontend and tests implemented and deployed (migration 0008). Real check on the synthetic meeting "Smoke QA meeting-120s": notes with a fact never said (a budget of 12,000 euros) and an @reference to a segment of "Smoke ca-two-speakers". Prompt v6 read the notes but left them out of the extraction; prompt `brain-extraction-v7` states that the notes are part of the record and must be extracted. With v7 Summary extracted the budget as a decision citing `note-001`, and the referenced segment shaped a decision and a concept; a Brain question about the budget was answered from the note alone ("Apuntes ¶1").

### Independent QA/Security review (2026-10-02)

Nothing exploitable found: reference chips use `textContent` and only app links to `/meetings/<uuid>` are opened (no XSS, no open redirect), notes go through the prompt's data-not-instructions rule with brackets neutralised, the people search escapes `LIKE`, note content is never logged, and the limits hold. Findings fixed:
- Going back to earlier notes or names (A → B → A) answered "unchanged" and left B's analysis: a reused job whose result is not the current one is run again.
- Text typed while a save was on its way was discarded: only what was sent is cleared.
- The same note line in two meetings was deduplicated in Brain: for notes the meeting is part of the key.
- A long note block was one unbounded chunk: blocks are indexed in pieces of at most 800 characters, and the answer quotes each piece.
- Two concurrent saves of one meeting's notes could collide: saves are serialized per meeting.
- Cited note blocks showed the current text after an edit shifted the ids: the evidence keeps the cited words.
- Python and JavaScript split blocks differently on unusual Unicode: both use only ASCII spaces and "
", checked against one shared fixture (`frontend/tests/fixtures/note-blocks.json`).
- ":" after a reference opened the segment list on prose ("…Guillem: decidimos"): it needs a search text right after it.
- A name kept for a label the transcript no longer has named a different voice: such names are ignored.
- The draft was re-applied on refetch and outlived a deleted meeting: applied once, removed with the meeting.

## Decisions

See [ADR 0020](../adr/0020-meeting-notes-and-references-as-citable-annex.md) (Proposed).

## Files changed

- `backend/app/{analysis_input,notes,notes_api,reanalysis}.py` (new), `backend/migrations/versions/0008_notes_references_speakers.py` (new)
- `backend/app/{models,summary,summary_worker,summary_api,brain_worker,brain_indexing,brain_answer,brain_backfill,transcription_worker,concept_graph_api,main}.py`
- `backend/tests/test_notes.py`, `backend/tests/integration/test_notes_people.py`
- `frontend/src/features/notes/{editor,blocks}.ts` (new), `frontend/src/features/meeting/{MeetingNotes,MeetingBacklinks}.tsx` (new), `MeetingPage.tsx`, `SummaryPanel.tsx`, `frontend/src/features/brain/{links.ts,BrainPage.tsx,ConceptInspector.tsx,conceptGraphApi.ts}`, `frontend/src/{api.ts,styles.css}`, `frontend/package.json`
- `frontend/tests/e2e/notes-speakers.spec.ts`

## Validation

- Unit: blocks and ids, references, analysis key, prompt annex, note citations.
- Integration: saving and queueing, backlinks, Summary reading an expanded reference and citing a note, stale job, Brain finding a note by referenced words.
- E2E (mocked): formatting and grey signs while editing, hidden after saving; `@` and `:` completions and stored links; a Summary citation of a note opens it.
- Migration 0008: upgrade, `alembic check`, downgrade and upgrade on a throw-away database.

## Risks

- Notes can carry facts that were never said; they are always cited as notes.

## Next action

None.
