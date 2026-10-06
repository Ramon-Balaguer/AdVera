# GitHub settings that enforce the checks

A local hook can be skipped (`git push --no-verify`) or never enabled, so what really makes every
change pass the tests is the configuration of the repository on GitHub, together with the CI
(`.github/workflows/ci.yml`).

## The check that gates everything

The last job of the CI, **CI passed**, succeeds only if every other job succeeded: documentation,
backend (lint, format, **all** tests with PostgreSQL and Redis, 90% coverage, none skipped),
migrations (up, down and up again), agent (lint and tests), frontend (build and the Playwright
tests), landing page and Compose files. A skipped or cancelled job counts as a failure. Branch
protection requires only this one, so adding a job to the CI never needs a change on GitHub.

## Branch protection for `main`

Settings → Rules → Rulesets → New branch ruleset (or Settings → Branches → Add rule), for `main`:

- Require a pull request before merging.
- Require status checks to pass: add **CI passed**, and require the branch to be up to date.
- Block force pushes and deletion of the branch.
- Do not allow bypassing the rule: include administrators.

Repositories that are public can use these rules for free; private ones need a paid plan.

## Releases

Every merge to `main` is a release (`.github/workflows/release.yml`): the version is computed from
the latest tag `vX.Y.Z`, the tag and its GitHub Release are created, and the Docker images are
published as `X.Y.Z`, `X.Y` and `latest`. The pull request's label sets the bump: `major`, `minor`,
or neither (a patch). The first release is `v0.1.0`. Nothing is committed to `main`, so the
protection above stays as it is. Two merges in quick succession may share one release: only one
run waits in the queue.

## Other settings

- Settings → Pages → Source: **GitHub Actions** (the landing page).
- Settings → Code security: enable private vulnerability reporting, Dependabot alerts and secret scanning.
