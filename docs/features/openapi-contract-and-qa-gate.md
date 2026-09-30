# OpenAPI Contract and QA Gate
Status: partial
Last updated: 2026-09-20

## Objective
Publish and continuously verify AdVera's generated OpenAPI contract and interactive API documentation.

## Scope
- Keep FastAPI's generated OpenAPI document as the single contract source.
- Publish and verify `/openapi.json`, `/docs`, and `/redoc`.
- Make API metadata intentional and stable.
- Add a focused backend contract test that can run locally and in CI.
- Document the validation command and exposure policy.

Out of scope: API redesign, authentication, external API portals, SDK generation, and API versioning beyond the current backend version.

## Acceptance criteria
- `GET /openapi.json` returns HTTP 200 with a valid OpenAPI document.
- The document identifies the AdVera API and its intentional version.
- `GET /docs` and `GET /redoc` return HTTP 200.
- The schema contains the health endpoint and all registered API router paths.
- The automated test fails when documentation endpoints or required contract paths disappear.
- The check runs without external LLM, ASR, Redis, or production data dependencies.

## Implementation state
Complete for this feature slice. QA/Security passed the OpenAPI implementation and focused gate.

## Decisions
- Use FastAPI's generated schema rather than maintaining a duplicate static specification.
- Verify documentation through `TestClient` against the application object.
- Keep documentation routes at FastAPI defaults for local discoverability.
- Do not include secrets or meeting content in the schema or tests.

## Files changed
- `backend/app/main.py`
- `backend/tests/test_openapi_contract.py`
- `.github/workflows/openapi-contract.yml`
- `docs/features/openapi-contract-and-qa-gate.md`

## Validation
- `..\\.venv\\Scripts\\python.exe -m pytest -q tests/test_openapi_contract.py` from `backend`: passed, 1 test; two existing Starlette/httpx deprecation warnings remain.
- The focused test verifies HTTP 200 responses from `/openapi.json`, `/docs`, `/redoc`, and `/api/health`.
- The focused test verifies OpenAPI metadata, critical paths, and every schema-visible `APIRoute` registered on the application.
- `.github/workflows/openapi-contract.yml` runs the contract test on every push and pull request.
- Full repository QA remains separate: existing Ruff findings and global coverage debt are outside this feature slice.
- Independent QA/Security review: `PASS` for this feature; no critical, high, or medium findings introduced.

## Risks
- The current project has no committed CI workflow, so continuous execution depends on the repository's pytest/CI entry point.
- Documentation endpoints are currently unauthenticated; production exposure policy remains an operational decision.

## Next action
Configure the workflow as a required merge check through branch protection. Decide before production whether documentation endpoints should remain public or be protected by deployment-level access control.
