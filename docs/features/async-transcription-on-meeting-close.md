# Asynchronous Transcription on Meeting Close
Status: partial
Last updated: 2026-09-30

## Product Owner brief

### Problem

Closing a meeting currently keeps the audio WebSocket open while definitive MOSS or WhisperX transcription runs. Long recordings make the close operation slow and vulnerable to client disconnects.

### Target user

An AdVera user who stops a meeting and expects the recording to be safely accepted immediately while definitive transcription continues in the background.

### Desired outcome

Stopping a meeting returns quickly, preserves the original tracks, and exposes durable transcription progress and recovery without allowing Summary or Brain to consume provisional or incomplete data.

### Smallest useful increment

Persist a transcription job, enqueue it on a dedicated Redis Stream, process it in a separate worker, and expose its durable state while preserving the existing definitive transcript contract.

### In scope

- Durable `TranscriptionJob` persistence and idempotency.
- Dedicated `advera:transcription:jobs` Redis Stream and worker.
- MOSS with the configured WhisperX fallback.
- Durable progress and status reporting with WebSocket events when connected.
- Atomic definitive transcript publication.
- Summary and Brain scheduling after successful definitive transcription.
- Asynchronous reprocessing while preserving the previous transcript until success.
- Compose, migrations, tests and processing-flow documentation.

### Out of scope

- Changing the ASR provider boundary or removing MOSS/WhisperX fallback.
- Feeding provisional transcript data into Summary, Brain, embeddings or graph projection.
- Full historical transcript versioning.
- Moving live PCM capture buffers to Redis.

### User acceptance criteria

- `stop` persists both available PCM tracks and returns without waiting for definitive ASR.
- A durable queued transcription job exists before Redis enqueue.
- Redis receives only the transcription job identifier.
- A worker can recover a queued job after Redis or worker interruption.
- A valid result writes `transcript.json` atomically and changes the meeting to `ready`.
- Summary and Brain are scheduled only after the definitive transcript is committed.
- MOSS failure uses the configured WhisperX fallback when enabled.
- Empty or invalid output does not publish a successful transcript.
- Reprocess returns asynchronously and preserves the prior transcript when the new job fails.
- The client can recover status through HTTP after the WebSocket closes or disconnects.

### States and failure behavior

- Meeting: `processing` while transcription is queued or running; `ready` after success; `failed` after retry exhaustion.
- Job: `queued`, `running`, `completed`, `failed`.
- Redis enqueue failure leaves the persisted job queued for reconciliation.
- A stale worker lease can be recovered and re-enqueued.
- Definitive ASR failure preserves original audio and any prior transcript.
- Summary and Brain failures do not damage the definitive transcript.

### Data and provenance constraints

- The definitive transcript remains the only intelligence input and retains source audio provenance and hashes.
- The transcription job is keyed by meeting, source-track hash, provider and model.
- Errors and logs must be sanitized; no tokens, full audio, or real meeting content may be exposed.
- Transcript replacement is atomic and occurs only after valid definitive segments exist.

### Assumptions and open questions

- ASR runs in a separate worker with access to the same meeting storage and provider configuration.
- Detailed progress is persisted and emitted over WebSocket when a connection is available; HTTP remains the durable recovery path.
- A track with no audio is skipped; a provider failure follows the existing fallback policy. A complete failure or empty merged result fails the job.
- The first increment keeps one current transcript per meeting; historical versions remain out of scope.

## Objective

Move definitive transcription from the audio WebSocket close handler into a durable background worker without changing the definitive transcript boundary.

## Implementation state

The core asynchronous path is implemented: durable job, Redis enqueue, worker, asynchronous WebSocket close, status endpoint, frontend status recovery and development Compose service. The feature remains partial because removal of the unreachable synchronous ASR branch, durable per-track progress, stale/retry recovery coverage and release validation remain open.

## Decisions

- Use a dedicated ASR worker and Redis Stream, separate from Summary and Brain workers.
- Persist the job in PostgreSQL before publishing its `job_id` to Redis.
- Keep the previous transcript during reprocess until a new valid transcript is atomically published.
- Trigger Summary and Brain only after the definitive transcript transaction is committed.

## ADRs

- [ADR 0002: Definitive Transcript as the Intelligence Boundary](../adr/0002-definitive-transcript-source-of-truth.md)
- [ADR 0008: Asynchronous Definitive Transcription Worker](../adr/0008-asynchronous-definitive-transcription-worker.md)

## Files changed

- `backend/app/models.py`
- `backend/app/config.py`
- `backend/app/transcription_jobs.py`
- `backend/app/transcription_worker.py`
- `backend/app/audio.py`
- `backend/app/meetings.py`
- `backend/app/summary_api.py`
- `backend/migrations/versions/0011_transcription_jobs.py`
- `backend/tests/test_transcription_jobs.py`
- `backend/tests/test_transcription_worker.py`
- `backend/tests/integration/test_audio_websocket.py`
- `docker/compose.dev.yml`
- `scripts/dev.ps1`
- `scripts/dev.sh`
- `docs/meeting-processing-flow.md`
- `docs/redis.md`
- `docs/adr/0008-asynchronous-definitive-transcription-worker.md`
- `frontend/src/App.tsx`

## Validation

- Product discovery and implementation plan recorded before code changes.
- Focused job, worker and WebSocket tests pass (`9 passed`).
- Full backend suite passes (`210 passed`, with three pre-existing dependency/deprecation warnings).
- Docker Compose configuration validates with `docker compose -f docker/compose.dev.yml config --quiet`.
- Frontend build was attempted but remains blocked by pre-existing `cytoscape` dependency/type errors and an unrelated `capture_locked` type mismatch.

## Risks

- ASR model and diarization dependencies must be available in the worker image.
- Progress events can be lost with a disconnected WebSocket, so the HTTP status contract must remain authoritative.
- Concurrent stop/reprocess requests require idempotency and active-job protection.

## Next action

Extract and remove the now-unreachable synchronous ASR branch from `audio.py`, add durable per-track progress and worker recovery tests, then complete frontend build/release validation.
