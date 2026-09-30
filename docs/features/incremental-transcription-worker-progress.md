# Feature: Incremental transcription worker progress
Status: complete
Last updated: 2026-09-25

## Problem and target user
Users waiting for definitive transcription cannot distinguish an active worker from a stalled one because the job percentage remains at zero until the whole meeting finishes.

## Desired outcome
Expose an honest, incremental percentage based on completed audio tracks while preserving the definitive transcript as the source of truth.

## Scope
- Persist progress after each available microphone or system track completes.
- Keep the existing polling response and job fields.
- Preserve provider selection, fallback behavior, and final transcript processing.
- Do not estimate progress inside an individual ASR call.

## Acceptance criteria
- A two-track job reports `0/2`, then `1/2`, then `2/2` at the corresponding track boundaries.
- `progress` is monotonic and equals `processed_tracks / total_tracks` until final completion.
- The current track and `transcribing` stage are persisted while a track is processed.
- Retries do not duplicate completed-track counts.
- Completion still reports `progress = 1.0` and `stage = completed`.

## States and failure behavior
Queued and failed jobs retain zero or the last confirmed progress. A provider failure does not emit a completed-track event. A lost worker lease prevents further progress writes.

## Data and provenance constraints
Progress is operational metadata derived only from available audio tracks. It is not transcript content, quality evidence, or provisional transcript data.

## Dependencies and assumptions
The existing `TranscriptionJob` progress fields and polling endpoint are sufficient. The ASR provider does not expose a stable internal progress callback, so per-track progress is the smallest reliable increment.

## Implementation record
- Add a callback at the track boundary in `reprocess_stored_audio`.
- Persist callback events from `process_transcription_job` through the worker event loop.
- Add regression coverage for callback ordering and persisted intermediate progress.

## Validation
- `python -m pytest tests/test_reprocessing.py tests/test_transcription_worker.py` from `backend`: 3 passed.
- VS Code diagnostics report no errors in the changed Python files.

## Risks and open questions
A long individual track can remain at the same percentage while its ASR call runs. Real-time WebSocket delivery remains outside this slice.

## Next action
Expose the persisted fields in the existing meeting UI if a more visible progress experience is needed.
