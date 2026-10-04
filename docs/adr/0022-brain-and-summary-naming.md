# ADR 0022: Brain is the knowledge of all the meetings; Summary is what is extracted from one

## Status

Accepted (2026-10-04), by the operator, for commercial reasons.

## Context

Until now the code and the documents called **Brain** the extraction made from one meeting (summary, decisions, actions, concepts) and **Memory** everything built on top of it: the index, the cited search, the concept graph and the timeline. The product name that should carry the value is **Brain**, and the extraction of one meeting is better described as the **summary of the meeting**.

## Decision

- **Brain** is the search, the concept graph, the timeline and the index and workers behind them. In the interface: Brain / Cerebro / Cervell ("Search the brain", "Brain graph"); the side menu entry shows a brain icon and the text "Brain" in the three languages. The page lives at `/brain`.
- **Summary** is the extraction of one meeting, with the short name `summary` in the code (modules, classes, tables, queue, `/api/meetings/{id}/summary`). In the interface: Meeting summary / Resumen de la reunión / Resum de la reunió.
- Everything is renamed, with no old name kept: modules, classes, tables, columns, constraints and indexes (migration `0009_brain_naming`), queues (`advera:summary:jobs`, `advera:brain:index`, `advera:brain:query`), settings and environment variables (`SUMMARY_*`, `BRAIN_*`), API paths (`/api/brain/*`, `/ws/brain/query/{id}`, `/api/meetings/{id}/summary`), Compose services (`summary-worker`, `brain-worker`), the optional `brain` extra, front-end routes, files and texts, and the documents.
- Values that only identify what produced a stored row are **not** renamed, because changing them would make every result look out of date and queue the model again for every meeting: the prompt version `brain-extraction-v10` and the projection versions `memory-chunks-v1` and `memory-concepts-v1`.
- The two words are swapped (memory becomes brain and brain becomes summary), so the migration and the documents were rewritten in one pass for each name, never one after the other.

## Consequences

- Old API paths, queue names and environment variables stop working. AdVera is single-user with no external clients, but a `.env` that sets `BRAIN_QUEUE_NAME` or `MEMORY_*_QUEUE_NAME` must be updated.
- Queues are new streams: messages left in the old ones are not read. Jobs are not lost, because reconciliation republishes from PostgreSQL what is queued or stale; the old streams are deleted after the deployment.
- Records written before this date keep their content, rewritten with the new names; where an old text said "memory" in the sense of RAM it was left as it was.

## Validation and rollback

The migration was run on a copy of the real database: row counts per table are identical, no object keeps the old names, and `downgrade` restores every name exactly. Rollback: `alembic downgrade 0008_notes_speakers` and the previous commit.

## Related records

- [Rebuild Brain naming](../features/rebuild-brain-naming.md)
- [ADR 0019: Summary concept extraction and concept graph projection](0019-summary-concept-extraction-and-graph-projection.md)
