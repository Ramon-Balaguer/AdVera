# Feature: Rebuild speakers named as people
Status: complete
Last updated: 2026-10-01

## Objective

Name each diarized speaker of a meeting as a person from a shared directory, and use the names in the transcript, Summary, Brain and the concept graph (ADR 0021).

## Scope

In scope:
- A "Hablantes" panel on the meeting page: one row per speaker and track, with time and a sample, and a name field that offers known people while typing; saved with a button.
- `GET /api/people`, `GET/PUT /api/meetings/{id}/speakers`; people are person concepts.
- Names in the transcript (`person` per segment), in Summary's prompt (queued again on change), in Brain sources (resolved on read) and in the graph and inspector.
- People left without speakers or mentions are deleted.

Out of scope: recognizing a person by voice across meetings; naming one voice across both tracks at once.

## Acceptance criteria

1. A speaker can be named with a known or new person; the same name in another meeting is the same person.
2. The transcript shows the name; Summary's prompt uses it.
3. The person appears in the graph with the meetings they speak in.
4. Unnaming or deleting the meetings leaves no orphan person.

## Implementation state

Backend, frontend and tests implemented and deployed. Real check on "Smoke QA meeting-120s": two speakers named "Ramón Prueba" and "Marta Prueba"; the transcript shows the names, Summary was queued again and its actions now carry "Marta Prueba" as owner where it used the label before, and both appear in the graph as people.

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

See [ADR 0021](../adr/0021-speakers-named-as-people.md) (Proposed).

## Files changed

- `backend/app/people_api.py` (new), `backend/app/{concepts,concept_graph_api,meetings,brain_worker,brain_answer,analysis_input}.py`, migration `0008`
- `backend/tests/integration/test_notes_people.py`
- `frontend/src/features/meeting/MeetingSpeakers.tsx` (new), `MeetingPage.tsx`, `frontend/src/features/brain/*`, `frontend/src/api.ts`
- `frontend/tests/e2e/notes-speakers.spec.ts`

## Validation

- Integration: speakers listed and named, reuse across meetings, suggestions, graph and inspector, prompt names, unknown speaker refused, pruning.
- E2E (mocked): a known person chosen from the suggestions, a new name typed, both saved together.

## Risks

- Two different people with the same name are one person (same rule as concepts).

## Next action

None.
