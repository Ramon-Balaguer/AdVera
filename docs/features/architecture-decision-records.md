# Architecture Decision Records
Status: complete
Last updated: 2026-09-25

## Objective

Make AdVera's durable architecture decisions discoverable, reviewable and connected to implementation records.

## Scope

Inventory and formalize existing decisions affecting transcript authority, intelligence provenance, ASR provider boundaries, WebSocket/audio contracts, dual-track persistence, meeting reprocessing and MOSS deployment. Implementation details remain in feature records.

## Acceptance criteria

- The ADR directory has an index and one record for each durable decision family identified in the current codebase.
- Each record states context, decision, consequences, validation and rollback.
- Architecture/Data responsibilities require ADR review for ownership, contract, provider, persistence and deployment-boundary changes.
- Feature handoffs link affected ADRs.

## Implementation state

Implemented for the current architecture baseline.

## Decisions

- Use one ADR per durable decision family rather than one ADR per bug or feature detail.
- Keep feature records as the execution history and ADRs as the durable decision log.
- Treat the definitive transcript hash and evidence chain as the boundary for derived knowledge.

## Files changed

- `docs/adr/README.md`
- `docs/adr/0002-definitive-transcript-source-of-truth.md`
- `docs/adr/0003-asr-provider-boundary-and-moss-role.md`
- `docs/adr/0004-audio-capture-and-live-delivery.md`
- `docs/adr/0005-dual-track-audio-processing.md`
- `docs/adr/0006-reprocess-transcript-before-brain.md`
- `docs/adr/0007-moss-vllm-development-deployment.md`
- `.github/copilot-instructions.md`
- `.github/agents/advera-architecture-data.agent.md`
- `.github/agents/advera-operations.agent.md`
- `docs/agent-workflow.md`

## Validation

Review the ADR index, verify relative links and run repository documentation/link checks when available.

## Risks

The records describe the current local MVP and may need superseding ADRs when multi-user deployment, transcript version history or cross-track speaker identity are introduced.

## Next action

Link future feature records to the relevant ADRs and create a superseding ADR when a durable decision changes.
