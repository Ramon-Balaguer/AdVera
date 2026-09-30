# Feature: Spike on a local typed-decision model (Laya)
Status: complete
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

## Decision

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

- `scripts/laya_benchmark.py` (new, spike script; requires `laya`, which is not a backend dependency)

## Validation

- The benchmark ran on CPU with `laya` 0.3.22, `torch` 2.14.0 and `transformers` 5.17.0 in a scratch virtualenv outside the repository (`C:\Users\scrambler\laya-venv`, kept for a possible follow-up). The package was read before running: its only network access is downloading weights from Hugging Face, and it uses no `trust_remote_code`, `pickle` or `torch.load`. About 1 GB of weights went to the Hugging Face cache.
- No transcript, audio or real meeting was involved.

## Risks

The set is small (23 turns, 24 claims) and synthetic, so the numbers are indicative. They are far enough from the criteria (recall 0.33 against 0.95) that more data is unlikely to reverse the conclusion for the zero-shot model.

## Next action

None for this spike. Revisit only if labelled meeting segments exist to fine-tune on.

## Sources

- https://laya-ai.com/
- https://pypi.org/project/laya/
- https://huggingface.co/Contrastive-LM/CLM-v0.1-8B
