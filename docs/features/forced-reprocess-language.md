# Feature: One-off forced language for meeting reprocessing
Status: partial
Last updated: 2026-09-30

## Objective

Allow a user to reprocess one stored meeting with an explicit ISO 639-1 language code, such as `ca`, when MOSS autodetection is incorrect.

## Scope

The optional language is accepted by the meeting reprocess endpoint, stored on the asynchronous transcription job, and sent to MOSS and its fallback for that job only. Normal transcription remains autodetected and no meeting language preference is persisted.

This is a narrow, operator-initiated exception to the autodetection-only rule in [ADR 0014](../adr/0014-original-language-transcription.md), not a language-preference feature. It is recorded here rather than as an ADR because it changes no ownership boundary, contract or source-of-truth rule: it only adds an optional per-request field to an existing endpoint and leaves the meeting row untouched.

## Acceptance criteria

- `POST /api/meetings/{meeting_id}/reprocess` accepts `{ "language": "ca" }`.
- Invalid language values are rejected before a job is created.
- MOSS receives `language=ca` for each track in the forced job.
- Requests without a language continue sending no language override.
- An active transcription job prevents a second reprocess request for the same meeting.

## Implementation state

Implemented.

## Decisions

- Accept lowercase two-letter ISO 639-1 syntax only.
- Keep the override on `TranscriptionJob`, not `Meeting`.
- Propagate the override to WhisperX if MOSS falls back.

## Files changed

- `backend/app/brain_api.py` — `ReprocessRequest` and the `POST /{meeting_id}/reprocess` route
- `backend/app/reprocessing.py` — reads the stored tracks and applies the override
- `backend/app/transcription_worker.py` — carries the override into the provider request
- `backend/app/moss_asr.py` — forwards the language to MOSS
- `backend/migrations/versions/0015_transcription_requested_language.py` — nullable `requested_language` on the transcription job
- `backend/tests/test_reprocessing.py` — forced and autodetected paths

## Validation

- Focused reprocessing and MOSS provider tests cover forced and autodetected requests.

## Risks

- The final language still depends on provider output when the provider returns explicit metadata.

## Next action

Run migration `0015` and reprocess the Catalan meeting with `{ "language": "ca" }`.