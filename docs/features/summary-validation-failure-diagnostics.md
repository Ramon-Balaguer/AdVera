# Feature: Summary Validation Failure Diagnostics
Status: in progress
Last updated: 2026-09-25

## Objective

Make Summary validation failures actionable and prevent futile retries.

## Acceptance criteria

- Summary jobs preserve a safe, specific validation reason.
- `TypeError` and `ValueError` failures become terminal after the first attempt.
- Provider availability and request failures retain retry behavior.
- Failure logs include the safe reason alongside meeting and job identifiers.
- Existing definitive transcript provenance remains unchanged.

## Root cause and decision

The affected jobs were created with `provider=none`, causing `Summary LLM provider is not configured`. The worker previously replaced that reason with a generic message and retried it until `max_attempts`. Validation failures are non-transient, so the worker now preserves their reason and stops retrying them.

## Files changed

- `backend/app/worker.py`
- `backend/tests/test_summary_worker.py`

## Validation

Run the focused Summary worker tests, then recreate the affected jobs with the currently configured `ollama` provider.

## Risks and next action

Existing failed jobs remain terminal and require an explicit force/reprocess action. Verify Ollama availability before requeueing them.