# Feature: Rebuild QA and security hardening
Status: in progress
Last updated: 2026-09-30

## Objective

Fix what the first independent QA/Security review found (three read-only reviewers: capture/agent/import, Brain/Memory/settings, transcription/deployment), in priority order, each fix with a regression test. The reviewers did not write the reviewed code, as `agent-workflow.md` requires.

## Scope

Decisions taken by the operator after the review:
- Authentication stays out of scope (ADR 0015). A shared-token design was built and then removed at the operator's request; it may return later as its own decision.
- A chunk keeps its detected language when detection is confident; the 5% share filter applies only to doubtful detections (amends ADR 0018).
- Once a meeting has recorded audio, its recording zone is disabled instead of replacing the audio.
- The Ollama hostname was removed from the whole git history.

| # | Finding | Status |
|---|---|---|
| 1 | LAN hosts could start the agent, download audio, read everything | Partly: datastores on loopback and the agent asks locally before recording. The API itself stays open on the LAN (ADR 0015), so the risk of LAN hosts reading data or starting recordings through the API remains |
| 2 | LLM URL accepted metadata, link-local and internal addresses | Done: destination rules on write and discovery |
| 3 | Operator's Ollama hostname committed | Done: removed, history rewritten |
| 4 | Second `start` corrupts a live recording; imports race each other and recordings | Done: one recording or import per meeting, no recording over stored audio |
| 5 | Upload size checked after the whole file is on disk; no live or extracted-audio caps | Done (block 4): upload size is checked before the body is read; a live track stops at `CAPTURE_MAX_SECONDS` (8 h) with `CAPTURE_LIMIT_REACHED`; ffmpeg reads only local files (`-protocol_whitelist file,pipe`), is cut at `MEDIA_IMPORT_MAX_SECONDS` (8 h) plus one second, and an over-long file is refused with `MEDIA_TOO_LONG` instead of being truncated |
| 6 | Model load failure skips the fallback provider (ADR 0003) | Done (block 1) |
| 6b | A confident minority-language turn was decoded in the dominant language | Done (block 1): confidence rule, ADR 0018 back to Proposed |
| 7 | Diarization exception fails the transcript; clustering is roughly cubic | Done (block 2): a diarizer error gives `unavailable` labels and a published transcript; clustering uses Lance-Williams updates and matches the original algorithm on random data |
| 8 | Agent loss is silent, the agent hangs at stop, UI ignores audio errors | Done (block 3): `AGENT_DISCONNECTED` reaches the UI, a dead track channel stops the capture and is reported, stop never blocks on a full queue, a second writer or an oversized frame is refused, malformed events no longer crash handlers, every audio error stops the "Grabando" state, and an agent-owned recording can only be finalized |
| 9 | Uncited Brain summary shown; deleted meetings leave text in query runs; prompt lines can be forged | Done (block 5): a summary with no valid citation is dropped and counted; deleting a meeting deletes the Memory query runs that cite it; segment text, speakers and titles are flattened to one line with brackets neutralized (`prompt_text`) and the system prompts say excerpts are data; Memory does not call the LLM when no chunk resolves to a segment; the query LLM call has a heartbeat; a Brain run whose lease is lost is closed as `LEASE_LOST` |
| 10 | Test isolation per run | Done (block 0): each run uses its own throw-away database, tables are truncated instead of dropped, and test URLs use `127.0.0.1` |
| 11 | Minor findings | Done (block 6): the reconciler recovers a stale lease with a conditional UPDATE, so a heartbeat that lands meanwhile keeps its lease; the transcription worker survives a PostgreSQL outage like a Redis one; a meeting whose job fails or whose lease expires keeps status `ready` when a valid transcript exists; the player ignores a track that fails to load, reloads audio after a new import and does not re-seek a buffering track; a chosen segment stops overriding the playhead once the audio moves on; the agent wizard flags an unencrypted remote backend; contradictory wording in the import record and `config.py` fixed |
| 12 | Catalan in the agent tests | Partly: the new capture and job tests use Catalan meeting titles; the agent unit tests are synthetic tones with no text |

