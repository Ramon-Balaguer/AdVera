# Feature: Rebuild backend coverage to 90%
Status: done
Last updated: 2026-10-04

## Objective

Raise the statement coverage of `backend/app` from the measured 87% to at least 90% with tests of observable behaviour, and keep it there with a gate. Planned on 2026-10-03; the operator decided not to do it yet.

## Baseline

Measured on 2026-10-03 with `python -m pytest --cov=app --cov-report=term-missing tests` from `backend/` (`pytest-cov` is declared in the `dev` extras since then): 275 tests, 4,710 statements, 589 missed, **87%**. Reaching 90% means covering at least **118** more statements (471 missed at most). The run takes about two minutes.

| Module | Cover | Missed | What is not covered |
|---|---|---|---|
| `memory_worker.py` | 77% | 68 | `run()`/`main()`, failures of the query worker (LLM error, empty answer), embedding failures |
| `capture_agent.py` | 82% | 57 | disconnection and error paths of the agent relay |
| `asr_whisperx.py` | 19% | 55 | needs the real model and a GPU |
| `memory_backfill.py` | 28% | 55 | `backfill()` and `main()`; only `_reproject` is tested |
| `brain_worker.py` | 78% | 49 | `run()`/`main()`, `reconcile()`, stale or too long transcripts, provider errors |
| `transcription_worker.py` | 85% | 42 | `run()`, failure paths |
| `diarization.py` | 82% | 35 | branches of the real engine |
| `embeddings.py` | 46% | 25 | needs BGE-M3 |
| `media_import.py` | 77% | 19 | extraction timeouts and errors |
| `transcription_jobs.py` | 85% | 14 | retry and failure bookkeeping |
| `settings_api.py` | 83% | 9 | invalid updates, model discovery errors |

## Scope

Tests, in this order, with the statements each should add:
1. **`memory_backfill`** (about 45): `backfill()` against the real test database with meetings that have definitive transcripts, covering `--brain`, `--concepts`, `--rebuild`, `--meeting`, `--exclude-title`, `--reproject` and a meeting without transcript; `main()` with a patched `sys.argv`.
2. **`brain_worker`** (about 35): `run()` and `reconcile()` with a stop event, a stale transcript (`INPUT_CHANGED`), a transcript too long for the context, a provider that cannot be built, a lease lost during the model call.
3. **`memory_worker`** (about 35): `run()`, a query whose LLM fails (`LLM_UNAVAILABLE`), an embedding failure that falls back to full-text chunks, a lost lease.
4. **`transcription_worker`** (about 25): `run()` and the engine failure paths with the fake engine.
5. **`settings_api` and `transcription_jobs`** (about 20): invalid settings, unreachable model server, retries exhausted.

That is about 160 statements, enough for 90% with margin. Everything uses synthetic data, fakes for models, queues and the LLM, and the throw-away PostgreSQL and Redis of the test run.

Optional, not needed for the 90%: adapters that need a real model (`asr_whisperx`, `embeddings`) tested with fake `whisperx` and `sentence_transformers` modules, which would check how their output is mapped but not the models themselves.

Out of scope: the agent and the frontend (their own records), `# pragma: no cover` (all production code stays in the measured scope), and any change of production behaviour to improve the number.

## Acceptance criteria

1. From `backend/`, `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 tests` passes.
2. The tests assert behaviour (job states, messages, errors recorded), not only that lines run.
3. No real service, model, GPU, audio device, credential or meeting is needed or touched (never the operator's "test" meeting).
4. Once 90% is reached, the gate stays: `fail_under = 90` in `pyproject.toml` and in the QA gate (`qa-release-gate.md`), so it cannot silently drop.

## Implementation state

Done on 2026-10-04: 90.15% (4,710 statements, 464 missed) with `--cov-fail-under=90` passing. Added `tests/integration/test_memory_backfill.py` (7 tests), `tests/test_worker_entrypoints.py` (8 tests: `run()` and `main()` of the three workers, embedding and diarizer builders) and 2 settings API tests (malformed URL, model discovery). The margin is thin (about 7 statements); the `brain_worker`, `memory_worker` and `transcription_worker` failure paths of steps 2 to 4 were not covered one by one, only their entry points. `fail_under = 90` is now in `pyproject.toml`.

## Decisions

- Measure statement coverage of all of `app`, with no exclusions, as the earlier record did.
- Cover the worker entry points with the real test database and Redis rather than mocking them, so the tests also check the wiring.
- Turn on the gate only when 90% is reached, so it is not red in the meantime.

## Files changed

- `backend/pyproject.toml` (`pytest-cov` in `dev`; later the gate)

## Validation

When done: the command of criterion 1, ruff, and the whole suite.

## Risks

- The worker `run()` tests start loops that must stop cleanly (a stop event and a bounded wait); a mistake would hang the suite.
- 90% can be reached without testing the hard parts (the real ASR, diarization and embedding engines), which only a run with real models checks.

## Next action

Optional: cover the worker failure paths of steps 2 to 4 for a larger margin.
