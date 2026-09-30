# Agent code coverage to 90%
Status: partial
Last updated: 2026-09-20

## Objective

Raise statement coverage for the `agent` package from the existing baseline to at least 90% with deterministic tests for normal, failure, cleanup, platform-specific, and transport behavior.

## Scope

- Add focused tests under `agent/tests/` for the uncovered agent modules and branches.
- Use synthetic devices, sockets, GUI objects, and Windows registry APIs.
- Keep production behavior unchanged unless a test exposes a real defect.
- Keep backend and frontend coverage out of scope.

## Acceptance criteria

- `python -m pytest --cov=agent --cov-report=term-missing --cov-fail-under=90 tests` passes from `agent/`.
- Existing tests pass without real audio hardware, tray UI, network services, or production credentials.
- Tests verify behavior and failure handling rather than only executing statements.

## Implementation state

Complete. The package now reports 90.04% statement coverage with 60 passing tests.

## Decisions

- Measure package statement coverage with `pytest-cov`.
- Mock platform integrations at their module boundaries.
- Preserve the existing Spanish user-facing messages and agent contracts.

## Files changed

- `agent/tests/test_agent.py`
- `agent/tests/test_agent_core.py`
- `agent/tests/test_agent_transport.py`
- `agent/tests/test_agent_ui.py`
- `docs/features/agent-code-coverage-90.md`

## Validation

- Baseline: 42% with 21 tests collected and three hardware-dependent test failures.
- Final: `python -m pytest --cov=agent --cov-report=term-missing --cov-fail-under=90 tests` passes with 60 tests and 90.04% coverage.

## Risks

- Tkinter, tray, registry, and audio libraries require complete mocks to remain deterministic.
- 82 statements remain uncovered, concentrated in defensive optional-dependency and advanced remote transport branches.

## Next action

Keep the 90% command as the agent quality gate and expand remote transport tests if its protocol grows.
