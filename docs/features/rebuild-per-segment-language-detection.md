# Feature: Rebuild per-segment language detection for mixed-language tracks
Status: planned
Last updated: 2026-09-30

## Objective

Transcribe tracks where people switch languages (for example Catalan/Spanish or Spanish/English) in their original languages, with the correct language on every segment, as spec §2 and §7 and ADR 0014 require. Today the WhisperX provider decides one language per track.

## Scope

Proposed:
- Inside the WhisperX provider boundary, split each track into voice chunks with VAD.
- Detect the language of each chunk with the same Whisper model.
- Group consecutive chunks that share a language and transcribe each group in its detected language.
- Keep the segment timestamps absolute.

This is autodetection per segment, not an operator language override, so it complies with ADR 0014.

Out of scope: code-switching within a single sentence, and translation (ADR 0014).

## Acceptance criteria

1. A Spanish/English two-voice track transcribes every line in its own language, with segment languages `es` and `en`.
2. A Catalan/Spanish two-voice track produces the correct text with `ca` and `es` per segment.
3. The track and meeting `primary_language` list contains every detected language.
4. No speech is translated or dropped.
5. Single-language tracks behave as before.

## Implementation state

Not started. Evidence measured on 2026-09-30 on the RTX 3090 with Whisper `large-v3` (faster-whisper 1.2.1, which WhisperX uses internally):

| Approach | Spanish + English | Catalan + Spanish |
|---|---|---|
| Current: one language per track | English **translated into Spanish** ("The release candidate is ready…" came out as "El candidato de lanzamiento…"), labelled `es` | Correct text, but everything labelled `ca` |
| faster-whisper `multilingual=True` | Same as current | Same as current |
| Language detection per VAD chunk | Correct text, `es`/`en` per segment | Correct text, `ca`/`es` per segment |

The current behavior silently translates, which violates ADR 0014 ("never translate the definitive transcript"). In the WhisperX pipeline the smoke instead showed the English lines dropped.

## Decisions

Pending the product owner's decision. The per-chunk approach needs no new model or infrastructure. It also reuses the VAD boundaries WhisperX already computes.

## Files changed

None yet.

## Validation

Ad-hoc comparison script in the worker container on `data/smoke/es-en-two-speakers.wav` and `data/smoke/ca-es-two-speakers.wav`, both synthetic.

## Risks

- Short chunks, under about 1 s, can be misdetected. They should inherit the language of their neighbors.
- Transcribing chunk groups separately costs more than one batched pass. The unbatched experiment took 11.8 s for 19 s of audio; batching per language group should recover most of that.
- CTranslate2 finds the CUDA libraries only after `torch` has been imported (observed in the worker container). The provider must keep that import order.

## Next action

The product owner decides whether to implement it. If approved, `es-en-two-speakers` moves from XFAIL to a required pass in `scripts/asr_smoke.py`, and a `ca-es-two-speakers` case is added to the smoke.
