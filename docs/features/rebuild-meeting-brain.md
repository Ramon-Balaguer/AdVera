# Feature: Rebuild meeting Brain
Status: complete
Last updated: 2026-10-05

## Objective

See everything the Brain holds of a meeting (not only its summary) and browse decisions, actions, risks, open questions and topics across meetings (ADR 0024).

## Scope

- Table `brain_facts` (migration `0010_brain_facts`), filled by the concept projection; concept projection version `brain-concepts-v2`.
- `GET /api/meetings/{id}/brain` and `GET /api/brain/facts`.
- Page of a meeting: a Brain tab beside the summary (index state, facts, concepts, relationships, tags, people, graph of the meeting). Page `/brain/facts` with a tab per kind and filters.

Out of scope: facts as search fragments, searches that cite a meeting, editing or deduplicating facts.

## Acceptance criteria

1. Every fact of a summary is projected with its kind, state, owner, due date and citations, replaced (not duplicated) when the meeting is projected again, and deleted with the meeting.
2. The list filters by kind, state, owner, text, meeting, any of several tags and dates, with counts per kind and pagination.
3. The tab of a meeting shows the index and projection state, the facts, concepts, relationships, tags and people, and warns when something is missing or out of date.
4. Backend (at least 90% coverage), Playwright and `check_docs.py` pass; after `--reproject` the facts match the stored summaries.

## Implementation state

Done on branch `feature/meeting-brain` (not merged) and deployed on 2026-10-05. Migration `0010` applied; `--reproject` projected the 70 meetings with no model calls and no failed jobs: 35 decisions, 57 actions, 7 questions, 8 risks and 109 topics, exactly the counts in the stored summaries. A real meeting's Brain tab data (index, projection, facts, 26 concepts, 29 relationships, tags) and `/brain/facts` answer correctly. Backend 90.87% coverage, 64 Playwright tests.

## Decisions

- A new Brain endpoint instead of widening `/summary` (the summary is the result of one job).
- Facts are projected as their own rows, not read from the JSON on every request.
- The version of the concept projection changes, and existing meetings are filled with the existing reprojection, without the model.

## Files changed

- `backend/app/models.py`, `backend/migrations/versions/0010_brain_facts.py`, `backend/app/brain_worker.py`, `backend/app/brain_jobs.py`, `backend/app/facts_api.py`, `backend/app/meeting_brain_api.py`, `backend/app/main.py`
- `frontend/src/features/meeting/MeetingBrain.tsx`, `frontend/src/features/brain/{FactsPage,FactList,factsApi}.ts*`, `MeetingPage.tsx`, `App.tsx`, `ConceptGraphSection.tsx`, `i18n/*`, `tests/e2e/meeting-brain.spec.ts`
- `backend/tests/test_brain_facts.py`, `backend/tests/integration/test_brain_facts.py`, `backend/tests/integration/test_brain_endpoints.py`

## Validation

- Unit and integration tests; migration upgrade and downgrade on a copy of the real database.

## Risks

- Until `--reproject` runs, existing meetings show their facts as missing.
- Facts are as good as the summary extracted them.

## Next action

The operator decides on merging the branch.
