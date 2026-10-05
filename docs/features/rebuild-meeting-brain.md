# Feature: Rebuild meeting Brain
Status: in progress
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

Backend done on branch `feature/meeting-brain` (projection, both endpoints, migration tested on a copy of the real database). Interface, deployment and `--reproject` pending.

## Decisions

- A new Brain endpoint instead of widening `/summary` (the summary is the result of one job).
- Facts are projected as their own rows, not read from the JSON on every request.
- The version of the concept projection changes, and existing meetings are filled with the existing reprojection, without the model.

## Files changed

- `backend/app/models.py`, `backend/migrations/versions/0010_brain_facts.py`, `backend/app/brain_worker.py`, `backend/app/brain_jobs.py`, `backend/app/facts_api.py`, `backend/app/meeting_brain_api.py`, `backend/app/main.py`
- `backend/tests/test_brain_facts.py`, `backend/tests/integration/test_brain_facts.py`, `backend/tests/integration/test_brain_endpoints.py`

## Validation

- Unit and integration tests; migration upgrade and downgrade on a copy of the real database.

## Risks

- Until `--reproject` runs, existing meetings show their facts as missing.
- Facts are as good as the summary extracted them.

## Next action

The interface, then deployment and `--reproject`.
