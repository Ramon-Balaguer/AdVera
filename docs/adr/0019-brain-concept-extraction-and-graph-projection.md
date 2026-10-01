# ADR 0019: Brain concept extraction and concept graph projection

## Status

Accepted (2026-10-01, operator review; proposed 2026-09-30, revised 2026-10-01).

## Context

The concept graph is the only graph (Phase 0 decision in `rebuild-bootstrap-and-governance.md`; `concept-graph.md`). The documents describe its tables (spec §9), its read API (`GET /api/memory/concept-graph`), manual tags as shared concepts (ADR 0013) and the rule that a projection is triggered when Brain completes (`meeting-processing-flow.md`, `redis.md`). They never define what Brain must output for concepts and relationships: no JSON schema, no concept types, no relationship vocabulary, no rule for merging the same concept across meetings. Spec §11 lists "hechos, ideas, memorias y relaciones" without fields, and the rebuilt Brain (`rebuild-brain-extraction.md`) extracts only a summary, topics, decisions, actions, open questions and risks.

## Decision

**Extraction.** Brain prompt version `brain-extraction-v2` added two lists to the model output; `brain-extraction-v3` keeps them and asks for every relationship the transcript supports. `brain-extraction-v4` writes concept names in the output language chosen in Settings (ADR 0009), translating common nouns and keeping proper names, with the spoken name as an alias, and forbids concepts made of a generic word alone; this is how Spanish and Catalan spellings of one subject join, by exact alias, without similarity. Both lists default to empty so an older stored output still validates, but they are required in the JSON schema sent to the model: a model constrained to the schema left the optional fields out on the first real run, which produced an empty graph.
- `concepts`: `{name, type, aliases, evidence_ids}`. `type` is one of `topic`, `person`, `organization`, `project`, `product`, `technology`. At most 15 are requested, 30 kept.
- `relationships`: `{source, target, type, evidence_ids}`, where `source` and `target` are names of concepts of the same output. `type` is one of `related_to`, `depends_on`, `part_of`, `decided_by`, `assigned_to`, `constrains`, `derived_from`, `verifies`. At most 40 kept. The list is the one in `brain-memoria-global.md` without `supersedes` (future work, spec §12) and with `part_of` added, which the model needs to express containment.
- A concept or relationship without at least one valid citation is dropped and counted in `dropped_items`, like every other item (spec §3.2). Concepts with the same normalized name in one output are one, whatever type each was given (the first type is kept; evidence and aliases merged). A relationship whose ends are not concepts of this output is dropped, never completed with an invented concept.
- Decisions, actions and risks stay facts in the extraction; they are not graph nodes (`concept-graph.md`).
- A new prompt version changes the job idempotency key, so each meeting gets one new extraction, which is how existing meetings are backfilled.

**Identity.** Two mentions are the same concept only when their normalized names match (lower case, no accents, collapsed spaces, no punctuation at the ends, at most 80 characters), or when an alias Brain gave matches exactly. Nothing is merged by similarity: a candidate that could be two concepts stays separate. A name that matches several concepts keeps the exact-key one or none. An alias that is the name of another concept of the same output is dropped, and the projection resolves every name of an output before it records any alias, so an alias never decides the identity of a name said in the same meeting. Aliases keep the hash of the transcript they came from and are forgotten when no concept projection of that transcript remains (its last meeting was deleted), so a deleted meeting stops steering resolution. A Brain alias still merges a later meeting's mention by exact match; that is the rule, and its risk (an injected or wrong alias) is accepted in exchange for joining "Kafka" and "Apache Kafka". Manual tags use the same function in their own namespace (`memory_concepts.identity = "tag"`), so a tag and a concept with the same name stay two nodes joined by `related_to` (ADR 0013).

The type is not part of the identity (revised 2026-10-01). The first real backfill showed the model typing the same subject differently from meeting to meeting ("documentación" as a topic, a project and a technology; "cliente" as a person and an organization), which split eight subjects into unconnected nodes. The operator chose one node per name, even when the subjects differ. Each mention keeps the type it was given (`memory_concept_mentions.concept_type`) and the concept shows the type its mentions use most (ties: alphabetical). Migration `0006_concept_identity` merges the existing duplicates into the oldest concept: mentions and aliases move to it, relationships are re-pointed (joined to an equal one, or dropped when they would join the concept to itself).

