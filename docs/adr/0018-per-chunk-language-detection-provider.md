# ADR 0018: faster-whisper provider with per-chunk language detection

## Status

Accepted (2026-09-30); changes the default definitive provider (human review requested).

## Context

ADR 0014 requires original-language transcription with detected languages and no translation. WhisperX detects one language per track and decodes the whole track in it. On a 120 s, six-speaker meeting in Catalan, Spanish and English it labelled every segment `ca` (13 of 26 correct), lost the English turns and translated others into Catalan. faster-whisper's `multilingual=True` did not change that.

## Decision

Add a `faster-whisper` provider behind the existing ASR provider boundary (ADR 0003). It splits a track into voice chunks with VAD, detects the language of each chunk with the same Whisper model, and decodes each chunk in its own detected language. Chunks under 1.2 s inherit the nearest reliable language. Segment languages are the per-chunk languages and `primary_language` is their distinct set. No language is ever supplied from outside, so ADR 0014 still holds.

`faster-whisper` becomes the default definitive provider. WhisperX stays the live provider and the explicit definitive fallback, and diarization is unchanged. Word-level alignment, which WhisperX did with wav2vec2, is not performed by the new provider: segments carry Whisper's own timestamps.

## Consequences

- Multilingual meetings keep every turn in its original language. No translation occurs.
- Segment timestamps are less tight than WhisperX-aligned ones. Word timestamps are not produced.
- A turn shorter than 1.2 s that switches language can inherit the wrong language.
- Decoding per chunk is unbatched, so it is slower per audio second than WhisperX; the 120 s meeting took 30 s including model load.
- torch must be imported before CTranslate2 so the CUDA libraries are found.

## Validation and rollback

On the 120 s meeting: 27 of 27 segment languages correct, 6 of 6 speakers, 320 of 336 reference words (WhisperX: 13 of 26, 6 of 6, 235 of 336). Unit tests use a fake model. Rollback by setting `ASR_DEFINITIVE_PROVIDER=whisperx`; stored transcripts stay valid.

## Related records

- [ADR 0014: Preserve original-language transcription](0014-original-language-transcription.md)
- [ADR 0003: ASR provider boundary](0003-asr-provider-boundary-and-moss-role.md)
- [Rebuild per-segment language detection](../features/rebuild-per-segment-language-detection.md)
