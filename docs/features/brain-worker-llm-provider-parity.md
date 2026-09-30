# Feature: Brain worker LLM provider parity
Status: complete
Last updated: 2026-09-26

## Objective

Ensure Brain jobs created automatically after definitive transcription carry the same configured LLM provider and model used by the API and Brain worker.

## Product brief

Problem: The transcription worker created Brain jobs with `provider=none` because its Compose environment omitted the LLM settings. The Brain worker then failed with `Brain LLM provider is not configured`.

Target user: AdVera operators and meeting reviewers who expect Brain extraction to start after definitive transcription.

Desired outcome: Newly scheduled Brain jobs resolve consistently to the configured Ollama provider and model.

Smallest useful increment: Propagate the shared LLM environment to `transcription-worker` and protect the behavior with a regression test.

In scope: Development Compose configuration, automatic Brain job provider/model snapshots, processing-flow documentation and regression coverage.

Out of scope: Provider selection redesign, automatic repair of historical jobs, retry policy changes and Brain extraction behavior.

## Acceptance criteria

- `transcription-worker`, API and `brain-worker` receive matching `LLM_PROVIDER`, `LLM_MODEL` and `LLM_BASE_URL` defaults.
- A definitive transcription creates a queued Brain job with `provider=ollama` and `model=ornith-1.5:35b` under the default development configuration.
- Existing definitive-transcript-only and provenance behavior remains unchanged.
- Existing jobs with `provider=none` are not silently rewritten; operators can explicitly retry or regenerate them after configuration is corrected.

## States and failure behavior

- New jobs are `queued` with the provider and model snapshot persisted.
- A missing or unsupported provider remains a terminal Brain job configuration failure.
- Existing failed jobs retain their recorded failure until an explicit retry or regeneration action.

## Data and provenance constraints

The definitive transcript remains the only Brain input. Provider, model, prompt version and input hash remain persisted with the job and LLM run. No credentials or transcript content are added to logs.

## Decisions and dependencies

This restores configuration parity across the existing API, transcription-worker and Brain-worker deployment path. No schema, API contract, provider boundary or ownership decision changes, so no new ADR is required. Related decisions: [ADR 0002](../adr/0002-definitive-transcript-source-of-truth.md) and [ADR 0008](../adr/0008-asynchronous-definitive-transcription-worker.md).

## Files changed

- `docker/compose.dev.yml`
- `backend/tests/test_transcription_worker.py`
- `docs/meeting-processing-flow.md`

## Validation

- Focused transcription worker regression test.
- Rendered Compose configuration validation.

## Risks and next action

Existing `provider=none` jobs require explicit reprocessing after the worker configuration is deployed. Verify the worker environment and requeue only the affected meetings.
