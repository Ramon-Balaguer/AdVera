# Feature: Spike on local typed-decision models (Laya, tev1)
Status: in progress
Last updated: 2026-09-30

## Objective

Find out whether a local "System 1" decision model (small, one forward pass, no text generation) could take work away from the LLM in Brain and Memory, and where it would help most. Candidates proposed by the operator: Laya and CLM-v0.1-8B. This is a measurement, not a product change: nothing in the backend, Docker or settings was touched.

## Candidates

| | Laya (`convaiinnovations/laya`, package `laya` 0.3.22) | CLM-v0.1-8B |
|---|---|---|
| Size | about 421M parameters | frozen Qwen3-8B plus two heads |
| Serving | in-process, CPU or GPU | needs vLLM serving Qwen3-8B (about 16 GB of VRAM) plus `clm-serve` |
| Languages | English checkpoint and a multilingual one (routed by language detection); Catalan and Spanish not listed | English only |
| License | Apache 2.0 | Apache 2.0 |

CLM-8B was discarded without running: English only, and its encoder would compete with Whisper `large-v3` and BGE-M3 for the 24 GB of the RTX 3090. Both models read text, not audio, so neither can replace spoken-language detection.

## What was measured

`scripts/laya_benchmark.py` on the synthetic 120 s meeting (Catalan, Spanish, English; no real data), CPU, zero-shot with the multilingual checkpoint, which the package selected automatically:

1. **Classifying turns** as decision, action, question, risk or other (23 labelled turns; two ambiguous turns excluded). This is the basis of a pre-filter that would let the LLM read only candidate segments.
2. **Verifying a claim against the segment it cites** (24 claims: 12 supported, 12 altered in who, what or when). This would go beyond today's check, which only confirms that the cited id exists.

| | Result | Adoption criterion | Met |
|---|---|---|---|
| Turn classification accuracy | 13 of 23 (ca 5/8, en 5/8, es 3/7) | not set | no |
| Decision and action kept as candidates | 4 of 12 (recall 0.33) | at least 0.95 | **no** |
| False claims caught | 12 of 12 | F1 at least 0.9 | yes |
| Correct claims kept | 5 of 12 at threshold 0.5 (mean p 0.38 for true claims, 0.02 for false) | rejects at most 5% | **no** |
| Latency per question | about 95 ms on CPU | under 50 ms | not on CPU; GPU not measured |

A second wording of the questions (richer instructions, one round only, to avoid fitting 23 turns) was worse: 10 of 23 in classification and 4 to 5 of 12 correct claims kept.

## Second model: `tev1:0.8b` through Ollama (`/v1/systemone`)

