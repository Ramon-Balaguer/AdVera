# ADR 0019: Brain concept extraction and concept graph projection

## Status

Proposed (2026-09-30); fills a gap the documentation leaves open and awaits human review.

## Context

The concept graph is the only graph (Phase 0 decision in `rebuild-bootstrap-and-governance.md`; `concept-graph.md`). The documents describe its tables (spec §9), its read API (`GET /api/memory/concept-graph`), manual tags as shared concepts (ADR 0013) and the rule that a projection is triggered when Brain completes (`meeting-processing-flow.md`, `redis.md`). They never define what Brain must output for concepts and relationships: no JSON schema, no concept types, no relationship vocabulary, no rule for merging the same concept across meetings. Spec §11 lists "hechos, ideas, memorias y relaciones" without fields, and the rebuilt Brain (`rebuild-brain-extraction.md`) extracts only a summary, topics, decisions, actions, open questions and risks.

## Decision

**Extraction.** Brain prompt version `brain-extraction-v2` adds two lists to the model output, both optional so an older output still validates.
- `concepts`: `{name, type, aliases, evidence_ids}`. `type` is one of `topic`, `person`, `organization`, `project`, `product`, `technology`. At most 15 are requested, 30 kept.
- `relationships`: `{source, target, type, evidence_ids}`, where `source` and `target` are names of concepts of the same output. `type` is one of `related_to`, `depends_on`, `part_of`, `decided_by`, `assigned_to`, `constrains`, `derived_from`, `verifies`. At most 40 kept. The list is the one in `brain-memoria-global.md` without `supersedes` (future work, spec §12) and with `part_of` added, which the model needs to express containment.
- A concept or relationship without at least one valid citation is dropped and counted in `dropped_items`, like every other item (spec §3.2). Concepts with the same type and normalized name in one output are one (evidence and aliases merged). A relationship whose ends are not concepts of this output is dropped, never completed with an invented concept.
- Decisions, actions and risks stay facts in the extraction; they are not graph nodes (`concept-graph.md`).
- A new prompt version changes the job idempotency key, so each meeting gets one new extraction, which is how existing meetings are backfilled.

**Identity.** Two mentions are the same concept only when their normalized names match (lower case, no accents, collapsed spaces, no punctuation at the ends, at most 80 characters), within the same type, or when an alias Brain gave matches exactly. Nothing is merged by similarity: a candidate that could be two concepts stays separate. A name that matches several concepts keeps the exact-key one or none. Manual tags use the same function with type `tag`.

**Projection.** When a Brain job completes, its worker schedules a `memory_index_jobs` row with `kind = "concepts"`, `source_brain_job_id` set and `projection_version = "memory-concepts-v1"`, published on `advera:memory:index` by id only. The Memory index worker, for that kind:
1. revalidates that the transcript is still the one Brain read (`INPUT_CHANGED` otherwise);
2. refuses to project an extraction that is not the meeting's latest (`STALE_EXTRACTION`, not retried);
3. in one transaction deletes that meeting's previous mentions and relationship occurrences, then resolves each concept and inserts its mention, each relationship (once, globally) and its occurrence;
4. completes the job with a lease-fenced write.

Chunk indexing does not wait for Brain. Concepts and relationships are global and are kept when a meeting stops mentioning them; a concept nobody mentions or tags is not shown. Deleting a meeting deletes its mentions, occurrences and tag assignments by cascade.

**Evidence.** Mentions and occurrences keep their evidence as JSON (`segment_id`, `start`, `end`, `speaker`, `track`), the shape Brain already stores. `memory_evidence.relationship_id` stays without a foreign key: chunk evidence and concept evidence have different lifecycles, and a second evidence table would duplicate the JSON. The inspector resolves each cited segment to its text from the definitive transcript at read time.

**Tags.** As ADR 0013: a tag is a concept of type `tag` assigned to a meeting (`memory_concept_assignments`, one per meeting and concept), with no evidence. Limits chosen here, which the records left open: 60 characters per tag and 20 tags per meeting. A tag named exactly like an existing non-tag concept gets a `related_to` relationship with `source_type = "manual_user"`, best effort.

**API.** `GET /api/memory/concept-graph` (filters `type`, `q`, `meeting_id`, `tag`, `limit`, at most 500 nodes, most shared first; dangling edges removed) and `GET /api/memory/concepts/{id}` (the inspector), both read-only. Memory search gains a `tag` filter resolved before ranking.

## Consequences

- Every Brain extraction asks the model for more output, so runs get somewhat longer; the extraction stays bounded by the caps above.
- The same real-world thing named differently in two meetings ("Kafka" and "Apache Kafka" without an alias) stays two nodes until an alias or a manual decision links them. This is the price of never merging by similarity.
- A concept's meetings are known through mentions; a tag's meetings through assignments. The graph unions both.
- Reprocessing a meeting replaces its own mentions only; other meetings' evidence is untouched.

## Validation and rollback

Unit tests cover the schema and the validation rules; integration tests against PostgreSQL cover scheduling, projection, merging by name and alias, no merge by similarity, filters, size bound, the inspector, stale extractions, re-projection without duplicates and meeting deletion. Rollback: stop scheduling concept jobs and remove the routes; migration `0005_concepts` downgrades cleanly. Chunks, transcripts and Brain extractions are unaffected.

## Related records

- [ADR 0013: Manual meeting tags as memory concepts](0013-manual-meeting-tags-memory-concepts.md)
- [ADR 0015: Authentication deferred](0015-authentication-deferred-single-user.md)
- [Rebuild concept graph and tags](../features/rebuild-concept-graph-and-tags.md)
