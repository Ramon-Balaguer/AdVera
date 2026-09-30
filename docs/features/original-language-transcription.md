# Feature: Original-language transcription
Status: complete
Last updated: 2026-09-27

## Objective
Keep every definitive and provisional transcription in the original language of the audio/video. Do not send a language override to ASR; populate `Meeting.primary_language` after definitive transcription from the distinct segment languages. Do not silently translate or force Spanish.

## Product brief
Problem: ASR was globally forced to Spanish even for Catalan and other original-language recordings.
Target user: Meeting reviewers working with multilingual or non-Spanish recordings.
Desired outcome: The transcript preserves the spoken language and records the effective language as provenance.
Smallest useful increment: Apply meeting-level language precedence and provider autodetection by default.

## Scope
- In scope: ASR autodetection for live and definitive flows; a list of detected meeting languages; development defaults without forced Spanish; durable documentation for future multilingual/translations.
- Out of scope: translation, ordered language lists, per-segment language selection, and multilingual decoding in one provider request.

## Acceptance criteria
- No meeting state or settings value sends a language override to live or definitive ASR.
- A new meeting starts with `primary_language=[]`.
- Definitive transcription stores all distinct non-null `segment.language` values in `primary_language`.
- Local Compose and development scripts do not force `ASR_LANGUAGE=es`.
- The definitive transcript remains the original-language source of truth and persists the effective provider language.
- Existing fallback behavior remains intact.

## States and failures
- `configured`: the meeting primary language is used.
- `detected`: no meeting language is supplied and the provider returns a language.
- `unknown`: the provider returns no language; persist `null` without inventing one.
- Provider failures retain current failure/fallback behavior.

## Data and provenance constraints
Translations must be future derived artifacts, never replacements for `transcript.json`. A future multilingual design should preserve source language, target language, provider/model, source transcript hash and translation provenance.

## Future direction
Evaluate an explicit ordered language list for multilingual audio only if the ASR provider supports it. Add translations as separate versioned artifacts linked to the definitive transcript, with the original transcript remaining authoritative.

## Files changed
- `backend/app/audio.py`
- `backend/app/reprocessing.py`
- `backend/app/transcription_worker.py`
- `backend/app/models.py`
- `backend/app/meeting_contracts.py`
- `backend/migrations/versions/0014_meeting_detected_languages.py`
- `backend/tests/test_reprocessing.py`
- `frontend/src/App.tsx`
- `frontend/src/features/meetings/MeetingLibrary.tsx`
- `docker/compose.dev.yml`
- `scripts/dev.ps1`
- `scripts/dev.sh`
- `docs/meeting-processing-flow.md`
- `docs/adr/README.md`
- `docs/adr/0014-original-language-transcription.md`

## Validation
- `backend/tests/test_reprocessing.py`: 4 passed.
- `backend/tests/test_moss_asr.py backend/tests/test_asr.py`: 28 passed.
- `python -m compileall`: passed.
- `backend/tests/test_reprocessing.py backend/tests/test_transcription_worker.py backend/tests/test_moss_asr.py backend/tests/test_asr.py`: 35 passed.
- Alembic migration `0014_meeting_detected_languages` applied successfully; existing Catalan meeting now returns `primary_language: ["ca"]`.
- Compose resolves `ASR_LANGUAGE` to an empty value by default for API and worker.

## Risks and next action
Existing meetings must be reprocessed to correct transcripts already generated with Spanish forced. Next: run focused tests, then reprocess affected meetings with their primary language or autodetection.
