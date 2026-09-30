# Feature: Rebuild concept graph and manual tags
Status: in progress
Last updated: 2026-09-30

## Objective

Give the meetings a shared memory of the concepts they talk about, and let the user tag meetings by hand. Brain extracts concepts and relationships with evidence, they are projected into one global graph, the same concept in two meetings is one node, and the user can explore the graph, open the cited moment of any meeting, and filter Memory searches by tag (`concept-graph.md`, ADR 0013, ADR 0019).

## Scope

In scope:
- Tables of `migration 0005_concepts` (spec §9): concepts, aliases, mentions, assignments, relationships and relationship occurrences, plus `memory_index_jobs.kind`.
- Concept identity by normalized name and exact alias, never by similarity (`backend/app/concepts.py`).
- Brain prompt `brain-extraction-v2` with `concepts` and `relationships`, validated against the transcript (ADR 0019).
- A concept projection job created when Brain completes, processed by the Memory index worker, replacing the meeting's own mentions atomically.
- Manual tags: `GET /api/meetings/tags`, `GET/POST /api/meetings/{id}/tags`, `GET /api/meetings/{id}/tags/suggestions`, `DELETE /api/meetings/{id}/tags/{assignment_id}`; meetings carry their `tags`.
- Read-only graph API: `GET /api/memory/concept-graph` and `GET /api/memory/concepts/{id}`.
- Memory search filter by tag, resolved before ranking.
- Backfill: `python -m app.memory_backfill --concepts [--meeting ID] [--exclude-title TITLE]`.

Out of scope: editing, merging or deleting concepts, similarity merging, `supersedes`, the entity graph (`memory_entities`, `memory_relationships`, dropped by the Phase 0 decision), timeline, exporting or reindexing from the UI.

## Acceptance criteria

1. The same concept in two meetings is one node; a similar but different one is not merged.
2. Every node and edge traces to definitive segments; a tag has no transcript evidence and says so.
3. A manual tag is idempotent across case, accents and spacing, shared across meetings, and removing it from a meeting removes only that assignment.
4. Deleting a meeting removes its mentions, occurrences and assignments and keeps the shared concepts.
5. The graph API filters by type, text, meeting and tag, bounds its size and never returns an edge outside its nodes.
6. A stale extraction is never projected over a newer one.
7. Nothing in the UI edits the graph.

## Implementation state

Backend implemented and tested against real PostgreSQL and Redis: migration, identity, Brain schema, projection, tags, graph API, tag filter and backfill. Frontend (tags on the meeting and in the list, the graph view and inspector, the tag filter in Memory) and the real backfill are pending.

## Decisions

See [ADR 0019](../adr/0019-brain-concept-extraction-and-graph-projection.md), which is Proposed: the schema of concepts and relationships, the identity rule, the projection job and the tag limits (60 characters, 20 tags per meeting) are decisions this record makes where the documents are silent.

## Files changed

- `backend/app/{concepts,tags_api,concept_graph_api}.py` (new), `backend/migrations/versions/0005_concepts.py` (new)
- `backend/app/{models,brain,brain_worker,memory_jobs,memory_worker,memory_retrieval,memory_api,memory_backfill,meetings,meeting_contracts,main}.py`
- `backend/tests/integration/{test_tags,test_concept_graph,test_memory_pipeline}.py`, `backend/tests/test_brain.py`
- `docs/adr/0019-*.md`, `docs/meeting-processing-flow.md`, `docs/redis.md`

## Validation

- Migration: upgrade, `alembic check` (no drift), downgrade to 0004 and upgrade again on PostgreSQL.
- Unit: Brain validation of concepts and relationships (merge by normalized name, uncited and unknown-end items dropped, caps, old outputs still valid, bad type rejected).
- Integration: tags (idempotence, reuse, removal, limits, suggestions, related-to, cascade, list), projection (one job per extraction, merge by name and alias including Catalan, no similarity merge, filters, bound, inspector, re-projection, stale, deletion) and the Memory tag filter.

## Risks

- Brain now asks for more output; quality of the extracted concepts on real meetings is not measured yet.
- Without aliases, "Kafka" and "Apache Kafka" stay two nodes.

## Next action

Frontend, then the backfill over the existing meetings (except the operator's real "test" meeting), then an independent QA/Security review.
