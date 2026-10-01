# Feature: Rebuild speakers named as people
Status: in progress
Last updated: 2026-10-01

## Objective

Name each diarized speaker of a meeting as a person from a shared directory, and use the names in the transcript, Brain, Memory and the concept graph (ADR 0021).

## Scope

In scope:
- A "Hablantes" panel on the meeting page: one row per speaker and track, with time and a sample, and a name field that offers known people while typing; saved with a button.
- `GET /api/people`, `GET/PUT /api/meetings/{id}/speakers`; people are person concepts.
- Names in the transcript (`person` per segment), in Brain's prompt (queued again on change), in Memory sources (resolved on read) and in the graph and inspector.
- People left without speakers or mentions are deleted.

Out of scope: recognizing a person by voice across meetings; naming one voice across both tracks at once.

## Acceptance criteria

1. A speaker can be named with a known or new person; the same name in another meeting is the same person.
2. The transcript shows the name; Brain's prompt uses it.
3. The person appears in the graph with the meetings they speak in.
4. Unnaming or deleting the meetings leaves no orphan person.

## Implementation state

Backend, frontend and tests implemented. Deployment and a real check are pending.

## Decisions

See [ADR 0021](../adr/0021-speakers-named-as-people.md) (Proposed).

## Files changed

- `backend/app/people_api.py` (new), `backend/app/{concepts,concept_graph_api,meetings,memory_worker,memory_answer,analysis_input}.py`, migration `0008`
- `backend/tests/integration/test_notes_people.py`
- `frontend/src/features/meeting/MeetingSpeakers.tsx` (new), `MeetingPage.tsx`, `frontend/src/features/memory/*`, `frontend/src/api.ts`
- `frontend/tests/e2e/notes-speakers.spec.ts`

## Validation

- Integration: speakers listed and named, reuse across meetings, suggestions, graph and inspector, prompt names, unknown speaker refused, pruning.
- E2E (mocked): a known person chosen from the suggestions, a new name typed, both saved together.

## Risks

- Two different people with the same name are one person (same rule as concepts).

## Next action

Deploy with migration 0008, check on a synthetic meeting, then an independent QA/Security review.
