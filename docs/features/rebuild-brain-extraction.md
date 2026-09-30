# Feature: Rebuild Brain extraction
Status: partial
Last updated: 2026-09-30

## Objective

After the definitive transcript is saved, extract a summary, topics, decisions, actions, open questions and risks, each citing the transcript segments it comes from. Show it in the meeting with Decisions first (spec §11; `brain-extraction-from-definitive-transcript.md`; ADR 0002, 0009).

## Scope

In scope:
- `brain_jobs`, `llm_runs` and `brain_extractions` (migration `0003_brain`, spec §9).
- Scheduling: the transcription worker creates the job and publishes it to `advera:brain:jobs` only after the transcript is committed. The job snapshots provider, model, base URL, prompt version and output language (ADR 0009, flow step 9).
- A `brain-worker`:
  - It revalidates that the transcript is definitive and matches the job hash; otherwise `INPUT_CHANGED` is terminal.
  - Transcripts over the configured context fail with `TRANSCRIPT_TOO_LONG` and are never silently truncated.
  - A lease heartbeat keeps long LLM calls alive.
  - An `LLMRun` is stored for every call, holding the final output only.
  - Output is schema-validated. Unknown citations are removed, and items left without evidence are dropped.
  - Provider and invalid-output failures retry; configuration failures are terminal.
- `GET` and `POST /api/meetings/{id}/brain`, with the states `blocked`, `not_started`, `queued`, `running`, `completed`, `empty` and `failed`.
- A Brain panel in the meeting page with Decisions first, state badges, owners and due dates, and citations that play the audio from the segment.

Out of scope: normalized decision tables (spec §26, still pending), temporal memory (§12), the concept graph (next increment), and live summaries.

## Acceptance criteria

1. No Brain job exists before the definitive transcript is committed. Provisional data never reaches it.
2. Every stored item cites at least one real segment with its timestamp.
3. A failed or invalid Brain run never modifies the transcript or audio, and is visible and retryable.
4. Changing the output language creates a distinct job (ADR 0009).
5. Deleting the meeting deletes its Brain jobs, runs and extractions.

## Implementation state

Implemented and verified against the real server. It stays `partial` pending independent QA/Security review and a run on real, non-synthetic meetings.

Product owner decision (2026-09-30): the live transcript (plan increment 3) is skipped for now, and the Brain is built before it. This deviates from spec §32 ("No avanzar al brain hasta que este flujo sea estable"). The definitive-only boundary (ADR 0002) makes the order safe, because the Brain never reads provisional data.

## Decisions

- `brain_jobs.base_url` is stored so a queued job runs against the server it was scheduled for. The flow snapshots `LLM_BASE_URL` and the spec §9 field list omits it.
- `llm_runs.raw_output` keeps the final JSON text next to the parsed output (spec §3.4, §36 "raw + parsed"). With thinking disabled and reasoning stripped, it holds no reasoning.
- The idempotency key includes the output language, as ADR 0009 requires; the spec §9 key omits it.
- "Regenerar" force-requeues the current job and replaces its extraction.

## Files changed

- `backend/app/{brain,brain_jobs,brain_worker,brain_api,leases}.py` (new), `backend/app/{models,transcription_worker,config,main}.py`, `backend/migrations/versions/0003_brain.py`
- `backend/tests/test_brain.py`, `backend/tests/integration/test_brain_pipeline.py` (new), `backend/tests/integration/conftest.py`, `backend/tests/test_units.py`
- `frontend/src/features/meeting/{BrainPanel.tsx (new),MeetingPage.tsx}`, `frontend/src/styles.css`, `frontend/tests/e2e/*.spec.ts`
- `docker/compose.dev.yml` (`brain-worker`)

## Validation

- Unit (7): the prompt lists every segment with id, speaker and language; evidence resolves to timestamps; unknown citations are removed and uncited items dropped; `empty` is returned when nothing is found; schema violations are rejected; the JSON schema has every category; the output language gives a distinct job.
- Integration against real PostgreSQL and Redis with a scripted LLM (6):
  - the transcript schedules Brain and the worker stores the result and its `LLMRun`;
  - invalid output retries and then succeeds;
  - an unavailable LLM exhausts retries without touching the transcript;
  - a changed transcript makes the job stale;
  - `blocked` and "Regenerar" behave as specified;
  - deletion cascades.
- E2E: the Brain panel goes from running to completed, Decisions come first, and a citation seeks and highlights the segment.
- Migrations: upgrade, downgrade and upgrade on PostgreSQL; `alembic check` shows no drift.
- Real run: the 120 s synthetic six-speaker ca/es/en meeting, with `ornith-1.5:35b` on the operator's Ollama server, through the real stack (API, Redis, `brain-worker`). It completed on the first attempt in 64 s:
  - a Spanish summary;
  - 2 decisions, both `decided`: extend the storage volume, and ship on Monday;
  - 5 actions with speaker owners, 5 topics, 1 open question and 2 risks;
  - every item cites real segments, with 0 items dropped.
  - Worker logs contained only ids and counts.

## Risks

- A 35B model can take minutes on long transcripts; the lease is 20 min with a 30 s heartbeat.
- Quality depends on the model. Items without valid citations are dropped, never shown.

## Next action

Memory: chunks, BGE-M3 embeddings, hybrid retrieval and cited Q&A.
