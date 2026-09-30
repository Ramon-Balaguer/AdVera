# Feature: Rebuild imported media keeps audio only
Status: complete
Last updated: 2026-09-30

## Objective

When a user imports a video or audio file, keep only its extracted audio (`system.pcm`), never the uploaded file.

## Scope

In scope: import storage behavior, ADR 0016, the canonical flow diagram and tests. Out of scope: import history, and the conversion, validation and job flow, which are unchanged.

## Acceptance criteria

1. A successful import leaves only `system.pcm` in the meeting directory, plus `transcript.json` once transcribed.
2. A failed extraction leaves no uploaded file and does not change the meeting.
3. An interrupted import's leftover temporary upload is removed by the next import.

## Implementation state

Implemented.

## Decisions

- Product owner decision (2026-09-30): "si se sube un video lo importaremos y solo guardaremos el audio", applied to audio uploads as well. Recorded as ADR 0016, which partially supersedes ADR 0012.
- The upload is written as a hidden, uniquely named temporary file (`.import-upload-<uuid><ext>`) in the meeting directory, so conversion reads it from the same volume.

## Files changed

- `backend/app/media_import.py`, `backend/app/meetings.py`
- `backend/tests/integration/test_import_transcription.py`
- `docs/adr/0016-imported-media-keeps-audio-only.md`, `docs/adr/0012-external-media-import.md`, `docs/adr/README.md`
- `docs/meeting-processing-flow.md`

## Validation

Integration tests (real PostgreSQL and Redis): the video import leaves only `system.pcm`; a broken `.mp4` returns `422 EXTRACTION_FAILED` with no uploaded file left and the meeting still `scheduled`.

## Risks

A failed conversion cannot be retried server-side; the user must upload again.

## Next action

None.
