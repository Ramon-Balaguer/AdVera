# ADR 0001: BGE-M3 and PostgreSQL Memory Retrieval

## Status

Accepted for the first Brain & Memoria architecture/data slice.

## Decision

Use local BGE-M3 embeddings with exactly 1024 dimensions. Store memory data in PostgreSQL with `pgvector`, using `vector(1024)` and an HNSW cosine index for vector retrieval. PostgreSQL full-text search remains a complementary fallback and not a replacement for provenance or the definitive transcript.

The backend depends on `pgvector` for the SQLAlchemy type. The ORM selects `vector(1024)` on PostgreSQL and JSON only for SQLite unit-test databases. Migration `0008_pgvector_memory_embeddings` converts the portable historical column, enables the extension, and creates the HNSW cosine index.

## Assumptions

- The deployment uses PostgreSQL 16 and can install or enable `pgvector`.
- BGE-M3 runs locally in a worker, with CPU as an explicit fallback.
- Chunks, entities, relationships, embeddings and query results are derived and regenerable.
- Definitive transcript hashes and evidence remain the provenance boundary.

## Consequences

- Semantic retrieval remains local and reproducible without making embeddings the source of truth.
- The PostgreSQL schema and index dimensions are coupled to the selected embedding model.
- Derived memory data can be discarded and rebuilt from definitive transcripts and their hashes.

## Validation and rollback

Validate the PostgreSQL migration, vector dimension, HNSW index and hybrid retrieval against a real PostgreSQL/pgvector environment. Rollback by disabling vector retrieval and using the complementary full-text path while preserving the canonical transcript and provenance data.

## Risks

- BGE-M3 can be expensive on CPU and may require substantial cache storage or VRAM.
- Full-text-only operation has lower semantic recall and must expose a partial index state.
- SQLite compatibility covers unit tests only; PostgreSQL migration execution and vector retrieval remain release gates for production.