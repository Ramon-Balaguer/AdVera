# ADR 0024: The facts of a meeting summary are Brain data

## Status

Accepted (2026-10-05), by the operator.

## Context

Decisions, actions, risks, open questions and topics existed only inside the JSON of each meeting summary (`summary_extractions.result`). The Brain held concepts and relationships, and its search read fragments of the transcript and the notes. So the Brain could not list "all the decisions", "the open questions" or "what is assigned to someone" across meetings, and the page of a meeting showed only its summary. The specification had left the normalization of these facts as future work.

## Decision

- A table `brain_facts` holds one row per fact: meeting, kind (`decision`, `action`, `risk`, `question`, `topic`), order in the summary, text, state (decisions), owner and due date (actions) and the citations. It is **derived**: the concept projection that already runs after each summary replaces the facts of the meeting as a whole, in the same transaction as its mentions and relationships. Nothing is computed by the model, and the rows go with the meeting.
- The stored projection version of the concepts changes to `brain-concepts-v2`, so meetings projected before this decision show as out of date until `python -m app.brain_backfill --reproject` fills them (it does not call the model).
- `GET /api/meetings/{id}/brain` returns everything the Brain holds of one meeting: index and projection state (and whether they read what the meeting holds now), facts by kind, concepts with their mentions, relationships, tags and people. `GET /api/brain/facts` lists facts across meetings with filters (kind, state, owner, text, meeting, any of several tags, dates), counts per kind and pagination.
- The summary endpoint keeps its meaning: the result of one job.

## Consequences

- Two sources hold the same facts (the summary JSON and the table); the table is always derived and the "out of date" state shows when they differ.
- Facts are shown as extracted: no editing, no deduplication across meetings.
- Not part of this decision: indexing facts as search fragments, listing the searches that cite a meeting.

## Validation and rollback

Tests cover the projection (kinds, state, owner, replacement, cascade), the filters, counts and pages of the list, and the view of a meeting. The migration `0010_brain_facts` was run on a copy of the real database and downgrades. Rollback: `alembic downgrade 0009_brain_naming`.

## Related records

- [Rebuild meeting Brain](../features/rebuild-meeting-brain.md)
- [ADR 0019: Summary concept extraction and concept graph projection](0019-summary-concept-extraction-and-graph-projection.md)
