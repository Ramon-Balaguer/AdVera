# Memory Embeddings Provider
Status: partial
Last updated: 2026-09-20

## Objective
Make the BGE-M3 memory embedding provider installable, reproducible, and persistent in the development worker.

## Scope
Declare `sentence-transformers`, persist the model cache for `memory-worker`, and validate the 1024-dimensional normalized-vector contract. The definitive transcript remains the only source for embedded chunks.

## Acceptance Criteria
- A clean backend image includes the embedding runtime dependency.
- The worker stores and reuses `BAAI/bge-m3` under `/data/models`.
- Provider output is validated as 1024-dimensional numeric vectors.
- Provider failures remain explicit and retryable; invalid vectors are never marked complete.
- Partial or provisional transcripts are never embedded.

## Implementation State
Implemented in code and Compose; the local Docker image rebuild is still pending because the existing ASR image rebuild stalled while downloading its heavyweight dependencies.

## Decisions
- Keep `sentence-transformers` with `BAAI/bge-m3` as the local provider.
- Keep the existing pgvector dimension at 1024.
- Use a named Docker volume for the model cache in development.

## Files Changed
- `backend/pyproject.toml`
- `backend/tests/test_memory_intelligence.py`
- `docker/compose.dev.yml`

## Validation
- Focused provider and memory tests: 14 passed.
- Compose configuration validates with the persistent `embedding-models` volume attached to `memory-worker`.
- The previous image was confirmed not to contain `sentence_transformers`; a rebuild is required to activate the provider.

## Risks
The first BGE-M3 download is large and CPU inference can be slow. The model cache must have sufficient disk space.

## Next Action
Run `docker compose -f docker/compose.dev.yml build memory-worker` when Docker can complete the dependency download, then verify `import sentence_transformers` and restart the worker.
