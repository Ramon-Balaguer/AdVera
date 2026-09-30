# Feature: Speaker diarization quality
Status: complete
Last updated: 2026-09-22

## Objective

Improve definitive speaker diarization quality for short recordings and partially filled windows while preserving the current local provider and pipeline boundaries.

## Problem

Partial audio windows may be discarded, and overly aggressive clustering can merge distinct speakers. These issues reduce speaker-label accuracy, especially for short recordings, partial windows and temporally overlapping speech.

## Target user

Self-hosted AdVera operators reviewing definitive meeting transcripts with anonymous speaker labels.

## Desired outcome

Short and partial recordings retain usable diarization evidence, speaker clusters are less likely to merge incorrectly, and temporal overlap is handled consistently without changing the current provider or introducing a new VAD/model.

## Smallest useful increment

Fix partial-window discard behavior, reduce overly aggressive clustering errors, and add regression coverage for short audio, partial windows and temporal overlap.

## Scope

- Preserve usable partial audio windows during diarization.
- Adjust clustering behavior to reduce incorrect speaker merges.
- Add regressions for short audio.
- Add regressions for partially filled windows.
- Add regressions for temporal overlap.
- Preserve anonymous, meeting-scoped speaker labels.
- Keep the current diarization provider and model boundary.

Out of scope:

- Changing diarization providers.
- Introducing a new VAD implementation.
- Introducing a new embedding or diarization model.
- Real-person speaker identification.
- Live diarization changes.
- Broader transcript or intelligence changes.

## Acceptance criteria

- Short audio containing valid speech is not discarded solely because it does not fill a complete window.
- Partial final windows are processed when they contain sufficient usable audio.
- Clustering does not merge distinct synthetic speakers under the previously failing aggressive-threshold conditions.
- Temporal overlap assigns speaker labels deterministically according to the existing overlap contract.
- Regression tests cover short audio, partial windows and temporal overlap.
- Existing fallback behavior remains intact when audio is insufficient or diarization cannot run.
- No provider, VAD or model change is introduced.

## States and failures

- `available`: sufficient usable audio produces deterministic speaker labels.
- `partial_input`: a shortened or final partial window is retained and processed when valid.
- `insufficient_audio`: too little usable speech returns no speaker labels without failing transcription.
- `completed`: labels are assigned and existing provenance is preserved.
- `unavailable`: diarization failure leaves the definitive transcript available without speaker labels.
- Clustering ambiguity must not cause transcription failure.

## Data and provenance constraints

- The definitive transcript remains the source of truth.
- Speaker IDs remain anonymous and scoped to one definitive meeting.
- Existing audio timestamps and temporal overlap semantics must be preserved.
- Tests and logs must not contain real meeting content, secrets or chain-of-thought.
- Existing diarization provider, model metadata, parameters and fallback reasons remain traceable.

## Assumptions

- The current diarization provider and embedding model remain suitable for this increment.
- The existing windowing and temporal assignment contracts should be refined rather than replaced.
- Synthetic fixtures are sufficient to reproduce the reported clustering and overlap failures.
- No schema or API contract change is required.

## Open questions

- What clustering threshold or guard should be used after regression evidence is added?
- What minimum speech duration makes a partial window valid?
- Should partial-window handling use padding, direct processing, or another existing normalization path?
- Are overlapping segments expected to receive one label or preserve multiple-speaker evidence?

## Recommended next agent

Orchestrator, followed by the Audio Live or Intelligence specialist as appropriate, with QA and Security review after implementation.

## Implementation state

Implemented. The focused increment is complete; broader audio-quality evaluation with annotated real audio remains a follow-up.

## Decisions

- Keep the current diarization provider.
- Do not introduce a new VAD or model in this increment.
- Address partial-window retention and clustering aggressiveness through focused implementation changes and regression tests.
- Preserve the existing definitive-transcript and fallback contracts.
- Retain partial windows only when they meet the configurable 0.5 second minimum by default.
- Keep strict initial clustering at `0.78` and use an independent tolerant merge threshold of `0.62` for intra-speaker drift.
- Treat an uninitialized local diarizer as unavailable so the existing ASR fallback remains reachable.
- Skip isolated windows without embeddings instead of discarding all valid diarization windows.
- Provide deterministic DER/JER evaluation for authorized, non-overlapping reference annotations.

## Files changed

- `docs/features/speaker-diarization-quality.md`
- `backend/app/diarization.py`
- `backend/app/asr.py`
- `backend/app/audio.py`
- `backend/app/config.py`
- `backend/tests/test_diarization.py`
- `backend/pyproject.toml`

No provider, VAD, model, schema or API contract was changed.

## Validation

Passed:

- `python -m pytest backend/tests/test_diarization.py backend/tests/test_asr.py backend/tests/test_config.py -q` -> 19 passed
- `python -m pytest backend/tests/test_diarization.py -q` -> 11 passed after isolated-embedding recovery change
- `python -m pytest backend/tests/test_diarization.py -q` -> 15 passed with DER/JER evaluation coverage
- `python -m pytest backend/tests/test_diarization.py -q` -> 16 passed with drift-merge coverage
- `python -m ruff check backend/app/asr.py backend/app/config.py backend/app/diarization.py backend/tests/test_diarization.py` -> passed
- `git diff --check` -> passed

The backend now declares `numpy` explicitly because the ASR and diarization paths import it directly.
The minimum usable diarization window is configurable through backend Settings and defaults to `0.5` seconds.
The cluster merge threshold is configurable through backend Settings and defaults to `0.62`.
Full lint of `backend/app/audio.py` remains blocked by four pre-existing findings unrelated to this feature.

`evaluate_diarization` currently requires non-overlapping single-speaker annotations. Overlapping speech needs an explicit product policy before it is included in DER/JER scoring.

## Risks

- Relaxing partial-window handling may admit low-quality audio into clustering.
- Reducing clustering aggressiveness may fragment a single speaker into multiple labels.
- Temporal overlap behavior may expose ambiguity in single-label assignment.
- Threshold changes may affect existing recordings and require anonymized integration validation.
- The current test suite still lacks DER/JER evaluation against annotated real audio.

## Next action

Keep regression coverage synthetic until an authorized or license-compatible public corpus is available. Do not tune diarization thresholds against private meeting audio without consent.