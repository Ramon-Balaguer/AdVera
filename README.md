# AdVera

**Every meeting, verifiable knowledge.**

AdVera is a free and open source (AGPL-3.0), self-hosted, AI-first meeting manager built
around one idea: **everything is recorded, and everything can be checked.** It keeps the audio, the
transcript with who said what and when, your notes, and what the AI concluded from them. Every
summary, decision, action and answer links back to the exact second of audio that supports it.

AdVera records or imports your meetings, transcribes them in around 100 languages, tells who is
speaking and writes a summary of each meeting. The **Brain** keeps all of it in one searchable
memory of every meeting you have had.

Your audio, transcripts and notes stay on your own machines. The only thing that leaves the
application is the text sent to the language-model server **you** choose.

> The definitive transcript is the source of truth; the audio is its origin.

## What is recorded

- **The audio.** Recordings keep their original tracks (microphone and system sound separately);
  an imported file keeps the audio extracted from it.
- **The transcript.** One definitive transcript per meeting, with the speaker, the language and
  the time of every segment. The summary and the Brain are built only from it.
- **Your notes**, which can be cited like the transcript.
- **What the AI did.** Each call to the language model is stored with the prompt version, the
  model and its raw answer, and every item it produced carries citations to segments of the
  transcript; an item without a valid citation is dropped, not shown.
- **What the Brain knows.** Facts, concepts, relationships, tags and people, each tied back to
  the meetings and the seconds they come from.

## What it does

- **Capture.** Record from the browser microphone, or from the Windows desktop agent, which records the
  microphone and the system sound as separate tracks. Or import an existing audio or video file.
- **Transcription.** Whisper (faster-whisper / WhisperX), which covers around 100 languages, with language
  detection per chunk and speaker diarization (ECAPA).
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

## Requirements

**To run it**

| | Minimum | Recommended |
|---|---|---|
| Software | Docker with Compose v2 | the same, plus the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) for GPU |
| Transcription | CPU: works, slow, and the default `small` model makes more mistakes in Catalan | NVIDIA GPU with CUDA: `large-v3` in float16, which is what the GPU override uses |
| Memory | the containers use under 1 GB while idle (measured); the models need more while they work | 16 GB of RAM or more |
| GPU memory | none | on our RTX 3090 (24 GB) the workers use about 5 GB with `large-v3` and the embeddings; the language model runs elsewhere |
| Disk | about 11 GB for the model cache (Whisper, BGE-M3, diarization, PyTorch), plus the container images | an SSD; audio is kept: about 2 GB for our first 70 test meetings, the database 150 MB |
| Network | internet on the first start, to download the models from Hugging Face | a LAN link to the model server |

- **A language model server**, which AdVera does not include: Ollama or any OpenAI-compatible server
  (llama.cpp, llama-swap, vLLM). It must be reachable from the containers (not `localhost` of your
  host), support JSON-schema structured output, and have a large context window: the default prompt
  budget is 131,072 tokens and a 73-minute meeting needs about 56,000. We run a 35B-class model;
  smaller ones have not been evaluated. It can be on another machine: the only thing sent to it
  is the text of your meetings.
- **A browser** to use the application. Recording with the microphone needs a secure context:
  `localhost` or HTTPS.
- **Free ports** 5173 (frontend), 8000 (API), 5432 (PostgreSQL) and 6379 (Redis); the last two are
  bound to the loopback only.
- **The desktop agent** (optional, for recording the system sound) needs Windows and Python 3.11+.

**To develop it**: Python 3.12+, Node 24+, Docker with Compose v2, and a PostgreSQL and a Redis for
the integration tests (the Compose ones are enough).

## Quick start

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

## Open source

AdVera is free and open source software under the [GNU Affero General Public License v3.0](LICENSE):
you may use it, study it, change it and share it, for any purpose, with no account, no telemetry
and no lock-in. If you run a modified version as a service for others, you must offer them its
source code under the same licence. Its dependencies use licences compatible with it (mostly
MIT, BSD and Apache-2.0). Contributions are welcome: see [Contributing](#contributing).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). After cloning, enable the Git hooks once, so a push
runs the quick checks of what it changes (the full suite runs in CI):

```bash
git config core.hooksPath .githooks
```

Security issues: see [SECURITY.md](SECURITY.md).

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
