# Feature: Rebuild concept graph and manual tags
Status: complete
Last updated: 2026-10-01

## Objective

Give the meetings a shared brain of the concepts they talk about, and let the user tag meetings by hand. Summary extracts concepts and relationships with evidence, they are projected into one global graph, the same concept in two meetings is one node, and the user can explore the graph, open the cited moment of any meeting, and filter Brain searches by tag (`concept-graph.md`, ADR 0013, ADR 0019).

## Scope

In scope:
- Tables of `migration 0005_concepts` (spec §9): concepts, aliases, mentions, assignments, relationships and relationship occurrences, plus `brain_index_jobs.kind`.
- Concept identity by normalized name and exact alias, whatever the type, never by similarity (`backend/app/concepts.py`, migration `0006_concept_identity`).
- Summary prompt `brain-extraction-v3` with `concepts` and `relationships` (required in the schema sent to the model), validated against the transcript (ADR 0019).
- A concept projection job created when Summary completes, processed by the Brain index worker, replacing the meeting's own mentions atomically.
- Manual tags: `GET /api/meetings/tags`, `GET/POST /api/meetings/{id}/tags`, `GET /api/meetings/{id}/tags/suggestions`, `DELETE /api/meetings/{id}/tags/{assignment_id}`; meetings carry their `tags`.
- Read-only graph API: `GET /api/brain/concept-graph` (with `include_isolated`) and `GET /api/brain/concepts/{id}`; the view hides concepts without relationships by default, with a «Mostrar conceptos sin relaciones» switch.
- Brain search filter by tag, resolved before ranking.
- Backfill: `python -m app.brain_backfill --concepts [--meeting ID] [--exclude-title TITLE]`; `--reproject` projects the latest stored extractions again without calling the model.

Out of scope: editing, merging or deleting concepts, similarity merging, `supersedes`, the entity graph (`brain_entities`, `brain_relationships`, dropped by the Phase 0 decision), timeline, exporting or reindexing from the UI.

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

Backend and frontend implemented and tested: migration, identity, Summary schema, projection, tags, graph API, tag filter and backfill, plus tags on the meeting page and in the list (with a tag filter), the graph view with its inspector and filters, and the tag filter in the Brain question form. First real backfill (prompt v2, 63 meetings): 99 concepts, 24 shared by more than one meeting, but 64 without any relationship and eight subjects split by type. Fixes from it: the schema sent to the model requires `concepts` and `relationships` (an optional field was simply left out), identity no longer includes the type (operator decision, 2026-10-01), prompt v3 asks for every supported relationship, and the view hides loose concepts by default.

