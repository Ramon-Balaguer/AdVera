# Feature: Summary Concept Relationship Alias Resolution
Status: complete
Last updated: 2026-09-26

## Problem

Summary projection can fail with `Summary projection validation failed: Concept relationship references an unknown concept` when a relationship references a valid `SummaryConcept.mention` whose value differs from its `canonical_name`.

## Target user

AdVera users relying on Summary concept graphs and brain projections from definitive meeting transcripts.

## Desired outcome

Valid concept relationships resolve correctly whether they reference a concept's canonical name or an allowed mention/alias, without weakening validation for genuinely unknown concepts.

## Smallest useful increment

Make concept relationship resolution recognize both canonical concept names and valid concept mentions, with regression coverage for an alias that differs from the canonical name.

## In scope / Out of scope

In scope: canonical and mention-based relationship endpoint resolution, canonical node identity, regression coverage, and preservation of provenance validation.

Out of scope: changes to the Summary extraction contract, user-facing alias editing, semantic similarity, provisional transcript processing, and historical reprocessing operations.

## User acceptance criteria

- Canonical relationship endpoints continue to project successfully.
- A valid mention that differs from the canonical name projects to the canonical concept node.
- Unknown relationship endpoints still fail with a clear validation error.
- Existing evidence and provenance metadata remain unchanged.

## States and failure behavior

Valid canonical references and valid mentions project normally. Unknown references fail with the existing projection error. The projection remains restricted to definitive transcripts.

## Data and provenance constraints

Definitive transcripts remain the source of truth. Existing normalization rules are reused. Canonical node identity, evidence IDs, transcript hashes, input hashes, provider/model metadata, and prompt version are preserved. No chain-of-thought or unsupported aliases are stored.

## Dependencies and constraints

The existing Summary concept and relationship contracts remain authoritative. No schema migration or API contract change is expected. The affected implementation is `backend/app/brain_graph.py`.

## Assumptions

`SummaryConcept.mention` is an allowed reference for a relationship endpoint because the extraction contract exposes both mention and canonical name.

## Open questions

- Should ambiguous normalized mentions be rejected explicitly in a later contract hardening change?
- Should aliases be persisted as graph metadata independently of this projection fix?

## Implementation state

The projection resolves relationship endpoints by normalized canonical name or normalized mention. When the extractor returns an explicit relationship endpoint that is absent from `concepts`, the endpoint is materialized as a generic concept node using the relationship evidence. The worker persists these nodes before their relationships.

## Validation

Focused projection and persistence tests pass: 27 passed. Ruff passes for all changed Python files. Static diagnostics report no errors for `brain_graph.py` and the intelligence tests. The broader selected backend run previously reported one unrelated local backfill failure in `test_backfill_reconciles_queued_completed_and_failed_jobs`.

## Decisions, risks and next action

Reuse existing label normalization, resolve mentions to the canonical node, and materialize only relationship endpoints explicitly supported by relationship evidence. The main residual risk is ambiguity if multiple concepts share the same normalized mention. Next action is QA review and, separately, investigation of the unrelated backfill test failure.
