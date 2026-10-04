# Backend statement coverage to 90%
Status: partial
Last updated: 2026-09-20

## Objective

Raise statement coverage for `backend/app` from the measured 79% baseline to at least 90% with deterministic, behavior-oriented tests organized by backend domain.

## Scope

- Add functional tests for uncovered API, audio, worker, intelligence, and brain failure paths.
- Use synthetic data and mocks for databases, queues, models, audio devices, and external services.
- Preserve definitive-transcript and provenance constraints.
- Keep test filenames organized by domain; do not use metric-oriented filenames.

## Acceptance criteria

- From `backend/`, `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 tests` passes.
- Existing tests remain green and no real services, credentials, meetings, GPUs, or audio hardware are required.
- Tests assert observable behavior and failure handling.

## Implementation state

In progress.

## Decisions

- Measure all importable modules under `app` using statement coverage.
- Add tests to existing domain files or descriptive domain-specific files.
- Do not change production behavior solely to improve the metric.
- Do not use `pragma: no cover`; all backend production code remains part of the measured scope.

## Baseline

- Baseline: 95 tests passing.
- 146 tests passing.
- 90.06% total statement coverage without exclusions (2,766 statements, 275 missed).

## Files changed

- `backend/tests/test_backend_services.py`
- `backend/tests/test_brain_backend.py`
- `backend/tests/test_worker_services.py`
- `backend/app/audio.py`
- `backend/app/worker.py`
- `backend/app/brain_worker.py`
- `backend/app/backfill_brain.py`

## Validation

`python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 tests -q` passed: 146 tests, 90.06% coverage without exclusions. Three dependency deprecation warnings remain.

## Risks

Individual integration modules remain below 90%, especially audio, backfill, and worker orchestration, while the backend total meets the gate. No production code is excluded from the metric.

## Next action

Keep the 90% gate in CI and raise module-level coverage for audio, backfill, and Redis worker orchestration as those integrations evolve.