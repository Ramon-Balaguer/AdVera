# Feature: QA release gate
Status: blocked
Last updated: 2026-09-17

## Problem and target user
Users should not have to discover runtime, syntax or integration errors after an implementation is reported as complete. The AdVera QA and Security agent must filter those failures before approval.

## Desired outcome
Every completed change has an independent QA decision with reproducible evidence. Critical and high-severity findings, failed checks and unavailable validation keep the change blocked.

## Scope
- Require compile/import validation, focused tests, lint when configured and relevant service smoke tests.
- Require an explicit `PASS` or `FAIL` decision with commands, findings, residual risks and next action.
- Treat lazy-loaded ASR initialization as requiring an in-container provider smoke test.
- Correct the syntax defect found in `backend/app/asr.py` during QA review.

## Acceptance criteria
- QA reports `PASS` or `FAIL` and includes executable evidence.
- A failed or unavailable check cannot be approved.
- Critical or high-severity findings block completion.
- Backend compilation passes after the ASR syntax correction.
- No real audio, transcript content, secrets or tokens are used in validation.

## States and failure behavior
`planned` -> `in_progress` -> `qa_pending` -> `qa_passed` -> `complete`.

A failed check or unresolved finding sets the change to `qa_failed` or `blocked`. The implementation agent must correct the issue and QA must rerun the failed check.

## Data and provenance constraints
Use synthetic fixtures or anonymized data. Record commands and outcomes without recording meeting content, credentials or chain-of-thought. Definitive transcript rules remain unchanged.

## Dependencies and assumptions
The QA agent can execute repository checks and inspect the changed files. Docker-based ASR checks require Docker Desktop and the configured image dependencies.

## Implementation record
- Strengthened `.github/agents/advera-qa-security.agent.md` with mandatory release-gate checks and a PASS/FAIL decision record.
- Added this dedicated feature record and indexed it in `docs/features/README.md`.
- Removed the stray token that caused an `IndentationError` in `backend/app/asr.py`.

## Validation
- `py -3.14 -m compileall -q backend/app` passed.
- `py -3.14 -m ruff check backend/app/asr.py` passed after correcting import order.
- `py -3.14 -m pytest -q backend` passed: `16 passed`.
- Independent QA review identified the syntax failure before completion and supplied reproduction evidence.
- The full backend lint gate is blocked by 14 findings in existing modules outside this feature slice.

## Risks and open questions
- Local Windows terminals may not expose `git` or Docker on `PATH`; QA must use configured absolute tool paths when needed.
- ASR dependencies are container-only in some environments, so local diagnostics may report unresolved imports even when the container smoke test passes.

## Next action
Resolve or explicitly scope the 14 existing backend lint findings, then rerun the full gate and the Docker ASR provider smoke test for the final independent QA decision.
