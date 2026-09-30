# Feature: Rebuild local speaker diarization
Status: partial
Last updated: 2026-09-30

## Objective

Give definitive transcripts anonymous speaker labels with a local provider (spec §5, §8), so `attendee_count` (ADR 0011) reflects distinct speakers instead of `0`.

## Scope

In scope:
- A `DiarizationEngine` boundary and a `LocalDiarizationProvider`. Each ASR segment is cut into fixed windows, embedded with an injectable encoder, and the segments are clustered deterministically with average-linkage cosine similarity (`local-speaker-diarization.md`).
- An ECAPA-VoxCeleb encoder through SpeechBrain, loaded lazily in the transcription worker, with the model cached in the `asr-models` volume.
- Handling of short and partial audio (`speaker-diarization-quality.md`):
  - A final partial window is kept when it holds at least 0.25 s.
  - Segments shorter than 1 s do not form clusters; they join the most similar cluster.
- Degraded modes. A missing model or encoder failure (`unavailable`), or too little audio (`insufficient_audio`), publish the transcript without speakers and never fail the job.
- Provider labels (MOSS) stay authoritative (ADR 0003).
- Diarization provenance per track: provider, model, status, speaker count and parameters.
- Unique labels within a meeting across tracks (ADR 0017).

Out of scope: cross-track identity reconciliation (ADR 0005), naming speakers, live diarization, and multilingual decoding within one track.

## Acceptance criteria

1. Alternating synthetic voices produce two speakers labelled by first appearance; a single voice produces one.
2. A short segment of a known voice does not create a new speaker.
3. Encoder failure or too little audio leaves the transcript published without labels.
4. Labels are unique across tracks, and `attendee_count` counts them (ADR 0017).
5. The real smoke passes the speaker checks in Catalan, Spanish and English.

## Implementation state

Implemented. All three languages pass the real smoke. It stays `partial` pending independent QA/Security review, and because multilingual speech within one track is still lost (see Risks).

## Decisions

- Voice regions come from the definitive ASR segments, so no second VAD is added.
- The clustering threshold is 0.5 cosine similarity, configurable with `DIARIZATION_THRESHOLD`. Optional `DIARIZATION_MIN_SPEAKERS` and `DIARIZATION_MAX_SPEAKERS` bound the count. `DIARIZATION_PROVIDER=none` disables diarization.
- The worker does not use WhisperX's own pyannote diarization, which needs a gated Hugging Face token. The ECAPA path follows spec §5.
- Product owner decision (2026-09-30): every smoke set includes Catalan.
  - `scripts/make_smoke_audio.py` generates Catalan with Piper voices (`ca_ES-upc_ona-medium` and `ca_ES-upc_pau-x_low`, from huggingface.co/rhasspy/piper-voices) and Spanish/English with Windows SAPI voices.
  - The generated sets are: one voice per language, a Catalan two-voice file and a Spanish/English two-voice file.
  - `scripts/asr_smoke.py` checks languages, speaker counts and required words through the real API.
- The GPU override defaults the definitive model to WhisperX `large-v3`; the base CPU configuration keeps `small` (`separate-live-definitive-asr-models.md`).
  - Why: with `small`, the smoke showed Catalan errors ("divendres" transcribed as "d'hivèndies") and a dropped short English sentence. `large-v3` fixed both on the RTX 3090.
  - The API and the worker share the setting, because the job records the model and uses it in its idempotency key.

## Files changed

- `backend/app/diarization.py` (new), `backend/app/transcription_worker.py`, `backend/app/transcripts.py`, `backend/app/config.py`, `backend/app/job_queue.py`, `backend/pyproject.toml` (`speechbrain` in the `asr` extra)
- `backend/tests/test_diarization.py` (new), `backend/tests/fakes.py`, `backend/tests/integration/{conftest,test_import_transcription}.py`
- `docker/compose.dev.yml`, `docker/compose.nvidia.yml`, `.env.example`
- `scripts/make_smoke_audio.py`, `scripts/asr_smoke.py` (new)
- `docs/adr/0017-meeting-unique-speaker-labels.md`, `docs/meeting-processing-flow.md`

## Validation

- Unit: 11 diarization tests with a deterministic tone encoder covering alternation, single voice, partial windows, insufficient audio, encoder failure, speaker bounds, short-segment joining and determinism.
- Integration (real PostgreSQL and Redis):
  - Labels are unique across tracks and give `attendee_count == 3`.
  - Provider labels are kept.
  - Unavailable diarization still publishes the transcript.
- Real smoke on the RTX 3090 with WhisperX `large-v3` and ECAPA (`python scripts/asr_smoke.py --speakers`):
  - `ca-single` → 1 speaker, `ca-two-speakers` → 2 speakers with the correct alternation (`00 00 01 00 01`), `es-single` → 1 speaker, `en-single` → 1 speaker. All required words are present.
  - `es-en-two-speakers` is XFAIL: the English lines are lost (see Risks).

## Risks

- **Multilingual speech within one track is lost.** WhisperX detects one language per track from its first 30 s and decodes everything in that language. In the mixed Spanish/English smoke the English lines disappeared.
  - This conflicts with the spec goal of multilingual meetings with per-segment language (§2, §7) and with the ADR 0014 intent.
  - It needs a decision: either per-chunk language detection in the WhisperX provider, or the MOSS provider (ADR 0007), which is still opt-in.
- ECAPA on synthetic TTS voices separates speakers easily; real overlapping speech, noise and similar voices remain untested.
- Speaker labels are an upper bound when one person is heard on both tracks (ADR 0017).

## Next action

Decide how to handle multilingual speech within one track, then run the diarization smoke on a licensed or public multi-speaker corpus.