Second real backfill (prompt v3, identity by name, review fixes, `--reproject`; 64 of 65 meetings, the operator's "test" meeting excluded): 81 concepts shown (was 99), 66 relationships drawn (was 32), 15 without any relationship (was 64), 40 concepts shared by more than one meeting (was 24), no duplicate names. The default view shows 66 connected concepts and says that 15 are hidden.

### Independent QA/Security review (2026-10-01)

No SQL injection (every interpolated SQL fragment is a constant; values are bound; LIKE escaped) and no XSS (Cytoscape draws on a canvas, React escapes text). Findings fixed:
- An alias naming another concept of the same output swallowed it: such aliases are dropped, and names are resolved before aliases are recorded.
- `include_isolated=false` treated a concept as connected through an edge that was not drawn (other end filtered out, or a tag left without meetings): connection is now computed from drawn edges.
- The tag filter did not scope relationship occurrences: it now scopes them like the meeting filter.
- The meeting list filtered tags by label, so a meeting tagged with another capitalization was hidden: it filters by concept id.
- Deleted meetings left aliases that kept steering resolution, and orphan concepts stayed readable by id: aliases of a transcript with no projection left are pruned, and the inspector answers 404 for orphans.
- Types were not refreshed for concepts that lost mentions; two names resolving to one concept made two mentions; the tag limit could be passed by concurrent requests (the meeting row is now locked); two projections of one meeting could interleave (advisory lock); the inspector was unbounded.
- Frontend: the inspector closes when filters change, and a refetch with the same graph no longer resets zoom and pan.

Accepted: a Summary alias merges a later mention by exact match (ADR 0019); relationship inserts from concurrent projections may deadlock and are retried.

### Graph size by meeting length (2026-10-02)

The operator saw the 73-minute podcast sparse in the graph. Nothing had failed (every job and projection completed, no item dropped): prompt v4 to v8 asked for "at most 15 concepts" and the schema sent to the model enforced 15 for every meeting, so a long meeting kept only its 15 most prominent subjects, against 30 with the first prompt that had no cap. Prompt `brain-extraction-v9` scales the number of concepts and relationships with the length of the meeting: up to 15 minutes 15 and 20, up to 45 minutes 25 and 35, longer 40 and 60 (`graph_limits`). The prompt, the schema (`maxItems`) and the validation use the same numbers, so an answer is still bounded; the model is told that a longer meeting covers more subjects and to name them all up to that number. Only the meetings longer than 15 minutes were extracted again.

### Second pass for relationships (2026-10-02)

After the larger graphs the operator asked how to get more relationships. Measured on the meetings longer than 15 minutes: of 72 relationships 59 were the generic `related_to` and only 13 had a meaningful type, and many concepts stayed unconnected (14 of 31 in "Guillem"), because one request does everything at once and relationships get the least attention at the end of a long answer. Prompt `brain-extraction-v10` adds a second request, made right after the first is validated, that gets the same meeting plus the list of concepts (those without any relationship marked) and the relationships already found, and returns relationships only: exact concept names, a citation from the transcript or notes, the most specific type with an example of each, `related_to` only when nothing else fits, and nothing when the meeting states nothing more. Its answer is validated like the first pass's (known ends, a citation, no repeats, the size limit of the meeting length) and merged. It is best effort: if it fails the extraction keeps what the first request found, and the failure is recorded on its own `llm_runs` row (prompt version `…:relations`) and in the result (`relations_pass`), never as a failed job. A hard rule remains: nothing is created from co-occurrence, every relationship cites what states it. Real result on the four meetings longer than 28 minutes: relationships 62 to 130 and concepts with at least one relationship 77 of 114 to 113 of 123; the generic `related_to` fell from 82 % to 73 % of them (33 specific ones against 13), so the types stay mostly generic. On the 73-minute podcast the second request was cut by the operator's proxy (the new prompt is read from scratch and that takes longer than the proxy waits), so it kept the first pass; the second request is therefore tried twice, because the model keeps what it read.

## Decisions

See [ADR 0019](../adr/0019-summary-concept-extraction-and-graph-projection.md), accepted by the operator on 2026-10-01: the schema of concepts and relationships, the identity rule, the projection job and the tag limits (60 characters, 20 tags per meeting) are decisions this record makes where the documents are silent.

## Files changed

- `backend/app/{concepts,tags_api,concept_graph_api}.py` (new), `backend/migrations/versions/{0005_concepts,0006_concept_identity_by_name}.py` (new)
- `backend/app/{models,summary,summary_worker,brain_jobs,brain_worker,brain_retrieval,brain_api,brain_backfill,meetings,meeting_contracts,main}.py`
- `backend/tests/integration/{test_tags,test_concept_graph,test_brain_pipeline}.py`, `backend/tests/test_summary.py`
- `frontend/src/features/meeting/MeetingTags.tsx`, `frontend/src/features/brain/{ConceptGraph,ConceptGraphSection,ConceptInspector,conceptGraphApi,links}.ts*`, `frontend/src/features/brain/BrainPage.tsx`, `frontend/src/features/meeting/MeetingPage.tsx`, `frontend/src/features/meetings/MeetingsPage.tsx`, `frontend/src/{api.ts,styles.css}`, `frontend/package.json` (Cytoscape.js)
- `frontend/tests/e2e/tags-graph.spec.ts`
- `docs/adr/0019-*.md`, `docs/meeting-processing-flow.md`, `docs/redis.md`

## Validation

- Migration: upgrade, `alembic check` (no drift), downgrade to 0004 and upgrade again on PostgreSQL. `0006` on a copy of the real database: eight duplicate groups merged, no self-relationship or orphan occurrence, no drift, downgrade and upgrade again.
- Unit: Summary validation of concepts and relationships (an alias naming another concept dropped, merge by normalized name whatever the type, uncited and unknown-end items dropped, caps, old outputs still valid, bad type rejected, schema requires both lists, bracketed segment ids).
- E2E (mocked backend): tags are added, suggested, reused, refused (client and server side), removed and survive a reload; the list shows and filters by tag; the graph draws nodes and edges, a list of the same concepts selects them, the inspector shows aliases, meetings, the cited moment as a link that plays, manual tags without evidence and relations; filters go to the server; empty, partial, truncated and failed states; the tag chosen in the question form is sent as a filter; loose concepts are hidden and counted by default, shown on request and included while searching; the list filter matches a tag typed with another capitalization.
- Integration: tags (idempotence, reuse, removal, limits, suggestions, related-to, cascade, list), projection (one job per extraction, merge by name and alias including Catalan, one node across types shown with the type used most, a same-named tag kept apart, no similarity merge, one mention per concept, filters, bound, loose concepts left out and counted, edges and connection scoped by tag, meeting and type, a tag without meetings does not connect, inspector, re-projection, stale, deletion with type refresh, alias pruning and 404 for orphans) and the Brain tag filter.

## Risks

- Summary now asks for more output; quality of the extracted concepts on real meetings is not measured yet.
- Without aliases, "Kafka" and "Apache Kafka" stay two nodes, and so do Spanish and Catalan spellings ("documentación", "documentació").
- Two different subjects with the same name are one node (accepted by the operator).

## Next action

None for this increment. Open, not decided: aliases in the other language (Spanish/Catalan) so both spellings join by exact alias; generic names ("proyecto", "projecte") are among the most shared nodes; the meeting "guillem 2" cannot be extracted because the operator's reverse proxy in front of Ollama cuts requests at about 90 s (`LLM_HTTP_ERROR` after three attempts), which streaming the model's answer would avoid.
