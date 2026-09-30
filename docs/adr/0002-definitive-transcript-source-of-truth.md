# ADR 0002: Definitive Transcript as the Intelligence Boundary

## Status

Accepted.

## Context

AdVera exposes provisional live transcription while a meeting is being captured, then produces a definitive transcript from the preserved original audio. Brain, Memory, embeddings, retrieval and graph projections must remain auditable and regenerable.

## Decision

The persisted definitive transcript is the only source of truth for intelligence. Provisional transcript segments and live summaries are presentation-only and must not create Brain output, concepts, relationships, chunks, embeddings or searchable answers. Derived artifacts retain the definitive transcript hash and evidence links to meeting segments and timestamps.

Concepts generated after a meeting are eligible as historical context for later meetings only. They must not be fed back into the same meeting's transcription or Brain input retroactively.

## Consequences

- ASR can be replaced and intelligence regenerated from the definitive transcript or original audio.
- Failed or partial derived jobs cannot damage the original audio or definitive transcript.
- Backfills and reprocessing must be hash-aware and invalidate stale derived results.
- The system needs explicit provisional, definitive, indexing and failed states.

## Validation and rollback

Validate with contract tests that provisional events never reach intelligence and that every derived result cites the definitive transcript hash. Rollback consists of disabling the derived consumer or rebuilding derived stores from the definitive transcript; the canonical audio and transcript remain intact.

## Related records

- `docs/meeting_manager_project_spec.md`
- `docs/features/stable-audio-transcription-pipeline.md`
- `docs/features/brain-memoria-global.md`
