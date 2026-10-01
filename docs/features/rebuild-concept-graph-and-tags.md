# Feature: Rebuild concept graph and manual tags
Status: in progress
Last updated: 2026-10-01

## Objective

Give the meetings a shared memory of the concepts they talk about, and let the user tag meetings by hand. Brain extracts concepts and relationships with evidence, they are projected into one global graph, the same concept in two meetings is one node, and the user can explore the graph, open the cited moment of any meeting, and filter Memory searches by tag (`concept-graph.md`, ADR 0013, ADR 0019).

## Scope

In scope:
- Tables of `migration 0005_concepts` (spec §9): concepts, aliases, mentions, assignments, relationships and relationship occurrences, plus `memory_index_jobs.kind`.
- Concept identity by normalized name and exact alias, whatever the type, never by similarity (`backend/app/concepts.py`, migration `0006_concept_identity`).
- Brain prompt `brain-extraction-v3` with `concepts` and `relationships` (required in the schema sent to the model), validated against the transcript (ADR 0019).
- A concept projection job created when Brain completes, processed by the Memory index worker, replacing the meeting's own mentions atomically.
- Manual tags: `GET /api/meetings/tags`, `GET/POST /api/meetings/{id}/tags`, `GET /api/meetings/{id}/tags/suggestions`, `DELETE /api/meetings/{id}/tags/{assignment_id}`; meetings carry their `tags`.
- Read-only graph API: `GET /api/memory/concept-graph` (with `include_isolated`) and `GET /api/memory/concepts/{id}`; the view hides concepts without relationships by default, with a «Mostrar conceptos sin relaciones» switch.
- Memory search filter by tag, resolved before ranking.
- Backfill: `python -m app.memory_backfill --concepts [--meeting ID] [--exclude-title TITLE]`.

Out of scope: editing, merging or deleting concepts, similarity merging, `supersedes`, the entity graph (`memory_entities`, `memory_relationships`, dropped by the Phase 0 decision), timeline, exporting or reindexing from the UI.

## Acceptance criteria

1. The same concept in two meetings is one node, even when the model typed it differently; a similar but different name is not merged.
2. Every node and edge traces to definitive segments; a tag has no transcript evidence and says so.
3. A manual tag is idempotent across case, accents and spacing, shared across meetings, and removing it from a meeting removes only that assignment.
4. Deleting a meeting removes its mentions, occurrences and assignments and keeps the shared concepts.
5. The graph API filters by type, text, meeting and tag, bounds its size and never returns an edge outside its nodes.
6. A stale extraction is never projected over a newer one.
7. Nothing in the UI edits the graph.
8. Concepts without relationships do not crowd the default view; the user can show them, and a search always finds them.

## Implementation state

Backend and frontend implemented and tested: migration, identity, Brain schema, projection, tags, graph API, tag filter and backfill, plus tags on the meeting page and in the list (with a tag filter), the graph view with its inspector and filters, and the tag filter in the Memory question form. First real backfill (prompt v2, 63 meetings): 99 concepts, 24 shared by more than one meeting, but 64 without any relationship and eight subjects split by type. Fixes from it: the schema sent to the model requires `concepts` and `relationships` (an optional field was simply left out), identity no longer includes the type (operator decision, 2026-10-01), prompt v3 asks for every supported relationship, and the view hides loose concepts by default.

### Independent QA/Security review (2026-10-01)

No SQL injection (every interpolated SQL fragment is a constant; values are bound; LIKE escaped) and no XSS (Cytoscape draws on a canvas, React escapes text). Findings fixed:
- An alias naming another concept of the same output swallowed it: such aliases are dropped, and names are resolved before aliases are recorded.
- `include_isolated=false` treated a concept as connected through an edge that was not drawn (other end filtered out, or a tag left without meetings): connection is now computed from drawn edges.
- The tag filter did not scope relationship occurrences: it now scopes them like the meeting filter.
- The meeting list filtered tags by label, so a meeting tagged with another capitalization was hidden: it filters by concept id.
- Deleted meetings left aliases that kept steering resolution, and orphan concepts stayed readable by id: aliases of a transcript with no projection left are pruned, and the inspector answers 404 for orphans.
- Types were not refreshed for concepts that lost mentions; two names resolving to one concept made two mentions; the tag limit could be passed by concurrent requests (the meeting row is now locked); two projections of one meeting could interleave (advisory lock); the inspector was unbounded.
- Frontend: the inspector closes when filters change, and a refetch with the same graph no longer resets zoom and pan.