The operator put a 0.8B decision model in their Ollama server (Ollama's typed-decision endpoint). The same test runs through `scripts/decision_model_benchmark.py`, which replaced the Laya-specific script; the server address comes from `$OLLAMA_URL` and is not stored in the repository. Laya's environment and weights were deleted from the machine. Same synthetic meeting, zero-shot, latency measured client side against the remote server (network included).

| | tev1:0.8b | Laya (for reference) | Criterion |
|---|---|---|---|
| Turn classification accuracy | 11 of 23 (ca 4/8, en 5/8, es 2/7) | 13 of 23 | none |
| Decision and action kept as candidates | 11 of 12 (recall 0.92) | 4 of 12 (0.33) | at least 0.95 |
| Share of turns it would pass to the LLM | about 20 of 23 (87%) | not measured | a real saving |
| Mean p(supported), true / false claims | 0.67 / 0.41 | 0.38 / 0.02 | wide gap |
| Threshold 0.5: false claims caught / true kept | 7 of 12 / 12 of 12 | 12 of 12 / 5 of 12 | F1 0.9, at most 5% wrongly rejected |
| Threshold 0.6: false caught / true kept | 12 of 12 / 8 of 12 | not measured | |
| Real Brain items accepted at 0.5 | 15 of 15 (lowest p 0.58) | 10 of 15 | all |
| Latency per question | about 210 to 220 ms (remote) | about 95 ms (local CPU) | under 50 ms |

Reading:
- As a pre-filter it keeps almost every decision and action, but only because it labels most turns as decisions (decision precision 0.33, "other" recall 0.25): it would hand about 87% of the transcript to the LLM, so the saving is small.
- As a verifier it is the opposite of Laya: it does not delete real Brain items (15 of 15 pass, and 12 of 12 true claims at 0.5), but it separates true from false poorly (7 of 12 false claims caught at 0.5). At 0.6 it catches all false claims and rejects a third of the true ones. It could flag items for a second look but not filter them on its own.
- Catalan is not worse than the other languages.

## Third model: `tev1:latest` (4B, 4.5 GB on the server)

The same script against the larger model, same data, zero-shot, latency remote.

| | tev1:latest | tev1:0.8b | Laya | Criterion |
|---|---|---|---|---|
| Turn classification accuracy | 18 of 23 (ca 7/8, en 7/8, es 4/7) | 11 of 23 | 13 of 23 | none |
| Same, on the Whisper text | 16 of 23 | 11 of 23 | not measured | none |
| Decision and action kept (argmax class) | 12 of 12 | 11 of 12 | 4 of 12 | at least 0.95 |
| Same, on the Whisper text | 10 of 12 (0.83) | 11 of 12 | not measured | at least 0.95 |
| Mean p(supported), true / false claims | 0.74 / 0.14 | 0.67 / 0.41 | 0.38 / 0.02 | wide gap |
| Threshold 0.5: false caught / true kept | 11 of 12 / 9 of 12 (F1 0.85) | 7 of 12 / 12 of 12 | 12 of 12 / 5 of 12 | F1 0.9, at most 5% wrongly rejected |
| Real Brain items accepted at 0.5 | 14 of 15 (one action at 0.36) | 15 of 15 | 10 of 15 | all |
| Latency per question | about 530 ms (remote) | about 210 ms (remote) | about 95 ms (local CPU) | under 50 ms |

A pre-filter by probability instead of by predicted class works better: keep a turn unless p(other) is at least T.

| Text | Decisions and actions kept | Turns kept (saving) |
|---|---|---|
| Reference text, T from 0.5 to 0.8 | 12 of 12 | 16 of 23 (30% fewer) |
| Whisper text, T from 0.5 to 0.8 | 12 of 12 | 17 of 23 (26% fewer) |
| Whisper text, T 0.95 | 12 of 12 | 20 of 23 (13% fewer) |

Reading:
- It is the first model that meets the recall criterion for a pre-filter (all 12 decisions and actions, on clean and on transcribed text) when the probabilities are used. The saving is modest: about a quarter to a third of the turns, and the turns kept include questions, risks and other context. Brain also extracts topics, open questions and risks, so a filter built only on "decision or action" would drop material Brain uses today; the filter would need its own rule for those.
- As a verifier it is clearly better than the 0.8B (11 of 12 false claims caught) but still short of the criterion: it would wrongly reject one correct item in four at 0.5 (9 of 12 true claims kept, and one of the 15 real Brain items). It fits "flag for review", not "delete".
- Latency is 2.5 times the 0.8B and far from 50 ms, mostly because it is called over the network for a 4.5 GB model; a local run was not measured.


## Decision (Laya)

Do not adopt Laya zero-shot for either use. As a pre-filter it would lose 8 of 12 decisions and actions, and losing a decision is worse than being slow. As a claim verifier it is a good detector of wrong claims but rejects most correct ones, which would delete real Brain items. The Catalan and Spanish results are not better than English, so the gap is not a language artifact of the synthetic set.

What could change this, none of it started:
- fine-tuning Laya's heads (the project documents it) on labelled meeting segments. There is no labelled real data, and training on this synthetic meeting would only measure memorization;
- using its confidence to abstain and pass only uncertain cases to the LLM, which needs a larger labelled set to calibrate;
- measuring the LLM (ornith) on the same 47 questions as a baseline. It was not run here because the zero-shot result already fails the criteria.

## Where it would help most, for when it is revisited

1. Verifying Brain items against their cited segments (quality).
2. Pre-filtering segments for Brain (speed, and meetings longer than the context).
3. Decision state (proposed, decided, rejected, superseded).
4. Memory question intent.
5. Suggesting existing tags for a meeting (with the concept graph, ADR 0013).

## Files changed

- `scripts/decision_model_benchmark.py` (spike script; first written for Laya as `laya_benchmark.py`, now for Ollama decision models, with no dependency beyond the standard library)

## Validation

- The Laya benchmark ran on CPU with `laya` 0.3.22, `torch` 2.14.0 and `transformers` 5.17.0 in a scratch virtualenv outside the repository, deleted afterwards with its weights. The package was read before running: its only network access is downloading weights from Hugging Face, and it uses no `trust_remote_code`, `pickle` or `torch.load`. The Laya weights (1.5 GB) were removed from the Hugging Face cache.
- No transcript, audio or real meeting was involved.

## Risks

The set is small (23 turns, 24 claims) and synthetic, so the numbers are indicative. They are far enough from the criteria (recall 0.33 against 0.95) that more data is unlikely to reverse the conclusion for the zero-shot model.

## Next action

Decide with the operator whether the modest saving of the probability pre-filter and a flagging verifier are worth a product change; `nimble` (9B) is not on the server yet and could be measured with the same script. Nothing in the product changes until then, and any adoption would need labelled real meetings to confirm these numbers.

## Sources

- https://laya-ai.com/
- https://pypi.org/project/laya/
- https://huggingface.co/Contrastive-LM/CLM-v0.1-8B
