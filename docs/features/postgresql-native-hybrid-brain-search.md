# PostgreSQL-Native Hybrid Brain Search
Status: partial
Last updated: 2026-09-21

## Objective
Move brain retrieval into PostgreSQL so filters, full-text search, pgvector similarity, and RRF ranking do not require loading all brain chunks into Python.

## Product Brief

- **Problem:** Brain queries currently materialize all chunks, evidence, entities, and meetings in the worker, then apply filters and rankings in Python.
- **Target user:** AdVera users querying definitive meeting brain.
- **Desired outcome:** Fast, bounded-memory hybrid retrieval with the existing citations and filter behavior.
- **Smallest useful increment:** PostgreSQL returns filtered, text-ranked and vector-ranked brain candidates combined with RRF; the worker no longer ranks the complete corpus in brain.
- **In scope:** Meeting, language, speaker, date, node type, and state filters; PostgreSQL full-text search; pgvector cosine search; RRF; late content-hash deduplication; citation preservation.
- **Out of scope:** Changing the embedding model, chunking, HTTP contracts, transcript finalization, or LLM synthesis.
- **Acceptance criteria:** Retrieval executes through SQL on PostgreSQL; no production query loads all brain chunks for ranking; all existing filters are applied before ranking; definitive-transcript provenance and citations remain valid; SQLite unit tests remain portable.
- **States and failures:** Preserve `retrieving`, `synthesizing`, `completed`, `empty`, and `failed`; text-only retrieval remains available when embeddings are unavailable; vector-only retrieval remains available when full-text search has no match; errors remain sanitized.
- **Data and provenance constraints:** Use only definitive transcript projections. Preserve chunk IDs, content hashes, transcript/input hashes, segment timing, evidence IDs, provider, model, and model version.
- **Dependencies and constraints:** PostgreSQL with the `vector` extension is required for the production SQL path. The existing GIN and HNSW indexes should be reused. SQLite is a unit-test backend only.
- **Assumptions:** `Meeting.created_at` remains the date filter source; `brain_chunks.embedding` remains `VECTOR(1024)`; the existing RRF constant remains 60.
- **Open questions:** Whether CI provides PostgreSQL with pgvector; the production candidate multiplier for approximate HNSW retrieval; acceptable ranking differences between Python token counts and PostgreSQL FTS.
- **Recommended next agent:** Architecture/Data and Intelligence, followed by QA/Security.

## Scope

The production retrieval path will use SQLAlchemy/PostgreSQL CTEs for filtered chunks, full-text ranking, vector ranking, RRF fusion, and deduplication. Python will generate the query embedding, build cited context, and synthesize the answer.

## Acceptance Criteria

1. All six retrieval filters are SQL predicates or SQL `EXISTS` predicates.
2. PostgreSQL performs both retrieval modalities and RRF ranking.
3. The worker does not materialize the complete brain corpus for a query.
4. Missing embeddings do not disable textual retrieval.
5. Results retain valid evidence and definitive transcript provenance.
6. Tests cover SQL compilation, worker behavior, migrations, and a real PostgreSQL/pgvector integration path.

## Implementation State

First implementation slice complete. The worker now calls a database-backed retrieval module instead of materializing and ranking the complete corpus in Python. PostgreSQL uses the planned hybrid CTE shape; SQLite retains a bounded SQL-only adapter for portable unit tests.

## Decisions

- Reuse the existing `to_tsvector('simple', content)` GIN index and `vector_cosine_ops` HNSW index.
- Apply filters before ranking, including `node_types` and `state` through SQL existence checks.
- Deduplicate by `content_hash` after RRF fusion.
- Keep the Python retrieval implementation as a temporary reference until SQL integration is verified.

## Files Changed

- `backend/app/brain_sql_retrieval.py`
- `backend/app/brain_worker.py`
- `backend/tests/test_brain_sql_retrieval.py`
- `docs/features/postgresql-native-hybrid-brain-search.md`

## Validation

- `python -m pytest tests/test_brain_sql_retrieval.py tests/test_brain_backend.py -q` -> `15 passed`.
- Pylance diagnostics are clear for the changed application and test files.
- PostgreSQL execution, pgvector binding, index usage, and integration fixtures remain pending because this environment does not have the `pgvector` Python package installed or a PostgreSQL integration service configured.

## Risks

- PostgreSQL FTS ranking is not numerically identical to the current token-count ranking.
- HNSW is approximate and needs an oversized candidate set before RRF.
- JSON evidence/entity links may require a normalized association table for efficient SQL filters.
- SQLite cannot validate PostgreSQL operators or index usage.

## Next Action

Add the normalized evidence/entity association migration, replace JSON-array relationship checks for `node_types` and `state`, and run a real PostgreSQL + pgvector integration test with `EXPLAIN` checks before treating the migration as production-ready.
