# ADR 0009: Summary output language provenance

## Status

Accepted (2026-09-25)

## Context

AdVera has one persisted runtime configuration, while Summary jobs are asynchronous and may run after the operator changes Settings. The definitive transcript remains language-neutral source data, but the requested language changes generated textual output and must be reproducible.

## Decision

Persist a validated `es` or `en` preference in the existing runtime settings file (extended on 2026-10-02 to `en`, `es` or `ca`, with English as the default for new installations and as the interface language, see `rebuild-interface-localization.md`). Copy the preference onto each `SummaryJob` at creation time and instruct the Summary provider to use it for textual fields. Existing jobs receive `es` through the schema migration default.

The preference does not change the definitive transcript hash, evidence IDs, structured keys, statuses or source-of-truth boundary.

## Consequences

- Jobs created under different language preferences are distinct and do not silently reuse an extraction in another language.
- The output language is available as job provenance without storing prompts or chain-of-thought.
- A future output compliance detector may be added without changing the transcript contract.
- Existing UI screens beyond Settings are not translated by this decision.

## Validation

The Settings API, Summary prompt and worker tests cover persistence, validation and propagation. Migration `0012_summary_output_language` adds the durable job column with a Spanish default.

## Rollback

Deploy the downgrade for migration `0012_summary_output_language`, remove the preference from the Settings payload, and revert the prompt parameter. Existing transcript hashes remain valid.

## Related records

- [Interface language and LLM response language](../features/interface-language-and-llm-response-language.md)
- [Definitive transcript as intelligence source of truth](0002-definitive-transcript-source-of-truth.md)
