# Agent workflow

Agents work with least privilege and do not share production credentials.

The executable workspace agents live in `.github/agents/` and are selected by role:

| Agent | File | Owns |
| --- | --- | --- |
| Product Owner | `advera-product-owner.agent.md` | product discovery, questions, scope and acceptance |
| Orchestrator | `advera-orchestrator.agent.md` | scope, sequencing and handoffs |
| Architecture and Data | `advera-architecture-data.agent.md` | contracts, schema, migrations and provenance |
| Backend | `advera-backend.agent.md` | FastAPI, domain services, persistence and workers |
| Frontend | `advera-frontend.agent.md` | React workflows, transcript UI and client state |
| Audio Live | `advera-audio-live.agent.md` | capture, WebSocket, framing and provisional transcript |
| Intelligence | `advera-intelligence.agent.md` | definitive transcript analysis, embeddings and cited retrieval |
| QA and Security | `advera-qa-security.agent.md` | independent tests, review and release gates |
| Operations | `advera-operations.agent.md` | Compose, CI, observability, backups and rollback |

## Roles

Each role below is one executable agent file in `.github/agents/`. There is no role without a file, and no file without a role.

- Product Owner: clarifies the user problem, value, scope, acceptance criteria and product risks before technical planning, and creates a new durable feature-memory file in `docs/features/` for every feature.
- Orchestrator: breaks requests into verifiable tasks and coordinates handoffs.
- Architecture and Data: owns contracts, ADRs, schemas, migrations and indexes.
- Backend: owns FastAPI, domain rules, persistence and the transcription, Summary and Brain workers.
- Frontend: owns React, API state, WebSocket state and user workflows.
- Audio Live: owns capture, framing, sessions, VAD, buffering and provisional transcript.
- Intelligence: owns definitive transcript analysis, LLM extraction, embeddings and cited retrieval.
- QA and Security: owns independent tests, review, release gates, authentication, uploads, secrets and sensitive logging.
- Operations: owns Compose, CI, observability, environments, GPU capacity, backups and rollback.

Roles that earlier drafts listed separately are merged, not dropped. Data sits with Architecture because schema and contract decisions are inseparable. Security sits with QA because both are the independent check on a change. DevOps and SRE are one Operations role because they share the runtime boundary. Full-audio transcription and definitive transcript finalization are not a separate specialist: the Audio Live agent owns the live path and the Backend agent owns the asynchronous definitive worker.

## Feature flow

```text
feature request
        |
        v
Product Owner: questions + Product Brief
        |
        v
Orchestrator: scope + technical sequence
        |
        +--> Architecture/Data: contracts, schema and ADR when needed
        |
        +--> Backend / Frontend / Audio Live / Intelligence: implementation slice
        |             |
        |             +--> unit tests and focused executable check
        |
        +--> QA and Security: independent review and integration tests
        |
        +--> Operations: deployability, observability and rollback check
        |
        v
human approval for critical changes -> staging -> production
```

### Routing rules

- Every new feature starts with Product Owner. No implementation agent starts from an ambiguous request.
- Every feature has its own new Markdown record in `docs/features/`; the Product Owner creates it before planning and completes it after implementation. Existing records are historical and are not reused for other features. The permanent record uses the template in `docs/features/README.md`; the discovery brief below is a separate pre-planning artifact.
- `docs/adr/README.md` is the durable architecture decision index. Architecture/Data owns ADR creation and supersession; Operations owns deployment and recovery decisions that cross the runtime boundary. Feature records must link affected ADRs.
- The first task for an undocumented existing project is a Product Owner retrospective of the implemented features and their current status.
- Product Owner asks only questions that affect user value, scope, acceptance, state, privacy, dependencies or risk.
- Product Owner hands a Product Brief to Orchestrator; Orchestrator turns it into technical handoffs.
- A database or API contract change starts with Architecture/Data, then Backend.
- A user workflow starts with Frontend and Backend when the API is missing.
- Audio capture, buffering or provisional events go to Audio Live. Full-audio definitive transcription is a separate handoff to Backend, which owns the asynchronous transcription worker; the provider itself is a configuration choice, not an agent.
- Knowledge extraction, embeddings or Q&A can start only after a definitive transcript contract exists; route to Intelligence.
- Every implementation handoff returns to QA and Security before release.
- Operations joins changes that affect deployment, queues, GPU resources, backups or recovery.

## Handoff template

```text
Objective:
Acceptance criteria:
Context and contracts:
Files changed:
Decisions and assumptions:
Tests and commands:
Risks and open questions:
Next action:
```

The Product Owner uses the following discovery brief before this technical handoff:

```text
Problem:
Target user:
Desired outcome:
Smallest useful increment:
In scope / Out of scope:
User acceptance criteria:
States and failure behavior:
Data and provenance constraints:
Dependencies and constraints:
Assumptions:
Open questions:
Recommended next agent:
```

The orchestrator records this handoff in the task or pull request. A specialist may not close a critical change without an independent QA/Security result.

## Handoff

Every task handoff records:

1. objective and acceptance criteria;
2. relevant context and contracts;
3. files changed;
4. decisions and assumptions;
5. tests and commands executed;
6. risks and next action.

## Production gates

```text
request -> product owner -> orchestrator -> specialist -> implementation -> tests
        -> QA/security -> staging -> human approval -> production
        -> observability -> rollback if required
```

No agent approves its own critical change. Migrations, authentication, provider changes, sensitive data handling and production deployments require human review. The intelligence agent can only consume definitive transcript data.
