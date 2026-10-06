# Contributing to AdVera

Thank you for helping. AdVera is built from its documentation: read [`docs/agent-workflow.md`](docs/agent-workflow.md) first. In short:

- Every change has a feature record in [`docs/features/`](docs/features/README.md) (one per increment), and a decision that changes a boundary gets an ADR in [`docs/adr/`](docs/adr/README.md). Where documents disagree: ADRs, then the meeting processing flow, then the Redis contract, then the feature records, then the plan and the spec.
- Tests come with the change. The backend keeps statement coverage at 90% or more.
- No real meeting data anywhere: audio, transcripts, prompts or notes in code, tests, issues or logs. Tests use synthetic data, with Catalan, Spanish and English.
- The name is always written **AdVera**.
- By contributing you agree that your work is published under the project's licence, the [Elastic License 2.0](LICENSE), and you grant the author, Ramon Balaguer, the right to also license it under other terms, including commercial licences.

## Setting up

See the [README](README.md) for the stack. Then enable the repository's Git hooks, once per clone:

```bash
git config core.hooksPath .githooks
```

The `pre-push` hook runs, for the parts a push changes, the quick checks: documentation, ruff and the unit tests of the backend and the agent, the frontend types and the landing page scripts. It takes seconds. The full suite (integration tests against PostgreSQL and Redis, Playwright, migrations) runs in CI on every push and pull request, and `main` only accepts changes that pass it.

## Pull requests

1. Branch from `main` (`feature/…` or `fix/…`).
2. Keep the change small and focused, with its feature record and tests.
3. Make sure `python scripts/check_docs.py` and the checks in the README pass.
4. Describe what changed and how you verified it.
