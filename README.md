# AdVera

**A self-hosted, AI-first meeting manager.** AdVera records or imports your meetings, transcribes
them in Catalan, Spanish and English, tells who is speaking, writes a summary of each meeting and
keeps everything in the **Brain**: a searchable memory of all your meetings in which every
answer, decision and action links back to the exact second of audio that supports it.

Your audio, transcripts and notes stay on your own machines. The only thing that leaves the
application is the text sent to the language-model server **you** choose.

> The definitive transcript is the source of truth; the audio is its origin.

## What it does

- **Capture.** Record from the browser microphone, or from the Windows desktop agent, which records the
  microphone and the system sound as separate tracks. Or import an existing audio or video file.
- **Transcription.** Whisper (faster-whisper / WhisperX) with language detection per chunk and speaker
  diarization (ECAPA). Speakers can be named as people, and the names are used everywhere.
- **Meeting summary.** A language model extracts the summary, decisions, actions, open questions,
  risks, topics, concepts and their relationships, each one with citations to the transcript.
  Ollama or any OpenAI-compatible server (llama.cpp, llama-swap, vLLM...), chosen in Settings.
- **Notes.** A Markdown editor per meeting, with `@` references to other meetings and moments.
  Notes are citable like the transcript.
- **Brain.** Cited search across all meetings (hybrid full-text and vector search with BGE-M3),
  an interactive concept graph, the timeline of any concept or tag, and the decisions, actions,
  questions and risks of all meetings in one place. Each meeting has a Brain tab that shows how it
  connects to the rest.
- **System page.** Whether each worker is up, the state of the queues and the latest summaries and
  searches.
- **Interface** in English, Spanish and Catalan, with a first-start wizard that sets the language
  and the model server.

## How it works

```text
browser / desktop agent ──► API (FastAPI) ──► PostgreSQL + pgvector   (state, transcripts, Brain)
                                 │
                                 └──► Redis Streams ──► workers
                                                         ├─ transcription  (ASR + diarization)
                                                         ├─ summary        (language model)
                                                         └─ brain          (index, search, graph)
```

Redis only carries job ids; PostgreSQL holds the state of every job, with leases, retries and
reconciliation, so a crash or an outage never loses work. The frontend is React + Vite.
Details: [meeting processing flow](docs/meeting-processing-flow.md) and
[Redis contract](docs/redis.md).

## Quick start

Requirements: Docker with Compose v2. For local checks also Python 3.12+ and Node 24+. A GPU is
recommended for transcription (NVIDIA override included); everything also runs on CPU, slower.

```bash
# PostgreSQL + pgvector, Redis, migrations, API, three workers and the frontend
docker compose -f docker/compose.dev.yml up -d --build --wait

# With an NVIDIA GPU (CUDA transcription and embeddings)
docker compose -f docker/compose.dev.yml -f docker/compose.nvidia.yml up -d --build --wait
```

Open <http://localhost:5173>. The first time, a short wizard asks for the language, the model
server (Ollama or OpenAI-compatible) and the model; you can change all of it later in Settings.
The API listens on port 8000. If a port is taken, set `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`,
`API_HOST_PORT` or `FRONTEND_HOST_PORT`.

AdVera has no authentication yet (single user, local network): do not expose it to the internet
([ADR 0015](docs/adr/0015-authentication-deferred-single-user.md)).

### Configuration

Defaults live in environment variables ([`.env.example`](.env.example)); the model server, model and
language chosen in Settings are stored in `RUNTIME_SETTINGS_PATH` and shared by the API and the
workers. ASR models, diarization, embeddings and queue names are documented there.

### Backend without Docker

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e "backend[dev]"
cd backend && ../.venv/Scripts/python -m alembic upgrade head   # Alembic owns the schema
../.venv/Scripts/python -m uvicorn app.main:app --reload
```

## Desktop capture agent (Windows)

```bash
.venv/Scripts/python -m pip install -e agent
.venv/Scripts/python -m advera_agent --probe                                   # microphone / system availability
.venv/Scripts/python -m advera_agent --backend-url http://localhost:8000       # run in the console
.venv/Scripts/python -m advera_agent --tray --backend-url http://localhost:8000
.venv/Scripts/python -m advera_agent --configure                               # save URL + current-user autostart
```

The console script `advera-agent` is equivalent to `python -m advera_agent`. The agent connects
outbound to the backend and records the microphone and the system playback as independent
tracks; the browser microphone is the fallback.

## Tests and checks

```bash
cd backend && ../.venv/Scripts/python -m ruff check . && ../.venv/Scripts/python -m pytest --cov=app   # fails under 90%
cd agent && ../.venv/Scripts/python -m pytest
cd frontend && npm run build && npm run test:e2e
python scripts/check_docs.py
```

Integration tests use a real PostgreSQL and Redis: set `TEST_DATABASE_URL` and `TEST_REDIS_URL`
(see `backend/tests/integration/conftest.py`). To try the whole pipeline with synthetic Catalan,
Spanish and English audio (no real data):

```bash
python scripts/make_smoke_audio.py            # Piper (ca) + Windows SAPI (es, en) into data/smoke/
python scripts/asr_smoke.py --speakers        # through the running stack
```

## Documentation

This repository is a rebuild driven exclusively by [`docs/`](docs/). Where documents disagree, the
order of precedence is: ADRs, then the meeting processing flow, then the Redis contract, then the
feature records, then the plan and the spec.

- [Product and architecture spec](docs/meeting_manager_project_spec.md)
- [Architecture Decision Records](docs/adr/README.md): the decisions that win over every other document
- [Meeting processing flow](docs/meeting-processing-flow.md) and [Redis Streams contract](docs/redis.md)
- [Feature records](docs/features/README.md): one per increment. Records prefixed `rebuild-` belong to
  this rebuild; the rest are the historical as-built system
- [Agent workflow](docs/agent-workflow.md) and the role files in `.github/agents/`
