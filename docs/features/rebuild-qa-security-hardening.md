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
| 5 | Upload size checked after the whole file is on disk; no live or extracted-audio caps | Partly: upload size is checked before the body is read; duration and size caps are block 4 |
| 6 | Model load failure skips the fallback provider (ADR 0003) | Done (block 1) |
| 6b | A confident minority-language turn was decoded in the dominant language | Done (block 1): confidence rule, ADR 0018 back to Proposed |
| 7 | Diarization exception fails the transcript; clustering is roughly cubic | Open |
| 8 | Agent loss is silent, the agent hangs at stop, UI ignores audio errors | Open |
| 9 | Uncited Brain summary shown; deleted meetings leave text in query runs; prompt lines can be forged | Open |
| 10 | Test isolation per run | Done (block 0): each run uses its own throw-away database, tables are truncated instead of dropped, and test URLs use `127.0.0.1` |
| 11 | Minor findings, Catalan in agent and settings tests | Open |

## Acceptance criteria

1. Every fix has a test that fails on the previous code.
2. Backend, agent and E2E suites, ruff and `check_docs.py` stay green.
3. Anything not fixed is listed with the reason.

## Implementation state

In progress: rows 2–4, 6 and 10 done; rows 1 and 5 partly.

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

## Next action

Rows 4–10.
