# ADR 0008: Asynchronous Definitive Transcription Worker

## Status

Accepted

## Context

The audio WebSocket previously executed definitive MOSS or WhisperX transcription during the `stop` command. Long recordings kept the connection open, made client disconnects affect completion, and left no durable operation to recover if the process stopped during ASR.

AdVera already uses PostgreSQL-backed jobs activated through Redis Streams for Summary and Brain. The definitive transcript remains the intelligence boundary described by ADR 0002.

## Decision

Move definitive transcription to a dedicated `TranscriptionJob` and worker.

When capture stops, the backend persists the original microphone and system tracks, changes the meeting to `processing`, creates the job in PostgreSQL, commits it, and publishes only its `job_id` to the `advera:transcription:jobs` Redis Stream. A dedicated transcription worker consumes the stream, reads the shared audio storage, executes the configured definitive provider with the explicit fallback policy, and atomically publishes `transcript.json` only after valid segments exist.

The worker marks the meeting `ready` and schedules Summary and Brain only after the definitive transcript has been committed. A failed or stale job preserves the original audio and any previous transcript. Reprocessing uses the same job boundary and retains the previous transcript until a new valid result replaces it.

Progress is persisted on the job and may be delivered over the audio WebSocket when connected. The HTTP transcription status endpoint is the durable recovery contract.

## Consequences

- Closing a meeting no longer waits for definitive ASR.
- ASR capacity and model dependencies are isolated from Summary and Brain workers.
- Redis remains a transport; PostgreSQL remains the job state and recovery source of truth.
- The deployment must share meeting audio storage and ASR configuration with the transcription worker.
- The client must handle queued and processing states and recover through HTTP after WebSocket disconnects.
- A new worker, stream, migration, compose service and operational health checks are required.

## Validation

- Unit tests cover job idempotency, Redis enqueue failure, worker completion and downstream job creation.
- WebSocket integration tests confirm `stop` returns `transcript.queued` without waiting for ASR.
- Compose configuration validates the dedicated worker service.
- Full PostgreSQL/Redis worker recovery and real provider smoke tests remain release gates.

## Rollback

Stop the transcription worker and revert the audio close handler to the previous synchronous path while leaving stored PCM and existing definitive transcripts intact. Do not delete queued jobs or audio during rollback; they remain available for a later retry or manual reconciliation.

## Related records

- [ADR 0002: Definitive Transcript as the Intelligence Boundary](0002-definitive-transcript-source-of-truth.md)
- [ADR 0005: Independent Microphone and System Tracks](0005-dual-track-audio-processing.md)
- [ADR 0006: Reprocess the Definitive Transcript Before Summary](0006-reprocess-transcript-before-summary.md)
- [Async Transcription on Meeting Close](../features/async-transcription-on-meeting-close.md)
- [Meeting Processing Flow](../meeting-processing-flow.md)
