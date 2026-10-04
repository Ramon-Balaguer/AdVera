# Feature: Rebuild bootstrap and governance
Status: partial
Last updated: 2026-09-30

## Objective

Start the AdVera rebuild from an empty repository with a runnable skeleton, the governance artifacts that `docs/agent-workflow.md` assumes, and a documentation checker, without any domain logic. This is increment 0 of the rebuild plan approved in Phase 0.

## Scope

In scope:
- git repository, root `README.md`, `.gitignore` and `.env.example` aligned with Compose;
- the FastAPI skeleton with `GET /api/health`, Alembic as sole schema owner, the pgvector extension migration, and the OpenAPI contract test;
- the React/Vite/TypeScript skeleton with TanStack Query, React Router and Zod installed, plus the API health gate;
- `docker/compose.dev.yml` with PostgreSQL 16 + pgvector, Redis, a one-shot migration service, the API and the frontend;
- `scripts/check_docs.py`, CI workflow, and the nine role files in `.github/agents/`;
- ADR 0015, which records the product decision to defer authentication, and marking ADR 0006 as partially superseded by ADR 0008.

Out of scope: meetings, audio, transcription, workers, Summary, Brain and authentication code. The transcription worker service is added with increment 1, when its module exists.

## Acceptance criteria

1. `GET /api/health` returns `200 {"status":"ok"}`, including through the Vite proxy.
2. API startup checks database connectivity and emits no DDL.
3. `alembic upgrade head` → `downgrade base` → `upgrade head` succeeds on PostgreSQL 16 + pgvector.
4. The frontend stays blocked until `/api/health` succeeds and retries every five seconds.
5. `/openapi.json`, `/docs` and `/redoc` are published and every registered route is in the schema.
6. `docker compose -f docker/compose.dev.yml up --wait` brings every service to healthy or completed.
7. `python scripts/check_docs.py` reports zero errors.

## Implementation state

All acceptance criteria are met locally. The feature stays `partial` until two things happen: an independent QA/Security review, and a first run of the CI workflow on a remote. The repository has no remote yet.

Documentation findings made while building the checker:
- The ADR index shortened four statuses (0009, 0011, 0012, 0013) even though its own rule says to reproduce the `## Status` heading verbatim. The index was corrected to the literal heading text.
- `docs/redis.md` links to backend modules that the rebuild has not produced yet. The checker reports these as warnings. `--strict-code-links` turns them into errors and should become the default once increment 8 lands.

## Decisions

- Documentation precedence and the Phase 0 decision table are recorded in the approved plan. The binding outcomes are:
  - WhisperX is the default for every ASR role and MOSS is opt-in (ADR 0007).
  - `transcript.json` is the transcript store.
  - Jobs are four tables.
  - Summary results are a JSON document.
  - The concept graph is the only graph.
  - Diarization labels are per track (ADR 0005).
  - Provisional transcript data is presentation-only.
  - The definitive path is built before the live pipeline.
- `.env.example` and Compose share ASR defaults, fixing the drift the baseline reported. No ASR language variable exists (ADR 0014).
- Following `local-startup-database-readiness`, Compose health checks are the readiness source of truth. `/api/health` reports API liveness only.
- Host ports are configurable because another stack may already occupy 5432, 6379, 8000 and 5173 on a development machine.
- Playwright runs on a dedicated strict port (5190), so E2E never targets another app already on 5173.
- The spec §19 layout lists `backend/requirements.txt`. It is not created: `pyproject.toml` is the single dependency source, to avoid two lists drifting apart.
- Product owner decision (2026-09-30): no authentication for now (ADR 0015, a documented deviation from spec §21). Meeting reprocessing is out of scope for now, including the one-off forced language. The contradiction between ADR 0014 ("no language override in any flow") and `forced-reprocess-language.md` stays open and must be settled by an ADR if reprocessing comes back into scope. The ADR 0006 status note is kept only as documentation accuracy; no reprocessing is built.

## Files changed

- `README.md`, `.gitignore`, `.env.example`
- `backend/pyproject.toml`, `backend/Dockerfile`, `backend/alembic.ini`
- `backend/app/{__init__,config,database,models,contracts,main}.py`
- `backend/migrations/{env.py,script.py.mako}`, `backend/migrations/versions/0001_enable_pgvector.py`
- `backend/tests/{conftest,test_health,test_openapi_contract}.py`
- `frontend/{package.json,package-lock.json,tsconfig.json,vite.config.ts,index.html,playwright.config.ts,Dockerfile}`
- `frontend/src/{main.tsx,App.tsx,ApiHealthGate.tsx,styles.css}`, `frontend/tests/e2e/api-health-gate.spec.ts`
- `docker/compose.dev.yml`
- `scripts/check_docs.py`, `.github/workflows/ci.yml`, `.github/agents/*.agent.md` (9 files)
- `docs/adr/0015-authentication-deferred-single-user.md`, `docs/adr/0006-reprocess-transcript-before-summary.md`, `docs/adr/README.md`
- `docs/features/rebuild-bootstrap-and-governance.md`, `docs/features/README.md`

## Validation

- Backend: `pytest` → 4 passed; `ruff check` and `ruff format --check` → clean.
- Frontend: `npm run build` → passed; `npm run test:e2e` → 2 passed.
- Compose: `config --quiet` passed; `up -d --build --wait` → postgres, redis and api healthy, migrate exited 0, frontend started.
- `curl /api/health` on the API and through the frontend proxy → `{"status":"ok"}`.
- PostgreSQL: extension `vector 0.8.6` present; Alembic `downgrade base` removed it and `upgrade head` restored it.
- `python scripts/check_docs.py` → 0 errors; 14 warnings for code links in `docs/redis.md`.

## Risks

- The pinned `^` ranges resolved to very recent majors (Vite 8, TypeScript 7, React 19). The lockfile pins the exact versions.
- The Starlette test client emits a deprecation warning about `httpx`.
- Tests use SQLite only for the no-DDL startup check. PostgreSQL behaviour is validated through Compose and the CI `migrations` job.

## Next action

The Product Owner opens `rebuild-import-definitive-transcript` for increment 1 (import → definitive transcript), starting with Architecture/Data for the `meetings` and `transcription_jobs` schema. There is no authentication; `created_by` stays `NULL`.