**Projection.** When a Brain job completes, its worker schedules a `memory_index_jobs` row with `kind = "concepts"`, `source_brain_job_id` set and `projection_version = "memory-concepts-v1"`, published on `advera:memory:index` by id only. The Memory index worker, for that kind:
1. revalidates that the transcript is still the one Brain read (`INPUT_CHANGED` otherwise);
2. refuses to project an extraction that is not the meeting's latest (`STALE_EXTRACTION`, not retried);
3. in one transaction, under a per-meeting advisory lock taken before the stale check, deletes that meeting's previous mentions and relationship occurrences, then resolves each concept and inserts one mention per concept (two names of one output that resolve to the same concept share it), each relationship (once, globally) and its occurrence, and refreshes the shown type of every concept that gained or lost a mention;
4. completes the job with a lease-fenced write.

Chunk indexing does not wait for Brain. Concepts and relationships are global and are kept when a meeting stops mentioning them; a concept nobody mentions or tags any more is deleted with its aliases and relationships (operator decision, 2026-10-01: a deleted meeting must leave no names behind), when a meeting is deleted, a tag removed or a meeting re-projected. Every write to the concepts holds one database-wide advisory lock (`lock_concepts`), so a concept being reused by one writer cannot be deleted by another; migration `0007_prune_orphans` removed the orphans left before. Deleting a meeting deletes its mentions, occurrences and tag assignments by cascade.

**Evidence.** Mentions and occurrences keep their evidence as JSON (`segment_id`, `start`, `end`, `speaker`, `track`), the shape Brain already stores. `memory_evidence.relationship_id` stays without a foreign key: chunk evidence and concept evidence have different lifecycles, and a second evidence table would duplicate the JSON. The inspector resolves each cited segment to its text from the definitive transcript at read time.

**Tags.** As ADR 0013: a tag is a concept of type `tag` assigned to a meeting (`memory_concept_assignments`, one per meeting and concept), with no evidence. Limits chosen here, which the records left open: 60 characters per tag and 20 tags per meeting. A tag named exactly like an existing non-tag concept gets a `related_to` relationship with `source_type = "manual_user"`, best effort.

**API.** `GET /api/memory/concept-graph` (filters `type`, `q`, `meeting_id`, `tag`, `limit`, at most 500 nodes, most shared first; dangling edges removed; the meeting and tag filters scope mentions, assignments and relationship occurrences alike, so an edge is drawn only when both ends are shown and it is manual or occurs in a meeting in scope; `include_isolated=false` leaves out concepts with no such drawn edge and returns how many in `hidden_isolated`; the view uses it by default, except while searching, so the graph stays readable as meetings accumulate) and `GET /api/memory/concepts/{id}` (the inspector, bounded to 200 mentions or tag assignments, 100 relations and 10 occurrences per relation), both read-only. Memory search gains a tag filter resolved before ranking (`tags`: meetings with any of them; the single `tag` is still accepted).

## Consequences

- Every Brain extraction asks the model for more output, so runs get somewhat longer; the extraction stays bounded by the caps above.
- The same real-world thing named differently in two meetings ("Kafka" and "Apache Kafka" without an alias) stays two nodes until an alias or a manual decision links them. This is the price of never merging by similarity. The same holds across languages: "documentación" and "documentació" are two nodes.
- Two different subjects with the same name become one node. The operator accepted this to keep the graph connected.
- Loose concepts are still stored, searchable and countable; only the default view leaves them out.
- A concept's meetings are known through mentions; a tag's meetings through assignments. The graph unions both.
- Reprocessing a meeting replaces its own mentions only; other meetings' evidence is untouched.

## Validation and rollback

Unit tests cover the schema and the validation rules; integration tests against PostgreSQL cover scheduling, projection, merging by name and alias, no merge by similarity, filters, size bound, the inspector, stale extractions, re-projection without duplicates and meeting deletion. Migration `0006_concept_identity` was run on a copy of the real database (eight duplicate groups merged, no self-relationship or orphan occurrence left), checked for drift, downgraded and upgraded again. Rollback: stop scheduling concept jobs and remove the routes; migrations `0006` and `0005` downgrade cleanly (merged concepts stay merged). Chunks, transcripts and Brain extractions are unaffected.

## Related records

- [ADR 0013: Manual meeting tags as memory concepts](0013-manual-meeting-tags-memory-concepts.md)
- [ADR 0015: Authentication deferred](0015-authentication-deferred-single-user.md)
- [Rebuild concept graph and tags](../features/rebuild-concept-graph-and-tags.md)
