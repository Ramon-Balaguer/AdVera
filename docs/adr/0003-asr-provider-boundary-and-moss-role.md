# ADR 0003: ASR Provider Boundary and MOSS Definitive Role

## Status

Accepted.

## Context

AdVera needs low-latency live feedback and a higher-quality definitive transcript. MOSS and WhisperX have different runtime and output characteristics, while downstream consumers require one normalized ASR contract.

## Decision

Expose ASR through the existing provider contract. WhisperX remains the live provider and the explicit definitive fallback. MOSS is used only for definitive transcription when configured. MOSS processes available tracks independently and is authoritative for speaker labels when it succeeds; speaker labels from separate tracks are not globally reconciled in this slice.

The adapter accepts structured segments and the vLLM-compatible JSON response containing canonical timestamped speaker text. Provider/model, track, input hash and fallback metadata remain part of transcript provenance. The configured language is a fallback only; provider metadata or text detection takes precedence.

## Consequences

- Live behavior remains independent from MOSS availability.
- A provider failure can fall back without changing transcript consumers.
- The remote response is a versioned boundary that requires strict normalization and focused contract tests.
- Cross-track speaker identity and multilingual global language require a later decision.

## Validation and rollback

Validate provider, fallback, malformed-response, language and provenance tests plus a synthetic endpoint smoke test. Rollback by setting the definitive provider to WhisperX; the provider contract and transcript format remain stable.

## Related records

- `docs/features/moss-definitive-provider.md`
- `docs/features/definitive-transcription-language.md`
- `docs/features/speaker-diarization-quality.md`