Accepted: a Brain alias merges a later mention by exact match (ADR 0019); relationship inserts from concurrent projections may deadlock and are retried.

## Decisions

See [ADR 0019](../adr/0019-brain-concept-extraction-and-graph-projection.md), which is Proposed: the schema of concepts and relationships, the identity rule, the projection job and the tag limits (60 characters, 20 tags per meeting) are decisions this record makes where the documents are silent.

## Files changed

- `backend/app/{concepts,tags_api,concept_graph_api}.py` (new), `backend/migrations/versions/{0005_concepts,0006_concept_identity_by_name}.py` (new)
- `backend/app/{models,brain,brain_worker,memory_jobs,memory_worker,memory_retrieval,memory_api,memory_backfill,meetings,meeting_contracts,main}.py`
- `backend/tests/integration/{test_tags,test_concept_graph,test_memory_pipeline}.py`, `backend/tests/test_brain.py`
- `frontend/src/features/meeting/MeetingTags.tsx`, `frontend/src/features/memory/{ConceptGraph,ConceptGraphSection,ConceptInspector,conceptGraphApi,links}.ts*`, `frontend/src/features/memory/MemoryPage.tsx`, `frontend/src/features/meeting/MeetingPage.tsx`, `frontend/src/features/meetings/MeetingsPage.tsx`, `frontend/src/{api.ts,styles.css}`, `frontend/package.json` (Cytoscape.js)
- `frontend/tests/e2e/tags-graph.spec.ts`
- `docs/adr/0019-*.md`, `docs/meeting-processing-flow.md`, `docs/redis.md`

## Validation

- Migration: upgrade, `alembic check` (no drift), downgrade to 0004 and upgrade again on PostgreSQL. `0006` on a copy of the real database: eight duplicate groups merged, no self-relationship or orphan occurrence, no drift, downgrade and upgrade again.
- Unit: Brain validation of concepts and relationships (an alias naming another concept dropped, merge by normalized name whatever the type, uncited and unknown-end items dropped, caps, old outputs still valid, bad type rejected, schema requires both lists, bracketed segment ids).
- E2E (mocked backend): tags are added, suggested, reused, refused (client and server side), removed and survive a reload; the list shows and filters by tag; the graph draws nodes and edges, a list of the same concepts selects them, the inspector shows aliases, meetings, the cited moment as a link that plays, manual tags without evidence and relations; filters go to the server; empty, partial, truncated and failed states; the tag chosen in the question form is sent as a filter; loose concepts are hidden and counted by default, shown on request and included while searching; the list filter matches a tag typed with another capitalization.
- Integration: tags (idempotence, reuse, removal, limits, suggestions, related-to, cascade, list), projection (one job per extraction, merge by name and alias including Catalan, one node across types shown with the type used most, a same-named tag kept apart, no similarity merge, one mention per concept, filters, bound, loose concepts left out and counted, edges and connection scoped by tag, meeting and type, a tag without meetings does not connect, inspector, re-projection, stale, deletion with type refresh, alias pruning and 404 for orphans) and the Memory tag filter.

## Risks

- Brain now asks for more output; quality of the extracted concepts on real meetings is not measured yet.
- Without aliases, "Kafka" and "Apache Kafka" stay two nodes, and so do Spanish and Catalan spellings ("documentación", "documentació").
- Two different subjects with the same name are one node (accepted by the operator).

## Next action

Redeploy with migration 0006, backfill with prompt v3 over the existing meetings (except the operator's real "test" meeting), measure connectivity again, then the independent QA/Security review. Possible next step, not decided: aliases in the other language (Spanish/Catalan) so both spellings join by exact alias.
