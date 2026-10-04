# Feature: Separate live and definitive ASR models
Status: complete
Last updated: 2026-09-17

## Objective
Allow deployments to choose a fast WhisperX model for provisional transcription and a more accurate model for the definitive transcript.

## Scope
- Add `ASR_LIVE_MODEL` for provisional transcription.
- Add `ASR_DEFINITIVE_MODEL` for definitive transcription.
- Keep `ASR_MODEL` as the compatibility fallback when either new setting is omitted.
- Cache one ASR provider per stage so the live model cannot be reused for definitive provenance.
- Preserve the existing provider, device, compute type, language and artifact filtering behavior.

## Acceptance criteria
- Live calls use the configured live model with `diarize=False`.
- Definitive calls use the configured definitive model with `diarize=True`.
- Definitive provenance records the definitive model.
- Omitting either new setting falls back to `ASR_MODEL`.
- Existing `ASR_PROVIDER=none` behavior remains unchanged.

## States and failures
Live ASR failures remain retryable and do not prevent the definitive stage from selecting its own provider. Definitive failures leave the meeting failed without publishing a ready transcript; source audio remains available.

## Data and provenance constraints
The definitive transcript is still generated from persisted PCM tracks. Provisional text is not used as definitive input. No credentials or meeting content are added to logs or tests.

## Decisions
- Configuration is deployment-level, not selectable per meeting or user.
- The defaults in `.env.example` and development Compose are `tiny` for live and `small` for definitive.
- `ASR_MODEL` remains supported during migration and is used when a stage-specific value is empty.

## Files changed
- `backend/app/config.py`
- `backend/app/audio.py`
- `backend/tests/integration/conftest.py`
- `backend/tests/integration/test_audio_websocket.py`
- `.env.example`
- `docker/compose.dev.yml`

## Validation
- `python -m compileall -q backend/app backend/tests` passed.
- Focused pytest could not run because `pytest` is not installed in the local virtual environment.
- Integration assertions now distinguish `tiny-test` provisional output from `large-test` definitive provenance.

## Risks
Two WhisperX models may increase brain use if both providers remain loaded in the same API process. CPU deployments should start with `tiny` and `small`; larger definitive models should be evaluated against available RAM and processing time.

## Next action
Recreate the development API container so the new Compose environment variables are active, then install or provide the test dependencies and run the focused integration test.
