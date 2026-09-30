# Feature: Rebuild Catalan in every test set
Status: complete
Last updated: 2026-09-30

## Objective

Product owner decision (2026-09-30): "todas las pruebas tienes que agregar el catalán". Every test set exercises Catalan together with Spanish and English (spec §2, §7, §25).

## Scope

Unit and integration fixtures, the frontend E2E fixtures and the real ASR/diarization smoke.

## Acceptance criteria

1. The deterministic ASR fake used by the backend integration tests reports Catalan (`ca`), so the import, capture and diarization paths all assert on Catalan transcripts.
2. The frontend E2E transcript fixture is Catalan, and the UI shows `Idioma: ca`.
3. The real smoke (`scripts/asr_smoke.py`) refuses to run without Catalan audio. It checks `ca` detection, required Catalan words and speaker counts for a one-voice and a two-voice Catalan file, next to the Spanish and English files.

## Implementation state

Implemented.

## Decisions

Catalan speech is synthesized with Piper voices (`ca_ES-upc_ona-medium`, `ca_ES-upc_pau-x_low`), approved by the product owner. The audio and the voices live under the git-ignored `data/smoke/` and are regenerated with `scripts/make_smoke_audio.py`.

## Files changed

- `backend/tests/fakes.py`, `backend/tests/integration/*`, `frontend/tests/e2e/import-transcript.spec.ts`
- `scripts/make_smoke_audio.py`, `scripts/asr_smoke.py`

## Validation

Real smoke on the RTX 3090 with WhisperX `large-v3`: Catalan detected as `ca`, the required words present, and one and two speakers identified correctly.

## Risks

Synthetic TTS is cleaner than real Catalan meetings. A licensed or public-corpus Catalan set is still needed for WER/CER (spec §25).

## Next action

None for this record.
