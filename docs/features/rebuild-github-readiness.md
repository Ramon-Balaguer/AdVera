# Feature: Rebuild GitHub readiness
Status: in progress
Last updated: 2026-10-06

## Objective

Prepare the repository to be published on GitHub: checks before a push, contribution and security guides, issue and pull request templates, dependency updates, and a CI that enforces what the project promises.

## Scope

- `.githooks/pre-push`: for the parts a push changes, the quick checks (docs, ruff and unit tests of the backend and the agent, frontend types, landing page script syntax); enabled per clone with `git config core.hooksPath .githooks`.
- `CONTRIBUTING.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`, `.github/dependabot.yml`.
- CI: the backend runs `pytest --cov=app` so the 90% coverage gate applies; a job checks the landing page scripts.
- `.gitignore`: editor folders.
- Docker base images pinned to an exact version and digest (`docker/IMAGES.md`): pgvector 0.8.6 on PostgreSQL 16, Redis 7.4.11, Python 3.12.14 and Node 24.21.0; Dependabot proposes updates.

Out of scope: replacing Redis with Valkey (later), the licence text until it is added, the remote and its branch protection (done on GitHub), rewriting history (the operator keeps the commits as they are).

## Acceptance criteria

1. The hook stops a push when a check of a changed part fails, and takes seconds.
2. The CI covers docs, backend (with coverage gate), migrations, agent, frontend (build and Playwright), landing page and Compose files.
3. No secret, real meeting data or private address in the tracked files.

## Implementation state

Done on branch `feature/github-ready`. A hook run over a range that changes the backend, frontend, landing page and docs took 15 seconds and passed.

## Decisions

- The hook runs quick checks only; the full suite is the CI's job, and branch protection on `main` is what enforces it (a hook can always be skipped with `--no-verify`).
- Commits keep their author e-mail (operator decision).

## Files changed

- `.githooks/pre-push`, `CONTRIBUTING.md`, `SECURITY.md`, `README.md`, `.gitignore`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.github/ISSUE_TEMPLATE/*`, `.github/pull_request_template.md`

## Validation

- The hook on a real range of commits; `check_docs.py`.

## Risks

- Without a licence the published code cannot legally be reused.

## Next action

The operator chooses a licence, creates the GitHub repository, enables branch protection and Pages.
