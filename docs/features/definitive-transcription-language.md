# Feature: Definitive transcription language
Status: complete
Last updated: 2026-09-18

## Problem and target user
The definitive ASR result detects a language, but the value is currently discarded. Meeting reviewers need the detected language as auditable transcript metadata.

## Desired outcome
The definitive transcript exposes and persists the language returned by the ASR provider.

## Scope
- Propagate the provider language through definitive ASR.
- Store it in `TranscriptProvenance.language`.
- Include the same value in the `transcript.definitive` event and transcript endpoint.
- Keep provisional transcription behavior unchanged.

## Acceptance criteria
- A successful definitive transcription with `language="es"` exposes `provenance.language == "es"` in the WebSocket event and API response.
- `transcript.json` persists the same language value.
- Missing provider language remains `null` without preventing a successful transcript.
- Definitive ASR failures retain the existing failure behavior.

## States and failure behavior
Language detection runs during definitive processing. An unavailable language is represented as `null`; ASR failures still emit `transcript.failed` and do not publish an incomplete definitive document.

## Data and provenance constraints
The definitive transcript remains the source of truth. The language comes from the ASR result or an explicit configured fallback. No meeting content or secrets are added to logs or tests.

## Dependencies and assumptions
The ASR provider returns a single language code for each processed track. A single global language is exposed when all tracks agree; conflicting track languages are represented as unavailable until per-track language metadata is supported.

## Implementation record
The ASR provider now returns segments together with its detected or configured language. The definitive audio workflow preserves one global language only when every processed track reports the same non-null value, and writes it to transcript provenance. Live transcription continues to consume segments only.

Files changed:
- `backend/app/asr.py`
- `backend/app/audio.py`
- `backend/app/transcripts.py`
- `backend/tests/integration/conftest.py`
- `backend/tests/integration/test_audio_websocket.py`
- `docs/features/definitive-transcription-language.md`

## Validation
- `py -m pytest tests/integration/test_audio_websocket.py -q -k persists_frames_and_updates_meeting` passed.
- `get_errors` reports no errors in the changed application, fixture, or integration test files; existing missing optional ASR dependency diagnostics remain in `backend/app/asr.py`.
- The full integration file still has four unrelated/event-timing failures under the local environment; the language acceptance test passes.

## Risks and open questions
Multilingual meetings and per-track language display remain out of scope. Updating `Meeting.primary_language` is deferred.

## Next action
Decide in a later feature whether multilingual meetings need per-track language metadata or should update `Meeting.primary_language`.