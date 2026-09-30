# Meeting Reprocess Includes Definitive Transcription
Status: complete
Last updated: 2026-09-25

## Objective

Make the meeting-page `Reprocesar` action rerun definitive ASR from stored audio before rebuilding Brain and Memory.

## Scope

The endpoint retranscribes the stored microphone and system PCM tracks with the configured definitive provider and fallback, atomically replaces the definitive transcript only after valid output, then schedules the existing forced Brain job. Brain continues to enqueue Memory through the existing pipeline. Live/provisional transcription and manual transcript editing are out of scope.

## Acceptance criteria

- A meeting with stored audio is retranscribed when `Reprocesar` is clicked.
- The previous transcript remains intact if retranscription fails or produces no segments.
- A valid new transcript is persisted before Brain is scheduled.
- Memory continues to rebuild from the new transcript through Brain.
- Meetings without stored audio remain blocked.
- The UI reports that retranscription, Brain, and Memory are being rebuilt.

## Implementation state

Implemented.

## ADRs

- [ADR 0002: Definitive transcript as the intelligence boundary](../adr/0002-definitive-transcript-source-of-truth.md)
- [ADR 0006: Reprocess the definitive transcript before Brain](../adr/0006-reprocess-transcript-before-brain.md)

## Decisions

- Reuse the existing definitive provider selection and WhisperX fallback policy.
- Process each available stored track independently.
- Use the existing atomic transcript writer.
- Keep the existing Brain status response and downstream queue contracts.

## Files changed

- `backend/app/reprocessing.py`
- `backend/app/brain_api.py`
- `backend/tests/test_reprocessing.py`
- `frontend/src/App.tsx`
- `docs/features/meeting-reprocess-transcription.md`

## Validation

- Reprocessing service and meeting API tests: `6 passed`.
- Backend modules compile successfully.
- Frontend build attempted; it remains blocked by existing `ConceptGraph.tsx` dependency/type errors and an unrelated `Meeting.capture_locked` type mismatch.

## Risks

- The HTTP request remains open while definitive ASR runs; long recordings may need a dedicated asynchronous transcription job later.
- Existing transcript and derived artifacts remain visible until the new transcript is successfully persisted.

## Next action

Consider extracting definitive transcription into a durable background job if production recordings make synchronous reprocessing exceed API timeout limits.
