# Feature: Transcription Worker MOSS Readiness
Status: complete
Last updated: 2026-09-26

## Problem

The transcription worker can start consuming jobs before the MOSS transcription API is ready, causing avoidable provider failures during model startup.

## Target user

Operators and developers running AdVera with MOSS as the definitive transcription provider.

## Desired outcome

The worker waits for MOSS readiness, reports the waiting state, and resumes queue processing automatically when MOSS becomes available.

## Smallest useful increment

Poll MOSS `GET /health` before queue setup when MOSS is the definitive provider, with a configurable interval and safe status logs.

## In scope / Out of scope

In scope: startup readiness polling, operator-visible logs, recovery after transient failures, and regression tests.

Out of scope: changes to MOSS, transcription persistence, queue semantics, or downstream processing.

## User acceptance criteria

- The worker does not process transcription jobs while MOSS is unavailable.
- The worker remains alive, reports that it is waiting, and retries automatically.
- The worker resumes normal processing after MOSS returns a successful health response.
- Non-MOSS providers retain the existing startup behavior.
- Logs contain no token, audio, transcript, or meeting content.

## States and failure behavior

The worker enters `waiting_for_moss` after a connection, timeout, or HTTP health failure, then retries after the configured interval. A successful health response transitions it to ready. Other providers bypass this gate.

## Data and provenance constraints

Readiness checks do not create or alter transcript data. Logs include only the safe health URL, error type, and retry interval.

## Dependencies and constraints

MOSS exposes `/health`, matching the Docker Compose healthcheck. The worker must remain compatible with Redis queue and lease behavior.

## Assumptions and open questions

The Compose `/health` endpoint is the runtime readiness contract. The polling interval defaults to five seconds and can be adjusted through settings; endpoint customization can be added if another deployment requires it.

## Validation

Focused tests cover unavailable then ready MOSS, non-MOSS bypass, and safe logging. The backend worker test suite is the acceptance check.

Commands run:

- `python -m pytest tests/test_transcription_worker.py -q` -> 3 passed.
- `python -m ruff check app/transcription_worker.py app/config.py tests/test_transcription_worker.py` -> passed.
- `docker compose -f docker/compose.dev.yml config --quiet` -> passed.
- `python -m pytest -q` -> blocked during collection because the active environment lacks `langdetect`.

## Files changed

- `backend/app/transcription_worker.py`
- `backend/app/config.py`
- `backend/tests/test_transcription_worker.py`
- `docker/compose.dev.yml`
- `docs/features/transcription-worker-moss-readiness.md`

## Decisions, risks and next action

Application-level waiting is used so the worker also behaves correctly outside Compose. A long MOSS startup produces periodic warning logs. Next action is QA/security review of the focused tests and deployment behavior.
