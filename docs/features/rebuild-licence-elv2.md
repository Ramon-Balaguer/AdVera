# Feature: Rebuild licence ELv2
Status: complete
Last updated: 2026-10-06

## Objective

Stop third parties from offering AdVera as a paid hosted service without a licence from the author, while the source stays public.

## Scope

- `LICENSE`: the Elastic License 2.0, with the licensor named and a contact for a commercial licence.
- The `license` field (`Elastic-2.0`) of `backend/pyproject.toml`, `agent/pyproject.toml`, `frontend/package.json` and its lockfile.
- `README.md` (intro and a Licence section), `CONTRIBUTING.md` (contributions under ELv2, with a grant to the author to license them under other terms) and the landing page (English and Spanish): "source available" instead of "open source".

## Acceptance criteria

1. No tracked file says AdVera is open source or AGPL, except the note that earlier versions remain AGPL-3.0.
2. `scripts/check_docs.py` passes.

## Implementation state

Done in the working tree, not yet committed.

## Decisions

- ELv2 over FSL (operator decision, 2026-10-06): the hosting restriction is permanent rather than lifting after two years.
- AdVera is no longer open source in the OSI sense; it is called "source available".
- Versions published before this change stay under the AGPL-3.0.
- Dependencies reviewed: MIT, BSD, Apache-2.0 and OFL-1.1, plus `pystray` (LGPL-3.0, imported unmodified by the agent), all compatible.

## Files changed

- `LICENSE`, `README.md`, `CONTRIBUTING.md`, `backend/pyproject.toml`, `agent/pyproject.toml`, `frontend/package.json`, `frontend/package-lock.json`, `landingpage/index.html`, `landingpage/i18n.js`

## Validation

- `git grep` for open source and AGPL mentions; `check_docs.py`.

## Risks

- Not legal advice; a lawyer should review before selling commercial licences.

## Next action

Commit, push and announce the change in the release notes.
