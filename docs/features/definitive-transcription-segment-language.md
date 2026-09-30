# Feature: Definitive transcription segment language
Status: complete
Last updated: 2026-09-18

## Problem and target user
The definitive transcript identifies a global language, but reviewers cannot see the language associated with each displayed segment.

## Desired outcome
Each definitive transcript segment displays its ASR-provided language, or a neutral unavailable state when no segment language exists.

## Scope
- Add optional language metadata to definitive transcript segments.
- Persist and expose that metadata through the existing transcript contract and definitive event.
- Render the language in each definitive segment in the frontend.
- Keep provisional transcript rendering and behavior unchanged.

## Acceptance criteria
- A definitive segment with `language="es"` displays `Idioma: es`.
- Existing transcripts without segment language remain readable and display `Idioma no disponible`.
- Segment language is sourced from ASR metadata and is not inferred from text or copied from global provenance by the frontend.
- ASR failure behavior remains unchanged.

## States and failure behavior
Known language is shown per segment. Missing language is shown as unavailable. A missing language never blocks persistence or display of the definitive transcript.

## Data and provenance constraints
The definitive transcript remains the source of truth. Segment language is optional and comes from ASR metadata. No meeting content or secrets are added to logs or tests.

## Dependencies and assumptions
The current WhisperX result provides one detected language per processed track; that value is attached to each segment generated from the track.

## Implementation record
The optional language field now flows from ASR segments and the ASR result fallback into definitive transcript segments. The frontend renders it in each definitive segment metadata row and shows `no disponible` when absent.

Files changed:
- `backend/app/asr.py`
- `backend/app/audio.py`
- `backend/app/contracts.py`
- `backend/app/live_pipeline.py`
- `backend/app/transcripts.py`
- `backend/tests/integration/test_audio_websocket.py`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/tests/e2e/audio-reconnection.spec.ts`
- `docs/features/definitive-transcription-segment-language.md`

## Validation
- `py -m pytest tests/integration/test_audio_websocket.py -q -k persists_frames_and_updates_meeting` passed.
- `docker exec docker-frontend-1 npm run build` passed, including TypeScript compilation and Vite build.
- The E2E regression is present, but its execution is blocked in the container because Playwright cannot launch the downloaded Chromium binary (`ENOENT`).

## Risks and open questions
True mixed-language detection within one audio track remains outside this increment.

## Next action
Propagate optional segment language and render it in the definitive transcript view.