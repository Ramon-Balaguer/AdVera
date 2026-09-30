# MOSS Definitive Transcription Provider
Status: partial
Last updated: 2026-09-26

## Objective

Reduce speaker fragmentation in definitive meeting transcripts by using MOSS-Transcribe-Diarize 0.9B through an authenticated HTTP provider, while preserving WhisperX for live transcription and fallback.

## Product Owner Brief

### Problem

The current definitive diarization path can create excessive speaker fragmentation, making the transcript difficult to trust and review.

### Target user

AdVera users reviewing a completed meeting and relying on speaker-attributed transcript segments.

### Desired outcome

Completed meetings receive timestamped, speaker-attributed definitive segments from MOSS without changing existing transcript consumers or provisional live behavior.

### Smallest useful increment

Route microphone and system tracks independently through a configurable MOSS HTTP provider, normalize successful responses into the existing ASR contract, and fall back to WhisperX when MOSS is unavailable or returns an invalid result.

### Scope

In scope:

- MOSS for definitive transcription only.
- One HTTP request per available audio track.
- Strict response normalization and typed provider failures.
- Configuration for endpoint, model, authentication, timeouts and TLS verification.
- Existing WhisperX live path and explicit definitive fallback.
- Provider and model provenance without audio or transcript payload logging.
- Unit and integration coverage with mocked HTTP responses.

Out of scope:

- MOSS for live or provisional transcription.
- Cross-track speaker identity reconciliation.
- Removing WhisperX, Pyannote or SpeechBrain dependencies.
- Schema changes to transcript or WebSocket contracts.
- A C++ runtime or GPU service deployment in the first slice.
- Evaluation or tuning with unauthorized private audio.

### Acceptance criteria

- Live transcription continues to use its existing provider and does not call MOSS.
- Definitive microphone and system tracks are submitted independently when present.
- A valid MOSS response becomes the existing definitive transcript representation with timestamps, text, language and speaker labels when supplied.
- HTTP errors, timeouts, malformed JSON and invalid segments produce a controlled fallback to WhisperX.
- If both providers fail, the existing retryable definitive failure behavior remains intact.
- Provenance identifies the provider, model, track, input hash and fallback reason where applicable.
- Secrets, audio bytes and response payloads are absent from logs and test fixtures contain no real meeting content.

### States and failure behavior

- `processing`: a track is being submitted to MOSS.
- `complete`: all required available tracks have valid definitive output.
- `fallback`: WhisperX produced output after a MOSS failure or unavailable provider.
- `partial`: one track has output while another is empty or failed; existing track semantics are preserved.
- `failed`: neither provider can produce a definitive result; the operation remains retryable.
- Empty tracks are skipped without blocking a valid track.

### Data and provenance constraints

The definitive transcript remains the source of truth. Store provider/model identity, track identity, input hash, request timing and fallback reason through existing provenance mechanisms. Do not store chain-of-thought, raw remote payloads, audio bytes or private transcript content in logs. The remote endpoint must be explicitly configured, authenticated and protected by TLS unless a local development endpoint is being used.

### Dependencies and constraints

The selected MOSS serving backend must expose a documented response containing timestamped segments and, when available, speaker labels. The backend must support independent track requests and bounded request timeouts. WhisperX remains installed during migration to preserve rollback.

### Assumptions

- The external MOSS service can accept the PCM/WAV representation produced by AdVera or an adapter can provide the required encoding.
- MOSS labels are scoped to each track in this first slice.
- Existing transcript and WebSocket contracts can represent normalized MOSS segments.
- Runtime secrets are supplied through environment or secure settings, never committed.

### Open questions

- Which serving backend and exact `verbose_json` response schema will be used in deployment?
- Does the endpoint require WAV, PCM, multipart upload or a JSON/base64 request?
- What are the provider's retention, residency and consent guarantees?
- Should a partial track result be marked explicitly in persistence in a later slice?

## Implementation State

Implemented for the first migration slice. Deployment and canary evaluation remain follow-up work.

## ADRs

- [ADR 0003: ASR provider boundary and MOSS definitive role](../adr/0003-asr-provider-boundary-and-moss-role.md)
- [ADR 0007: MOSS vLLM development deployment](../adr/0007-moss-vllm-development-deployment.md)

## Decisions

- MOSS is authoritative for speaker labels when the MOSS provider succeeds.
- WhisperX remains the live provider and definitive fallback.
- Track speaker labels are not merged globally in the first slice.
- The remote response is treated as an external versioned contract and normalized strictly.
- vLLM 0.30 rejects `response_format=verbose_json` for this model, so the adapter requests `json` and parses the model's canonical timestamped speaker text. Structured `segments` responses remain supported for compatible runtimes.
- The configured ASR language is only a fallback for MOSS. When the canonical response has no language metadata, the adapter detects the language from the transcript text, preventing Catalan transcripts from being labeled as Spanish merely because `ASR_LANGUAGE=es` is configured.
- No private audio is used for development evaluation.

## Files Changed

- `backend/app/moss_asr.py`
- `scripts/moss_smoke.py`
- `backend/app/asr.py`
- `backend/app/audio.py`
- `backend/app/config.py`
- `backend/pyproject.toml`
- `backend/tests/test_moss_asr.py`
- `backend/tests/test_config.py`
- `.env.example`
- `docker/compose.dev.yml`
- `docker/compose.nvidia.yml`

## Validation

Validated with focused MOSS/configuration tests, `18 passed` from the MOSS adapter suite, a real synthetic smoke test against the local vLLM endpoint, Python compilation of all touched backend modules, both Compose profiles, and `git diff --check`. Ruff is clean for the new MOSS and directly related modules. The full backend suite remains the release check.

## Risks

- The exact MOSS response schema may differ between serving backends.
- Remote latency or token limits may make synchronous finalization unsuitable for long recordings.
- Speaker labels may not be comparable across independently processed tracks.
- A fallback can increase compute cost unless requests and retries are bounded.
- The selected serving backend still needs a real endpoint smoke test and a licensed/public-corpus canary before production enablement.
- Long recordings use the configurable `MOSS_MAX_NEW_TOKENS` request limit, defaulting to `65536`.

## Next Action

The Compose server is started with `docker compose --profile moss -f docker/compose.dev.yml -f docker/compose.nvidia.yml up moss-server`. MOSS is now the default definitive provider, while live transcription remains on WhisperX and WhisperX remains the fallback. Run `python scripts/moss_smoke.py` from the repository root and perform a licensed/public-corpus canary evaluation before production rollout. The server image remains configurable because vLLM model support may require a pinned nightly build.