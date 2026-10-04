# AdVera

Self-hosted, AI-first meeting manager. The definitive transcript is the source of truth; audio is the origin.

This repository is a rebuild driven exclusively by [`docs/`](docs/). Start with:

- [Product and architecture spec](docs/meeting_manager_project_spec.md)
- [Architecture Decision Records](docs/adr/README.md) (they win over every other document)
- [Meeting processing flow](docs/meeting-processing-flow.md)
- [Redis Streams contract](docs/redis.md)
- [Agent workflow](docs/agent-workflow.md) and the role files in `.github/agents/`
- [Feature records](docs/features/README.md). Records prefixed `rebuild-` belong to this rebuild; the rest are the historical as-built system.

## Local development

Requirements: Python 3.12+, Node 24+, Docker with Compose v2.

```bash
# Full stack (PostgreSQL + pgvector, Redis, migrations, API, frontend)
docker compose -f docker/compose.dev.yml up -d --build --wait

# Host ports are configurable when the defaults are taken:
# POSTGRES_HOST_PORT, REDIS_HOST_PORT, API_HOST_PORT, FRONTEND_HOST_PORT
```

Backend only:

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e "backend[dev]"
cd backend && ../.venv/Scripts/python -m alembic upgrade head   # Alembic owns the schema
../.venv/Scripts/python -m uvicorn app.main:app --reload
```

## Desktop Capture Agent (Windows)

```bash
.venv/Scripts/python -m pip install -e agent
.venv/Scripts/python -m advera_agent --probe                                   # microphone / system availability
.venv/Scripts/python -m advera_agent --backend-url http://localhost:18000      # run in the console
.venv/Scripts/python -m advera_agent --tray --backend-url http://localhost:18000
.venv/Scripts/python -m advera_agent --configure                               # save URL + current-user autostart
```

The console script `advera-agent` is equivalent to `python -m advera_agent`. The agent connects
outbound to the backend and records the microphone and the system playback as independent
tracks; the browser microphone is the fallback.

## Smoke tests (synthetic Catalan, Spanish and English audio)

```bash
python scripts/make_smoke_audio.py            # Piper (ca) + Windows SAPI (es, en) into data/smoke/
python scripts/asr_smoke.py --speakers        # through the running stack
```

## Checks

```bash
cd backend && ../.venv/Scripts/python -m ruff check . && ../.venv/Scripts/python -m pytest
cd agent && ../.venv/Scripts/python -m pytest
cd frontend && npm run build && npm run test:e2e
python scripts/check_docs.py
```
