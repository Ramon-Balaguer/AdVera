# Feature: Rebuild QA and security hardening
Status: in progress
Last updated: 2026-09-30

## Objective

Fix what the first independent QA/Security review found (three read-only reviewers: capture/agent/import, Brain/Memory/settings, transcription/deployment), in priority order, each fix with a regression test. The reviewers did not write the reviewed code, as `agent-workflow.md` requires.

## Scope

Decisions taken by the operator after the review:
- AdVera is used from other LAN machines: the API stays reachable, so a shared access token is mandatory (ADR 0019).
- A chunk keeps its detected language when detection is confident; the 5% share filter applies only to doubtful detections (amends ADR 0018).
- Once a meeting has recorded audio, its recording zone is disabled instead of replacing the audio.
- The Ollama hostname was removed from the whole git history.

| # | Finding | Status |
|---|---|---|
| 1 | LAN hosts could start the agent, download audio, read everything | Done: ADR 0019 token, datastores on loopback, agent asks locally before recording |
| 2 | LLM URL accepted metadata, link-local and internal addresses | Done: destination rules on write and discovery |
| 3 | Operator's Ollama hostname committed | Done: removed, history rewritten |
| 4 | Second `start` corrupts a live recording; imports race each other and recordings | Open |
| 5 | Upload size checked after the whole file is on disk; no live or extracted-audio caps | Open |
| 6 | Model load failure skips the fallback provider (ADR 0003) | Open |
| 7 | Diarization exception fails the transcript; clustering is roughly cubic | Open |
| 8 | Agent loss is silent, the agent hangs at stop, UI ignores audio errors | Open |
| 9 | Uncited Brain summary shown; deleted meetings leave text in query runs; prompt lines can be forged | Open |
| 10 | Minor findings, test isolation per run, Catalan in agent and settings tests | Open |

## Acceptance criteria

1. Every fix has a test that fails on the previous code.
2. Backend, agent and E2E suites, ruff and `check_docs.py` stay green.
3. Anything not fixed is listed with the reason.

## Implementation state

In progress: rows 1–3 done.

## Decisions

See ADR 0019. The token gate is a pure ASGI middleware so WebSocket handshakes are covered. Rejecting loopback and private LAN addresses for the LLM URL was considered and dropped because Ollama commonly runs there.

## Files changed (rows 1–3)

- `backend/app/{auth,net_safety,settings_api,capture_agent,config,main}.py`, `backend/tests/{test_auth,test_llm_settings}.py`
- `agent/advera_agent/{consent,remote,tray,config,__main__}.py`, `agent/tests/test_remote.py`
- `frontend/src/{AccessGate,main,api}.ts*`, `frontend/tests/e2e/access-gate.spec.ts`
- `docker/compose.dev.yml`, `.env.example`, `docs/adr/{0015,0019,README}.md`

## Validation

- Backend 121+ tests, agent 16, E2E 16 at this point.

## Risks

The token travels in clear over HTTP on the LAN; use HTTPS when the network is not trusted (ADR 0019).

## Next action

Rows 4–10.
