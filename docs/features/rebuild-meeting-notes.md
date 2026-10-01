# Feature: Rebuild meeting notes and @references
Status: in progress
Last updated: 2026-10-01

## Objective

Take notes during a recording (and after) in a Markdown editor that shows its formatting while typing, reference other meetings or their moments with `@`, and have the notes and what they reference used by Brain, the concept graph and Memory (ADR 0020).

## Scope

In scope:
- Notes per meeting (`meeting_notes`), saved with a button; draft kept in the browser; warning on leaving with unsaved changes.
- CodeMirror 6 editor: headings, bold, italic, strikethrough, code and lists styled in place; Markdown signs grey while editing, hidden otherwise; small format bar.
- `@` references to meetings and `:` to their segments, shown as chips, stored as Markdown links; backlinks ("Referenciada desde").
- Notes as citable blocks (`note-001`…) for Brain (prompt `brain-extraction-v6`) and Memory, with references expanded.
- Analysis keyed by transcript + notes (+ names, ADR 0021); saving changed notes queues Brain and Memory again.
- Citations of notes shown as "Apuntes ¶n" and opening the notes at that block (meeting page, Brain panel, Memory sources, concept inspector).

Out of scope: collaborative editing, images or attachments, notes history.

## Acceptance criteria

1. While editing, a heading shows large and bold text bold, with their signs grey; after saving the signs are hidden.
2. `@` offers other meetings; `:` after a reference offers its segments; the reference is stored as a link and shown as a chip.
3. Saving changed notes queues Brain and Memory; while recording they wait for the transcript.
4. Brain can cite a note block; Memory finds a note through what it references.
5. An analysis made for older notes is not stored over the new one (`INPUT_CHANGED`).

## Implementation state

Backend, frontend and tests implemented. Deployment and a real check are pending.

## Decisions

See [ADR 0020](../adr/0020-meeting-notes-and-references-as-citable-annex.md) (Proposed).

## Files changed

- `backend/app/{analysis_input,notes,notes_api,reanalysis}.py` (new), `backend/migrations/versions/0008_notes_references_speakers.py` (new)
- `backend/app/{models,brain,brain_worker,brain_api,memory_worker,memory_indexing,memory_answer,memory_backfill,transcription_worker,concept_graph_api,main}.py`
- `backend/tests/test_notes.py`, `backend/tests/integration/test_notes_people.py`
- `frontend/src/features/notes/{editor,blocks}.ts` (new), `frontend/src/features/meeting/{MeetingNotes,MeetingBacklinks}.tsx` (new), `MeetingPage.tsx`, `BrainPanel.tsx`, `frontend/src/features/memory/{links.ts,MemoryPage.tsx,ConceptInspector.tsx,conceptGraphApi.ts}`, `frontend/src/{api.ts,styles.css}`, `frontend/package.json`
- `frontend/tests/e2e/notes-speakers.spec.ts`

## Validation

- Unit: blocks and ids, references, analysis key, prompt annex, note citations.
- Integration: saving and queueing, backlinks, Brain reading an expanded reference and citing a note, stale job, Memory finding a note by referenced words.
- E2E (mocked): formatting and grey signs while editing, hidden after saving; `@` and `:` completions and stored links; a Brain citation of a note opens it.
- Migration 0008: upgrade, `alembic check`, downgrade and upgrade on a throw-away database.

## Risks

- Notes can carry facts that were never said; they are always cited as notes.

## Next action

Deploy with migration 0008, check on a synthetic meeting, then an independent QA/Security review.
