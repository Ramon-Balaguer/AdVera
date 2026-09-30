# Feature: Local speaker diarization without Hugging Face
Status: in progress
Last updated: 2026-09-22

## Problem and target user

AdVera currently relies on a gated Hugging Face Pyannote pipeline for speaker diarization. This makes speaker labels depend on an external token and model access, even when the application is intended to run locally.

The target user is a self-hosted AdVera operator who needs definitive transcripts with anonymous speaker labels and wants the inference path to work offline after an explicit local model installation.

## Desired outcome

Definitive transcripts can receive stable anonymous labels such as `SPEAKER_00` and `SPEAKER_01` from a local diarization provider. Missing local models or low-confidence audio must degrade to a transcript without speakers and must not fail the meeting.

## Smallest useful increment

Implement a testable local diarization core with voice-region windows, injected voice embeddings, deterministic clustering and temporal assignment to ASR segments. Keep the live transcript unchanged and preserve the existing non-blocking fallback contract.

## Scope

- Add a dedicated local diarization abstraction and core algorithm.
- Keep model loading behind an injectable encoder boundary.
- Support optional speaker-count bounds and deterministic anonymous labels.
- Assign labels to definitive ASR segments by temporal overlap.
- Add provenance fields for local diarization when integrated.
- Document local model preparation and offline execution.

Out of scope for the first increment: real-person identification, live diarization, speaker naming, perfect overlapping-speech separation, training an acoustic model, and removing WhisperX transcription.

## Acceptance criteria

- The core produces deterministic speaker labels for synthetic alternating voices.
- ASR segments receive the speaker with the greatest temporal overlap.
- The same speaker is not renamed because audio came from another track when tracks are clustered together.
- Live ASR continues with `speaker=None`.
- Missing encoder/model, silence or insufficient speech returns no speaker labels without failing definitive transcription.
- No Hugging Face token is required by the local core or its tests.

## States and failure behavior

- `available`: local encoder and enough speech windows are available.
- `unavailable`: local model is missing or cannot load; transcript continues without speakers.
- `insufficient_audio`: no usable voiced windows or too few embeddings; transcript continues without speakers.
- `completed`: labels were assigned and provenance records the local provider and parameters.

## Data and provenance constraints

- Speaker IDs are anonymous and scoped to one definitive meeting.
- Audio and transcript data remain local.
- No token, secret or real meeting content is written to logs or fixtures.
- Provenance must identify the diarization provider, embedding model/version, clustering parameters and fallback reason.

## Dependencies and assumptions

- WhisperX remains responsible for transcription and alignment.
- The first algorithm is independent of a concrete ML framework and accepts an embedding encoder protocol.
- A later adapter may use a locally cached ECAPA-TDNN checkpoint, such as SpeechBrain, under `data/models/`.
- Clustering and model-loading dependencies must remain optional until the local runtime adapter is introduced.

## Implementation state

- Product brief recorded.
- Core implementation and focused tests: completed.
- Local encoder adapter and definitive WhisperX integration: completed.
- Local model preparation command and checkpoint smoke test: completed.

The first slice adds `backend/app/diarization.py` with injected voice embeddings,
deterministic cosine-similarity clustering, turn merging and temporal ASR assignment.
It does not download a model and does not require a Hugging Face token. Synthetic tests
cover alternating speakers, cross-track labels, overlap assignment and missing embeddings.
The second slice adds a lazy SpeechBrain ECAPA adapter, local diarization settings and
definitive WhisperX integration. Missing local checkpoints keep the transcript available
without speakers.
The local ECAPA checkpoint is prepared under `data/models/ecapa-voxceleb`; a synthetic
offline smoke test produced two anonymous speaker turns without `HF_TOKEN`.

## Risks

- Embedding quality determines diarization quality and may be lower than Pyannote in overlap and noise.
- SpeechBrain emits a non-blocking Windows symlink warning while loading the local checkpoint.
- Unknown speaker counts require a threshold that may merge or fragment voices.
- Cross-track clustering needs careful normalization and deterministic ordering.

## Validation

Focused unit tests, ASR/audio regression tests and an offline smoke test without `HF_TOKEN` pass.

## Next action

Use the prepared checkpoint with `scripts/dev.ps1 api` (or `scripts/dev.sh api`).
The next improvement is to remove the remaining SpeechBrain Windows symlink warning
and add a real anonymized recording smoke test.
