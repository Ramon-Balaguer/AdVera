# Feature: Rebuild robustness fixes
Status: in progress
Last updated: 2026-10-03

## Objective

Four problems were reported on 2026-10-03 (workers, Redis streams, interface language, silent frontend errors). Each was checked in the code before being fixed. This record keeps what was confirmed and what was not, and the state of each fix.

## Scope

1. **A PostgreSQL outage ended the Brain and Memory workers.** Confirmed. `consume()` in the Brain worker, which Memory reuses, caught only Redis and OS errors, while the transcription worker had its own copy that also caught `SQLAlchemyError`. `reconcile()`, `ensure_group()` and the recording of a job failure all touch PostgreSQL, so the exception left the loop and the process ended; Docker's `restart: unless-stopped` brought it back, so the effect was a crash and restart cycle at every database pause, not a permanent stop. Fixed: one loop for the three workers in `backend/app/consumer.py`, which waits and goes on after a Redis, OS or SQLAlchemy error; the copy in the transcription worker is gone. A job interrupted by an outage keeps its lease and `reconcile()` recovers it.
2. **Redis streams grow without bound.** Confirmed, with a nuance: no job is lost (reconciliation reads PostgreSQL); what grows is the stream (acknowledged entries are never trimmed) and the pending list of dead consumers (the consumer name is the container hostname, which changes at every recreation). Pending.
3. **Language changes leave texts in the old language.** Partly confirmed. Texts computed while rendering do follow the language (the app re-renders from `App`); texts stored in component state when they were produced (messages such as "Saved" or an error, the list of meetings that could not be deleted, the tag picker's messages) and the reference chip of the notes editor do not. Pending.
4. **Silent frontend errors.** Confirmed: the Memory question has no `try/catch` around `fetch` and `parse`, WebSocket frames are parsed without a guard in four places, and the live-level sockets of the agent have neither `onclose` nor `onerror`. Pending.

Out of scope: any change of behaviour beyond these four.

## Acceptance criteria

1. A PostgreSQL or Redis outage never ends a worker: it waits and goes on.
2. (pending) The streams stay bounded and entries left by dead consumers are reclaimed.
3. (pending) A message already shown follows a language change.
4. (pending) A network failure or a malformed frame is shown or ignored, never an unhandled rejection.

## Implementation state

Point 1 implemented and tested. Points 2 to 4 are planned (`plan` of 2026-10-03) and not started.

## Decisions

One shared consumer loop instead of two copies, so the recoverable errors cannot diverge again.

## Files changed

- `backend/app/consumer.py` (new), `backend/app/{brain_worker,memory_worker,transcription_worker}.py`
- `backend/tests/test_consumer.py` (new)

## Validation

- `tests/test_consumer.py`: a PostgreSQL error during reconciliation, a Redis error while reading, and a job whose failure could not be recorded (acknowledged, the loop goes on). Before the change the old loop ended with `OperationalError`.
- Backend suite and ruff.

## Risks

- A message acknowledged for a job whose failure could not be recorded relies on `reconcile()` to recover it once the database is back.

## Next action

Points 2, 3 and 4, as the operator decides.
