# ADR 0018: faster-whisper provider with per-chunk language detection

## Status

Accepted (2026-10-01, operator review; proposed 2026-09-30). It is the default definitive provider in this rebuild.

## Context

ADR 0014 requires original-language transcription with detected languages and no translation. WhisperX detects one language per track and decodes the whole track in it. On a 120 s, six-speaker meeting in Catalan, Spanish and English it labelled every segment `ca` (13 of 26 correct), lost the English turns and translated others into Catalan. faster-whisper's `multilingual=True` did not change that.

## Decision

Add a `faster-whisper` provider behind the existing ASR provider boundary (ADR 0003). It splits a track into voice chunks with VAD, detects the language of each chunk with the same Whisper model, and decodes each chunk in its own detected language. Chunks under 1.2 s inherit the nearest reliable language.

Two rules keep detection from inventing languages without erasing real ones. A language counts for the meeting when it covers at least 5% of the detected speech. A language below that share still counts when the detector is sure about it: one chunk of at least 3 s with probability of at least 0.85, or at least 6 s in total of chunks with probability of at least 0.7. Chunks whose own language is not allowed take the most probable allowed language. The thresholds were calibrated on a real 46 min Catalan/Spanish recording (copy of the operator's own meeting; only codes, probabilities and durations were dumped): 488 voice chunks, 46 of them detected in languages nobody spoke, 8 of those with probability of at least 0.7 (Romanian 0.96 for 1.8 s, Basque 0.88 for 2.6 s, Italian 0.76), all shorter than 2.7 s. A probability threshold alone (0.7, the first version) would have kept them; a duration requirement drops them and keeps a real 3 s Catalan turn inside a Spanish meeting, which a share-only rule decoded as Spanish, the forced language ADR 0014 forbids.

`faster-whisper` becomes the default definitive provider. WhisperX stays the live provider and the explicit definitive fallback, and diarization is unchanged. Word-level alignment, which WhisperX did with wav2vec2, is not performed by the new provider: segments carry Whisper's own timestamps.

## Consequences

- Multilingual meetings keep every turn in its original language. No translation occurs.
- Segment timestamps are less tight than WhisperX-aligned ones. Word timestamps are not produced.
- A turn shorter than 1.2 s that switches language can inherit the wrong language.
- The thresholds come from one recording and there is no ground truth for it. A genuine turn shorter than 3 s in a small language, spoken once, is still decoded in a dominant language; a spurious language confidently detected across 6 s or more would still survive. Only language codes are logged per track, so the effect can be watched in production.
- A model that cannot be loaded (download, memory) raises a provider error, so the worker takes the ADR 0003 fallback instead of failing the job.
- Decoding per chunk is unbatched, so it is slower per audio second than WhisperX; the 120 s meeting took 30 s including model load.
- torch must be imported before CTranslate2 so the CUDA libraries are found.

## Validation and rollback

On the 120 s meeting: 27 of 27 segment languages correct, 6 of 6 speakers, 320 of 336 reference words (WhisperX: 13 of 26, 6 of 6, 235 of 336). Unit tests use a fake model. Rollback by setting `ASR_DEFINITIVE_PROVIDER=whisperx`; stored transcripts stay valid.

## Related records

- [ADR 0014: Preserve original-language transcription](0014-original-language-transcription.md)
- [ADR 0003: ASR provider boundary](0003-asr-provider-boundary-and-moss-role.md)
- [Rebuild per-segment language detection](../features/rebuild-per-segment-language-detection.md)
