# Feature: Brain extraction from definitive transcript
Status: complete
Last updated: 2026-09-19

## Problem and target user

Meeting reviewers need to turn a definitive transcript into structured, verifiable knowledge. The first Brain slice must expose decisions and prepare the remaining categories without using provisional text or producing knowledge without traceability.

Target user: a person reviewing a completed meeting who needs to identify decisions, summary, topics, actions, open questions and risks.

## Desired outcome

After a meeting's definitive transcript is persisted, AdVera runs a durable extraction job and stores a structured result. The UI prioritizes Decisions and keeps the other categories ready for later display, always with verifiable provenance.

## Smallest useful increment

Extract and persist `summary`, `topics`, `decisions`, `actions`, `open_questions` and `risks` exclusively from the persisted `TranscriptDocument` with `status=definitive`, using a Redis-backed worker. Show Decisions first in the meeting workspace.

## Scope

- Add one extraction contract for the six categories.
- Run extraction through a durable Redis-backed worker.
- Persist jobs, LLM runs and the validated result with SQLAlchemy/Alembic.
- Associate each extracted item with source segment IDs and timestamps.
- Prioritize the Decisions view in the UI.
- Expose explicit pending, processing, completed and failed states.
- Keep the definitive transcript as the only input source.

Out of scope: embeddings, pgvector, search, Q&A, the knowledge graph, live/provisional extraction, chain-of-thought, and unsupported inference.

## Acceptance criteria

- Extraction can start only when a definitive transcript is persisted.
- The job produces the six agreed categories through one structured result.
- The job exposes `queued`, `running`, `completed` and `failed` states.
- A failed job is not presented as completed and can be retried according to the job contract.
- The result is persisted as validated structured JSON through SQLAlchemy/Alembic.
- Each traceable item includes valid source segment IDs and source timestamps when evidence exists.
- The UI prioritizes Decisions and never invents items without a persisted result.
- No provisional or live data reaches the extraction job.
- No chain-of-thought is persisted or exposed.
- A provider failure leaves the audio and definitive transcript intact.

## States and failure behavior

- `blocked`: no valid definitive transcript is available.
- `queued`: the job is waiting for a worker.
- `running`: a worker is processing the definitive transcript.
- `completed`: the structured result is persisted and validated.
- `empty`: the transcript is valid but no supported items were detected.
- `failed`: extraction failed; a sanitized error is retained and the job can be retried.
- Invalid or unreadable transcript input fails explicitly.
- Invalid model output never replaces a valid result.
- Redis or worker downtime leaves the extraction incomplete and recoverable.

## Data and provenance constraints

- The persisted definitive `TranscriptDocument` is the sole source of truth.
- Provisional transcript segments and live summaries cannot feed this extraction.
- The result stores structured JSON rather than unvalidated free text.
- Each item references the meeting, one or more transcript segment IDs and source timestamps.
- Store provider, model, prompt version, input hash, status and execution timestamps.
- Do not store prompts unnecessarily, secrets, real meeting content in tests/logs or chain-of-thought.
- Derived knowledge must remain regenerable from the definitive transcript.

## Dependencies and assumptions

- A definitive transcript can be loaded and validated from the configured meeting storage.
- Redis and a worker are available for durable jobs.
- PostgreSQL/SQLAlchemy and Alembic are the persistence boundary.
- The configured LLM returns only the agreed structured schema.
- The UI can poll the job and result endpoints independently of the audio WebSocket.

## Decisions

- Enqueue only after the definitive transcript is saved and the meeting transaction is committed.
- Use one extraction result for all six categories; Decisions is the first visible category.
- Require evidence references and preserve decision states such as proposed, decided, rejected, superseded or unknown.
- Use an idempotency key derived from meeting, canonical transcript hash, provider, model and prompt version.
- Keep embeddings, retrieval and graph features for later slices.

## Implementation record

Product brief recorded and smallest useful increment implemented.

- Backend contracts define strict structured output, evidence IDs, item state, provenance and explicit job states.
- SQLAlchemy models and Alembic migration persist `brain_jobs`, `llm_runs` and `brain_extractions`.
- The definitive transcript commit creates an idempotent queued job and enqueues it after commit.
- `OllamaClient` centralizes the asynchronous `/api/generate` transport and JSON response decoding for Brain and Live Summary; domain prompts and schema validation remain separate.
- The Redis Stream worker validates provider output, resolves evidence timestamps from the persisted transcript, persists the result and applies bounded retries with stale-job recovery.
- `GET` and `POST /api/meetings/{meeting_id}/brain` expose blocked, queued, running, completed, empty and failed states.
- The meeting workspace polls persisted Brain state, prioritizes Decisions, exposes the other categories and links evidence to audio timestamps.
- The Brain panel now distinguishes `queued` from `running` with an explicit `EN EJECUCIÓN` status, an active indicator and a worker-processing message.
- Audio WebSocket integration tests consume events by semantic type, and transcript failures identify whether they came from `live` or `definitive` ASR.
- Tests cover strict output validation, definitive-only input, idempotency, API blocked state, worker persistence and retry exhaustion.

## Validation

- `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/test_brain.py backend/tests/test_brain_worker.py backend/tests/integration/test_meetings_api.py::test_brain_status_is_blocked_without_definitive_transcript -q` -> 9 passed.
- `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/integration/test_meetings_api.py::test_brain_status_is_blocked_without_definitive_transcript backend/tests/integration/test_audio_websocket.py::test_audio_websocket_persists_frames_and_updates_meeting -q` -> 2 passed.
- `docker compose -f docker/compose.dev.yml -f docker/compose.nvidia.yml config --quiet` -> passed.
- `docker compose -f docker/compose.dev.yml build frontend` and containerized `npm run build` -> TypeScript and Vite build passed.
- Full backend suite -> 59 passed; the WebSocket tests now tolerate provisional and progress events. Two dependency deprecation warnings remain from the installed FastAPI/Starlette test client stack.
- `alembic stamp 0001_create_meetings` followed by `alembic upgrade head` -> schema is at `0002_create_brain_extraction`; `brain_jobs`, `llm_runs` and `brain_extractions` exist.
- `docker compose -f docker/compose.dev.yml -f docker/compose.nvidia.yml up -d --build brain-worker` -> worker image built and `docker-brain-worker-1` is running.
- Containerized frontend build after the running-state UI update -> TypeScript and Vite build passed.
- Redis `XINFO GROUPS advera:brain:jobs` -> consumer group exists with one consumer, zero pending messages and zero lag.
- Running API OpenAPI -> `/api/meetings/{meeting_id}/brain` is registered.
- Real Ollama smoke test -> a definitive transcript produced a persisted `completed` job and `brain_extractions` row; the worker retried two invalid provider responses before accepting the validated result.

## Risks and open questions

- The worker requires Redis, PostgreSQL, a configured Ollama endpoint and the migrated schema in deployment.
- The configured Ollama endpoint and model must remain reachable; provider output is strictly validated and retried when its structure is invalid.
- Runtime Ollama settings are process-local today; worker deployments should use the Compose environment as the shared source of configuration.
- WebSocket consumers must match events by type because provisional and progress events can be added to the stream.
- Long transcripts fail explicitly at the configured context limit; silent truncation is not allowed.

## Next action

Continue monitoring the audio event contract as new provisional or progress stages are introduced; the completed Brain extraction path and regression suite are now validated.