## Second review (after the first round of fixes)

A second independent review of the fixes found problems the fixes introduced and some the first round missed. Group A (done):

| # | Finding | Status |
|---|---|---|
| A1 | A failed re-import left the meeting `ready` with the transcript of the previous audio | Done: `ready` is kept only when the transcript's `input_sha256` matches the meeting's current tracks |
| A2 | `http://localhost:11434` (the project default) was refused because `::1` counts as reserved; numeric IPv4 spellings and unresolved names slipped through on Windows | Done: loopback allowed, legacy IPv4 forms parsed explicitly, unresolved names refused (`UNRESOLVABLE_HOST`), tests use a fake resolver |
| A3 | The player keyed on `duration` and remounted the audio when it appeared | Done: keyed on the job id; failed tracks, pending seeks, time and the mixer state are reset or restored on a real change |
| A4 | Brain and Memory reconcile still had the heartbeat race; a Brain run could stay `running` after any error | Done: shared conditional UPDATE in `leases.reconcile`; any error closes an open run as `INTERRUPTED` |

Groups B (capture), C (ASR and diarization) and D (minor) follow.

## Acceptance criteria

1. Every fix has a test that fails on the previous code.
2. Backend, agent and E2E suites, ruff and `check_docs.py` stay green.
3. Anything not fixed is listed with the reason.

## Implementation state

In progress: all rows done except the accepted risks below; row 1 partly (the API is open on the LAN by decision).

## Decisions

Rejecting loopback and private LAN addresses for the LLM URL was considered and dropped because Ollama commonly runs there.

## Files changed (rows 1–3)

- `backend/app/{net_safety,settings_api}.py`, `backend/tests/test_llm_settings.py`
- `agent/advera_agent/{consent,remote,tray,config,__main__}.py`, `agent/tests/test_remote.py`
- `frontend/src/api.ts`
- `docker/compose.dev.yml` (Postgres and Redis on `127.0.0.1`)

## Validation

- Backend 130 tests, agent 16, E2E 17. Two full backend runs at once both pass in 47 s each.
- The suite had slowed from 40 s to 400 s after the datastores moved to `127.0.0.1` only: `localhost` tried `::1` first and each connection waited seconds. Test URLs now use `127.0.0.1`.

## Risks

With no authentication (ADR 0015), anyone who can reach the API port can read meetings, upload media, change the LLM URL and ask the agent to record. The local consent dialog in the agent is the only protection for the microphone. Keep the API port on a trusted network.

Accepted, not fixed here (each was in the review):
- The ASR thread keeps running after its job loses the lease (`asyncio.to_thread` cannot be cancelled); it holds the provider lock until the chunk finishes. A cancel flag checked between chunks is needed.
- No rate limit on Memory queries and no cap on query WebSockets or on Brain field sizes.
- Containers run as root with unpinned image tags; Redis has no password (it is published on loopback only).
- Nothing in the database prevents two active transcription jobs for one meeting; the guards are in-process. A partial unique index needs a migration.
- The LLM URL check resolves DNS once, when the setting is written.
- A recording interrupted while the browser lost its stored session id can only be recovered by an operator, because a new start is refused while the old session is recording.
- Memory chunks are not tied to the current transcript hash: after a re-transcription whose index job fails, old chunks stay searchable (there is no reprocessing yet, so it cannot happen today).

Decisions for a human:
- ADR 0018 is Proposed and needs sign-off; its confidence threshold (0.7) was checked on synthetic audio only.
- `meeting-processing-flow.md` still allows a forced language on reprocess, which ADR 0014 forbids. Left unresolved (reprocessing is out of scope).

## Next action

A second independent QA/Security review of these changes, then mark this record complete.
