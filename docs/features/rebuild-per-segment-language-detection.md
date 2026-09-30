# Feature: Rebuild per-segment language detection for mixed-language tracks
Status: partial
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

Implemented as the `faster-whisper` provider ([ADR 0018](../adr/0018-per-chunk-language-detection-provider.md)). Result on the 120 s meeting: segment language 27 of 27, 6 of 6 speakers, 320 of 336 words (95%); all English turns recovered. It stays partial pending human review of the provider change and a real-speech corpus. Evidence measured on 2026-09-30 on the RTX 3090 with Whisper `large-v3` (faster-whisper 1.2.1, which WhisperX uses internally):

| Approach | Spanish + English | Catalan + Spanish |
|---|---|---|
| Current: one language per track | English **translated into Spanish** ("The release candidate is ready…" came out as "El candidato de lanzamiento…"), labelled `es` | Correct text, but everything labelled `ca` |
| faster-whisper `multilingual=True` | Same as current | Same as current |
| Language detection per VAD chunk | Correct text, `es`/`en` per segment | Correct text, `ca`/`es` per segment |

The current behavior silently translates, which violates ADR 0014 ("never translate the definitive transcript"). In the WhisperX pipeline the smoke instead showed the English lines dropped.

### Measured on a 120 s, six-speaker, three-language meeting (2026-09-30)

`scripts/make_meeting_audio.py` builds `data/smoke/meeting-120s.wav`: 25 turns, six distinct Piper voices (two Catalan, two Spanish, two English), with the ground truth in `meeting-120s.json`. Through the real stack (WhisperX `large-v3` on the RTX 3090, ECAPA diarization, 29 s):

| Metric | Result |
|---|---|
| Distinct speakers | **6 of 6** |
| Segments labelled with the right language | **13 of 26**: every segment is labelled `ca` and `primary_language` is `["ca"]` |
| Reference words present in the transcript | 235 of 336 (70%) |
| English turns | Lost or translated: all 3 of Jack's turns are missing, and one merged English+Spanish segment came out as Catalan |
| Spanish turns | Some kept as Spanish, some translated to Catalan ("Jo també puc ajudar amb les proves finals…") |

Diarization itself held up. Errors happen where the ASR merges two turns into one segment (for example Jordi and Jack in one 10 s segment), because labels are assigned per ASR segment.

## Decisions

Pending the product owner's decision. The per-chunk approach needs no new model or infrastructure. It also reuses the VAD boundaries WhisperX already computes.

## Files changed

None yet.

## Validation

Ad-hoc comparison script in the worker container on `data/smoke/es-en-two-speakers.wav` and `data/smoke/ca-es-two-speakers.wav`, both synthetic.

## Risks

- After the switch, `ca-single` mishears one word ("divendres" as "d'hivernes"). It is a recognition error on synthetic Catalan and it is tracked as a known issue in the smoke. The 120 s meeting scores 95% of reference words.
- Segment bounds come from Whisper's word timestamps. The first version used padded segment times and produced a spurious third speaker in `es-en-two-speakers`; word times fixed it.

- Short chunks, under about 1 s, can be misdetected. They should inherit the language of their neighbors.
- Transcribing chunk groups separately costs more than one batched pass. The unbatched experiment took 11.8 s for 19 s of audio; batching per language group should recover most of that.
- CTranslate2 finds the CUDA libraries only after `torch` has been imported (observed in the worker container). The provider must keep that import order.

## Next action

Human review of ADR 0018, then a real multilingual speech corpus. `es-en-two-speakers` is now a required pass in `scripts/asr_smoke.py`.
