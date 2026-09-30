# Feature: Project baseline and current capabilities
Status: complete
Last updated: 2026-09-30

## Objective

Describe the platform as it is actually built, so a new contributor can orient from this record instead of from a plan. This is an as-built baseline, not a roadmap; per-feature detail lives in the other records linked from the index.

## Scope

AdVera is a self-hosted, AI-first meeting intelligence platform. The transcript is the source of truth. Audio is the origin; the definitive transcript is the only input to intelligence.

Three explicit stages, all implemented:

1. **Live pipeline** — browser or desktop capture, per-track PCM over WebSocket, VAD, 5-15 s windows with overlap, stitching, provisional transcript and live summary.
2. **Definitive transcription** — asynchronous. On meeting close a `TranscriptionJob` is persisted, published to the `advera:transcription:jobs` Redis Stream and processed by a worker that reads the complete stored tracks. MOSS is the definitive provider, WhisperX the explicit fallback.
3. **Intelligence** — Brain extraction, Memory chunking with BGE-M3 embeddings, hybrid retrieval, concept graph and cited Q&A. Runs only from the persisted definitive transcript.

Provisional transcript data never feeds Brain, Memory, embeddings, search or the graph.

### Implemented

- FastAPI backend, React/Vite frontend, Docker Compose development environment.
- Meeting CRUD with derived attendee count, free-text tags mapped onto shared memory concepts, and capture lock after processing.
- Audio: browser microphone capture, native Windows desktop agent with WASAPI loopback, dual independent tracks (`original.pcm` microphone, `system.pcm` system), external media import converted to `system.pcm` via `ffmpeg`.
- Transcript: provisional during capture, definitive after the asynchronous worker, `transcript.json` written atomically, `primary_language` populated with the distinct detected segment languages.
- Reprocessing that re-reads stored audio and can force a single ISO 639-1 language for that job only.
- Brain: structured extraction with `LLMRun` provenance, idempotent jobs, output-language snapshotting.
- Memory: chunking, BGE-M3 embeddings, PostgreSQL/pgvector hybrid retrieval, evidence, entity timeline, concept graph.
- Operations: Redis Streams monitor with consumer-group and pending-job visibility, memory-job repair, system and GPU metrics over WebSocket, persistent runtime settings, Ollama model discovery, QA release gate.

### Not implemented

- Authentication and authorization. `Meeting` has no stable principal, so `created_by` and tag actor ids are nullable. This is the largest remaining gap and it blocks any non-single-user deployment.
- Job cancellation. `cancelled` exists in the event enum but no worker sets it and no endpoint exposes it.
- Tested backup and restore. The design is documented; a real restore has not been exercised.
- Translation artifacts. Deferred by ADR 0014; the original-language transcript is authoritative and translations are a future derived contract.
- Chunked MOSS processing for recordings beyond the two-hour development decode limit.
- AMD hardware validation. Runtime selection is implemented; the hardware is not certified.

## Acceptance criteria

- A user can create, list, open, rename and delete a meeting from the workspace.
- Microphone and system audio are captured as independent tracks and stored before processing.
- A disconnect does not lose audio; the finalization path rebuilds from stored tracks.
- Closing a meeting returns immediately and the definitive transcript appears when the worker finishes.
- An empty or invalid ASR result never surfaces as a successful transcript.
- A failed Brain or Memory job leaves the definitive transcript intact and is visible as a recoverable job.
- Every knowledge item resolves back to meeting, segment and timestamp.
- Removing a meeting removes its audio, transcript, knowledge and tag assignments.

## States and failure behavior

- Meeting: `scheduled`, `recording`, `processing`, `ready`, `failed`, `archived`. Enforced by Pydantic at `backend/app/meeting_contracts.py`; the column is untyped text.
- Transcription job adds a `stage` axis orthogonal to status: `transcribing`, `finalizing`, `fallback`, `retrying`, `requeued`.
- Memory query states: `queued`, `retrieving`, `synthesizing`, `completed`, `empty`, `failed`.
- Definitive ASR failure retains audio and falls back to WhisperX when configured.
- MOSS rejection is surfaced in the meeting screen and the worker console, with a sanitized status and never raw provider text.
- A Redis outage leaves every queue shown as unavailable; durable job state stays in PostgreSQL and no Redis failure may delete audio or the definitive transcript.

## Data and provenance constraints

- The definitive transcript is the only intelligence input. Provisional data is presentation-only.
- Derived knowledge carries `meeting_id`, `segment_id`, timestamps and `llm_run_id`.
- Audio lives outside PostgreSQL under `<AUDIO_STORAGE_PATH>/<meeting_id>/` as `original.pcm`, `system.pcm`, `transcript.json` and `audio_session.json`. The layout is flat; there is no date partitioning.
- ASR receives no language override in normal transcription; providers autodetect and report per-segment language.
- Manual tags are shared memory concepts with empty `evidence_ids` and must not be read as transcript evidence.
- Chain-of-thought is never stored. Secrets and real meeting content never reach logs or tests.

## Decisions

- MOSS is the definitive provider; WhisperX is live and fallback (ADR 0003, 0007).
- Definitive transcription is asynchronous and recoverable (ADR 0008).
- Original-language transcripts are authoritative; translations are deferred derived artifacts (ADR 0014).
- BGE-M3 at 1024 dimensions in pgvector (ADR 0001).
- Redis is transport only; PostgreSQL is the job state and recovery source of truth.

## Files changed

Historical baseline rewrite. No application code changed. See `backend/app/` for the implementation and `docs/adr/README.md` for the decisions.

## Validation

The suite this baseline describes is the current state of `main`. Per-slice validation evidence lives in each feature record. `python -m pytest` in `backend` and the frontend build remain the release checks; the QA gate is tracked separately in `qa-release-gate.md`.

## Risks

- Everything above rests on an unauthenticated API. Until a principal exists, tag ownership, audit and multi-user use are not expressible in the data model.
- MOSS is accepted for development and canary evaluation only. Production enablement requires a licensed or public-corpus canary and a capacity test.
- The MOSS two-hour decode limit and 65536-token context are development values, not a production capacity guarantee.
- ASR defaults in `.env.example` still differ from the Compose and script defaults; a developer who copies it gets WhisperX and forced Spanish.

## Next action

Authentication and RBAC. Until it exists, the remaining roadmap items are blocked behind an API that cannot identify who is calling it.
