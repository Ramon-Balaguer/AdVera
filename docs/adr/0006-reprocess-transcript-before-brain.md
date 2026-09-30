# ADR 0006: Reprocess the Definitive Transcript Before Brain

## Status

Accepted; partially superseded by ADR 0008 (reprocessing runs as a durable asynchronous TranscriptionJob, not inside the HTTP request).

## Context

A meeting may need a better ASR result after capture. Rebuilding Brain or Memory from an old transcript would preserve stale errors and violate the user's expectation that Reprocesar refreshes the complete analysis.

## Decision

The meeting `Reprocesar` operation reads the stored original tracks, reruns definitive ASR, atomically replaces `transcript.json` only after valid segments exist, and then force-schedules Brain. Memory continues through the existing Brain-derived pipeline. If retranscription fails, the previous definitive transcript remains intact and no new Brain job is scheduled.

The current implementation keeps the HTTP request open while ASR runs in a worker thread. A durable asynchronous transcription job is a future evolution if recording duration or API timeouts require it.

> **Superseded in part (2026-09-30).** The previous paragraph is replaced by [ADR 0008](0008-asynchronous-definitive-transcription-worker.md): "Reprocessing uses the same job boundary and retains the previous transcript until a new valid result replaces it." The rest of this decision (re-read stored tracks, atomic replacement only after valid segments, force-schedule Brain, preserve the prior transcript on failure) still applies.

## Consequences

- Brain input hashes naturally identify the new transcript version.
- Old derived results may remain visible until the new pipeline completes and must be treated as stale by hash-aware consumers.
- Reprocessing is safe against failed ASR but not a historical transcript versioning system.
- Long recordings may need an explicit job/status contract later.

## Validation and rollback

Validate successful reprocessing, no-audio blocking, provider failure preservation and scheduling order. Rollback by disabling the endpoint or routing definitive ASR back to WhisperX; the prior transcript remains available when a replacement fails.

## Related records

- `docs/features/meeting-reprocess-transcription.md`
- `docs/features/historical-memory-backfill.md`
- `docs/features/capture-lock-after-memory.md`
