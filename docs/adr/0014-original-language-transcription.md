# ADR 0014: Preserve original-language transcription

## Status

Accepted

## Context

The ASR runtime previously received `ASR_LANGUAGE=es` by default. That can make Catalan and other non-Spanish recordings be recognized as Spanish. `Meeting.primary_language` was also modeled as one configured language, which cannot represent multilingual meetings.

## Decision

ASR receives no language override in any flow. Providers autodetect the original language and return language metadata on segments. `Meeting.primary_language` is a JSON array populated after definitive transcription with the distinct detected segment languages; a new meeting starts with `[]`.

The definitive transcript remains the source of truth. Future translations and multilingual language-list requests must be implemented as separate derived artifacts/contracts, preserving the original transcript, source hash, source language, target language and translation provider metadata.

## Consequences

- Catalan, English and other original-language recordings are no longer globally forced to Spanish.
- Multilingual meetings can retain multiple detected languages.
- WhisperX and MOSS receive no language code; ordered language lists and translation are deferred.
- Existing transcripts generated under the old configuration need explicit reprocessing.

## Validation and rollback

Validate focused ASR/reprocessing tests and resolved Compose/script configuration. Rollback by restoring the previous defaults, understanding that doing so reintroduces forced-language behavior.

## Related records

- `docs/features/original-language-transcription.md`
- `docs/features/definitive-transcription-language.md`
- `docs/adr/0002-definitive-transcript-source-of-truth.md`
- `docs/adr/0003-asr-provider-boundary-and-moss-role.md`
