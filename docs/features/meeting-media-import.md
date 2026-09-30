# Meeting media import
Status: complete
Last updated: 2026-09-26

## Objective

Allow a user to import one audio or video file from a meeting detail page and process it through the definitive transcription pipeline without requiring a microphone.

## Product brief

- **Problem:** Existing recordings cannot be submitted from the meeting detail page; the current Exportar action is only a disabled placeholder.
- **Target user:** A user who needs to transcribe an existing meeting recording.
- **Desired outcome:** Select or drag a supported media file, extract audio from video when needed, and receive the normal definitive transcript.
- **Smallest useful increment:** One audio/video file per import, stored as the system track and submitted to the existing transcription job pipeline.
- **In scope:** Import button, large modal, file picker, drag-and-drop, audio/video validation, video audio extraction, upload and processing states, and microphone-free meeting states.
- **Out of scope:** Multiple files, live/provisional transcription, export formats, and automatic speaker identity reconciliation.

## Acceptance criteria

1. The meeting detail toolbar displays Importar instead of Exportar.
2. Importar opens a large modal that accepts file picker selection and drag-and-drop.
3. Only supported audio and video files are accepted; invalid files show a retryable error before processing.
4. Video audio is extracted and stored as the system track before the existing definitive transcription job is queued.
5. Imported processing works when no microphone track exists and does not start a microphone/WebSocket capture session.
6. Upload, conversion, processing, completed, and failed states are visible and preserve the meeting on failure.
7. Existing microphone capture and definitive transcript flows remain unchanged.

## States and failures

Idle, modal open, uploading, extracting audio, processing, ready, unsupported file, upload failure, extraction failure, and transcription failure. A second import is rejected while one is active.

## Data and provenance constraints

The definitive transcript remains the source of truth. Imported media is associated with the selected meeting, converted audio is represented by `system.pcm`, and the transcription job keeps its existing input hash, provider, and model provenance. No provisional transcript is sent to downstream intelligence features.

## Decisions and assumptions

- Import updates the selected meeting and uses the system track for the first increment.
- The original uploaded file is retained under the meeting storage directory for provenance and conversion retry.
- No schema migration is needed for the first increment; import metadata is represented by storage files and the existing transcription job.
- Upload validation uses allowlisted media MIME types/extensions and a 5 GiB default size limit; conversion uses the installed media toolchain.

## Validation

- `backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/test_meetings_api.py backend/tests/test_transcription_jobs.py backend/tests/test_openapi_contract.py -q` -> 12 passed.
- `frontend/npm run build` -> passed.
- Workspace diagnostics for the changed frontend and backend files -> no errors.
- The integration regression covers valid system-only import and unsupported media rejection.
- The browser reports upload progress using `XMLHttpRequest.upload.onprogress`.
- Windows cleanup closes the upload before deleting it and retries transient file-lock failures.
- Video imports show a separate extraction/verification state after upload reaches 100%.
- Extracted PCM is checked for a non-empty, complete sample stream before the video source is deleted.

## Risks

Video decoding consumes CPU, disk, and time. Upload limits and executable availability must be verified in the local runtime. A future import-history or richer provenance contract may require a migration and ADR revision.

## Files changed

- `backend/app/media_import.py`
- `backend/app/meetings.py`
- `backend/app/config.py`
- `backend/pyproject.toml`
- `backend/tests/integration/test_meetings_api.py`
- `frontend/src/features/meeting/MeetingImportModal.tsx`
- `frontend/src/features/meeting/MeetingPage.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/adr/0012-external-media-import.md`
- `docs/adr/README.md`
- `docs/meeting-processing-flow.md`

## Risks and next action

The Docker backend includes `ffmpeg`; a Windows host backend needs `ffmpeg` available on `PATH` for video and audio conversion. Upload history is not persisted relationally in this increment. The 5 GiB limit also requires sufficient proxy, temporary disk, and backend storage capacity. If extraction or verification fails, the original video remains available for retry. Next action is to run one real audio and video import through the local Docker stack and verify the worker reaches the definitive transcript.