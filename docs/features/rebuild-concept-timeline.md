# Feature: Rebuild concept and tag timeline
Status: complete
Last updated: 2026-10-02

## Objective

Read how a project, a person, a topic or a tag evolved across meetings: every meeting where it appears, oldest first, with the facts of that meeting related to it and the moments that cite it (operator request).

## Scope

In scope:
- `GET /api/memory/concepts/{id}/timeline`, read-only. Meetings where the concept is mentioned, tagged, or (for a person) one of the speakers is that person, ordered by when the meeting started (else when it was created); at most the 60 most recent.
- Per meeting: how it appears; up to 3 quotes of its mentions with their text; up to 8 facts of the meeting's latest Brain extraction (decisions, actions with owner and due date, risks, questions, topics) related to it. A fact is related when it cites a segment where the concept is mentioned or its text names the concept or an alias. For a tag the whole meeting carries it, so its decisions, actions, risks and questions and its summary are shown.
- `/memory/timeline/:conceptId` page; opened from the concept inspector ("Ver su línea de tiempo") and from each tag of a meeting. Citations open the meeting at that second, or the notes at that block.

Out of scope: generating a narrative with the model, editing, exporting.

## Acceptance criteria

1. The meetings of a concept are listed oldest first.
2. Each shows the facts related to the concept, with owners, dates and citations, and its quotes.
3. A tag's timeline shows the tagged meetings with their main facts and summary.
4. A concept nobody mentions any more answers 404, and the page says so.

## Implementation state

Implemented, tested and deployed.

## Decisions

- No model call: the timeline is assembled from what Brain already extracted and the concept graph already projected, so it is instant and traceable. Relatedness is decided by citations first and by name or alias in the text.
- No new ADR: a read-only view over data defined by ADR 0013, 0019, 0020 and 0021.

## Files changed

- `backend/app/timeline_api.py` (new), `backend/app/main.py`
- `backend/tests/integration/test_concept_graph.py`
- `frontend/src/features/memory/TimelinePage.tsx` (new), `frontend/src/App.tsx`, `frontend/src/features/memory/ConceptInspector.tsx`, `frontend/src/features/meeting/MeetingTags.tsx`, `frontend/src/styles.css`
- `frontend/tests/e2e/timeline.spec.ts`

## Validation

- Integration: two meetings in order, related facts kept and an unrelated one left out, owner and cited words, a tag's timeline with summary and facts, 404 for an unknown concept.
- E2E (mocked): entries in order with dates, facts, owners, due dates, links to the second and to a note block; the 404 message.

## Risks

- A fact that talks about the concept without naming it or citing its mentions is not shown.

## Next action

None.
