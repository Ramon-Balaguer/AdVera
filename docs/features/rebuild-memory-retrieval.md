# Feature: Rebuild Memory indexing and cited Q&A
Status: in progress
Last updated: 2026-09-30

## Objective

Make every definitive transcript searchable across meetings, and answer questions with sources that open the meeting at the cited second (spec §13-15; ADR 0001, 0002; `brain-memoria-global.md`).

## Scope

In scope:
- `memory_index_jobs`, `memory_chunks`, `memory_evidence` and `memory_query_runs` (migration `0004_memory`, spec §9):
  - `vector(1024)` with an HNSW cosine index;
  - a GIN full-text index on `to_tsvector('simple', content)`.
- **Indexing** (`advera:memory:index`):
  - the job is created once the definitive transcript commits;
  - it revalidates that the transcript is definitive and matches the job hash;
  - chunks follow speaker turns (at most 800 characters or 60 s) and never split a segment;
  - BGE-M3 embeddings, with one evidence row per segment;
  - the meeting's previous projection is replaced atomically.
- **Degraded mode:** if embeddings stay unavailable on the last attempt, the text chunks are kept, the job records `EMBEDDING_*`, and the overview reports `partial`.
- **Hybrid retrieval in PostgreSQL** (`postgresql-native-hybrid-memory-search.md`):
  - filters (meetings, language, speaker, dates) are applied in SQL before ranking;
  - full-text and vector candidates (50 each) are fused with RRF (k = 60).
- **Queries** (`advera:memory:query`): `queued → retrieving → synthesizing → completed | empty | failed`.
  - The LLM sees exact definitive segments under keys `S1…Sn` (`brain-evidence-segment-alignment.md`).
  - Citations outside the context are removed. An insufficient or uncited answer becomes `empty`.
  - With no retrieved evidence the LLM is not called.
  - An unavailable LLM gives `failed`, and the retrieved evidence is kept.
  - If Redis is down at creation, the run fails with `QUEUE_UNAVAILABLE`.
- **API:**
  - `POST /api/memory/query`;
  - `GET /api/memory/query/{id}`;
  - `WS /ws/query/{id}` (`brain-query-results-websocket.md`), with HTTP as the recovery path;
  - `GET /api/memory/overview`.
- **Backfill:** `python -m app.memory_backfill [--brain] [--rebuild]` (`historical-memory-backfill.md`).
- **UI:**
  - A "Memoria" page with a question field (Ctrl/⌘+Enter), language and date filters, WebSocket states, the answer and its sources.
  - Each source links to `/meetings/{id}?at=<s>&segment=<id>`.
  - The meeting page highlights that segment and positions the audio at the cited second.

Out of scope: the concept graph, tags and the timeline (next increment), editing memories, and reindexing from the UI.

## Acceptance criteria

1. No chunk, embedding or answer is built from provisional data. Every stored chunk carries the definitive transcript hash.
2. Every chunk resolves to meeting, segments and timestamps through `memory_evidence`.
3. Retrieval uses both modalities with filters applied first. Text-only retrieval still works without embeddings.
4. A factual answer is shown only with citations from the retrieved context. Otherwise the result says there is no evidence.
5. A source opens the meeting at the cited segment and second.
6. Memory failures never touch the transcript or audio. Deleting a meeting deletes its Memory data.

## Implementation state

Backend, worker, API and UI are implemented and tested against real PostgreSQL + pgvector and Redis with deterministic fake embeddings and a scripted LLM. A real run with BGE-M3 and the operator's Ollama server is pending.

## Decisions

- The index job is scheduled from the definitive transcript, not from Brain completion, because no Brain-dependent projection exists yet. The concept and relationship projection will be triggered by Brain completion when the concept graph is built. The canonical flow and `redis.md` are updated in this change.
- RRF runs in Python over the two bounded SQL candidate lists: 50 ids each, so the corpus is never materialized. The spec record places fusion in SQL; the observable ranking is the same.
- The full-text configuration is `simple`: no language-specific stemming. Catalan, Spanish and English share one index, and vector search covers word-form variation.
- `memory_query_runs` snapshots the LLM model, base URL and output language, like Brain jobs (ADR 0009).
- `memory_evidence.relationship_id` exists without a foreign key; the key arrives with the concept graph.

## Files changed

- `backend/app/{embeddings,memory_indexing,memory_retrieval,memory_answer,memory_jobs,memory_worker,memory_api,memory_backfill}.py` (new), `backend/app/{models,config,main,transcription_worker}.py`, `backend/migrations/versions/0004_memory.py`, `backend/pyproject.toml` (pgvector, the `memory` extra), `backend/Dockerfile` (`INSTALL_EXTRAS`)
- `backend/tests/test_memory.py`, `backend/tests/integration/test_memory_pipeline.py` (new)
- `frontend/src/features/memory/MemoryPage.tsx` (new), `frontend/src/features/meeting/MeetingPage.tsx` (deep links), `frontend/src/{App.tsx,styles.css}`, `frontend/tests/e2e/memory.spec.ts` (new)
- `docker/compose.dev.yml` and `docker/compose.nvidia.yml` (`memory-worker`)
- `docs/meeting-processing-flow.md`, `docs/redis.md`

## Validation

- Unit (8): chunk turns and caps, majority language, RRF, exact-segment context, citation validation, vector dimension and finiteness.
- Integration against real PostgreSQL + pgvector and Redis (12):
  - indexing with 1024-dim embeddings and evidence;
  - a cited answer linking to meeting, segment and time;
  - vector search finding what full text misses;
  - no evidence gives `empty` without an LLM call;
  - an uncited answer is rejected;
  - an unavailable LLM keeps the evidence;
  - filters applied before ranking;
  - embeddings unavailable gives `partial` with text retrieval still working;
  - WebSocket states;
  - Redis down gives `QUEUE_UNAVAILABLE`;
  - an unconfigured LLM is rejected;
  - deletion cascades.
- E2E: the question goes through WebSocket states to an answer and sources; a source opens the meeting with the segment highlighted and the audio at 12 s; no evidence and no LLM are handled.
- Migrations: upgrade, downgrade and upgrade on PostgreSQL; `alembic check` shows no drift; the HNSW and GIN indexes exist.

## Risks

- BGE-M3 needs about 2.3 GB of weights and GPU memory next to the ASR models.
- The `simple` full-text configuration does not match word variants such as "ampliar" and "ampliaremos"; vector search compensates.

## Next action

Real run: backfill the existing meetings with BGE-M3, then ask cited questions through the operator's Ollama server.
