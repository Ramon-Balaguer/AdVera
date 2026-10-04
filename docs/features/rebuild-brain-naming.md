# Feature: Rebuild Brain naming
Status: complete
Last updated: 2026-10-04

## Objective

Make Brain the name of the knowledge of all the meetings (search, graph, timeline, index) and Summary the name of what is extracted from one meeting, everywhere: code, data, queues, API, interface and documents (ADR 0022).

## Scope

- Backend modules, classes, tables, queues, settings, environment variables and routes renamed (memory to brain, brain to summary); migration `0009_brain_naming` renames tables, columns, constraints and indexes and the stored `BRAIN_*` error codes.
- Compose services `summary-worker` and `brain-worker`; the optional extra is `brain`.
- Front end: page and route `/brain`, menu entry with a brain icon and the text "Brain", `SummaryPanel` for the meeting, texts in English, Spanish and Catalan ("Search the brain", "Brain graph", "Meeting summary").
- All documents rewritten, including the file names of the records.

Out of scope: any behaviour change; the prompt and projection versions stored in the database (`brain-extraction-v10`, `memory-chunks-v1`, `memory-concepts-v1`) keep their names.

## Acceptance criteria

1. No `memory` or `brain` left in the old sense in code, configuration or documents (RAM uses of "memory", the SpeechBrain library and the stored versions excepted).
2. The migration keeps every row, leaves no object with an old name and downgrades symmetrically.
3. The backend suite (at least 90% coverage), the Playwright suite and `check_docs.py` pass.
4. After deployment the three workers run on the new queues, `/brain` answers, and the graph, the search and the meeting summaries show the existing data without calling the model again.

## Implementation state

Code, migration, interface and documents renamed and the tests pass (backend 90.17%, 53 Playwright). Deployment pending.

## Decisions

- Short name `summary` in the code instead of `meeting_summary`.
- Names in the menu are the brand "Brain" in the three languages; the page and its texts use Brain, Cerebro and Cervell.
- The old documents were rewritten too, instead of keeping the old names as history (operator decision).

## Files changed

- `backend/app/*` (renamed modules), `backend/migrations/versions/0009_brain_naming.py`, `backend/tests/*`, `docker/compose*.yml`, `.env.example`, `backend/pyproject.toml`
- `frontend/src/**` (`features/brain`, `features/meeting/SummaryPanel.tsx`, `i18n/*`, `App.tsx`), `frontend/tests/e2e/*`
- `docs/**`, `.github/agents/*`, `scripts/*`

## Validation

- Migration on a copy of the real database: identical row counts, no old names, `downgrade` restores every name.
- Backend suite, Playwright suite and `check_docs.py`.

## Risks

- A deployment with the old workers still consuming the old queues; the workers are stopped first and the old streams removed.
- A text where "memory" meant RAM or product memory was converted by mistake; the known cases were corrected by hand.

## Next action

None.
