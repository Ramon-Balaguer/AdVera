# Global Concept Graph
Status: partial
Last updated: 2026-09-22

## Product Brief

### Problem
The current graph is scoped to individual meetings, which makes recurring concepts, people, organizations, projects and relationships difficult to recognize across meeting history.

### Target User
Users reviewing multiple meetings who need to discover persistent concepts and trace them back to definitive transcript evidence.

### Desired Outcome
A trustworthy, read-only global concept graph that consolidates recurring concepts conservatively and preserves provenance for every visible node and relationship.

### Smallest Useful Increment
Extract concept and relationship candidates from definitive transcripts, persist a conservative global graph with provenance, run a complete historical backfill, and expose a read-only Cytoscape.js view with animated loading.

## Scope

### In Scope
- Ollama extraction of concept and relationship candidates from definitive transcripts.
- Hybrid identity resolution using normalization, aliases and conservative semantic similarity.
- Persistent global concepts and cross-meeting relationships.
- Provenance for meetings, transcript segments, hashes, model metadata and resolution decisions.
- Complete backfill of eligible historical definitive transcripts.
- Read-only API and Cytoscape.js visualization with animated loading.

### Out of Scope
- Provisional or live transcript data.
- Real-time graph updates.
- User editing, merging, deleting or creating graph entities.
- Unsupported conclusions or stored chain-of-thought.
- Advanced graph analytics or conversational querying.

## Acceptance Criteria

- A user can view concepts consolidated across more than one meeting.
- Equivalent concepts are merged only when configured resolution rules provide sufficient confidence.
- Ambiguous concepts remain separate or explicitly unresolved.
- Every visible node and relationship can be traced to definitive transcript evidence.
- The graph is read-only and does not present mutation controls.
- Loading, empty, partial, ready and failure states are explicit.
- Historical backfill is idempotent and does not destroy evidence from other meetings when one meeting is reprocessed.
- No graph data is created from provisional transcript data.

## States and Failure Behavior

- Loading: show graph loading/layout progress.
- Empty: explain when no eligible concepts exist.
- Partial: show available graph data and identify incomplete processing.
- Failure: preserve source transcripts, record job failure metadata and provide retry behavior without fabricated graph content.
- Ambiguous resolution: keep candidates separate and retain the resolution reason.

## Data and Provenance Constraints

- Definitive transcripts are the only extraction source.
- Store structured outputs, provenance, hashes, provider/model metadata, prompt/configuration versions and resolution decisions; never store chain-of-thought.
- Preserve evidence links for concepts and relationships across meetings.
- Favor false negatives over unsupported identity merges.
- Apply existing access and privacy rules to graph data and evidence.

## Implementation State

- Product brief recorded.
- Brain concept and relationship contract slice implemented and validated.
- Canonical resolver, additive schema, worker persistence, conceptual API and Cytoscape renderer implemented.
- Historical memory projection completed with 32 concepts, 17 relationships and 31 mentions; no failed memory jobs remain.
- One active prompt version and an explicit full rebuild trigger are implemented; semantic similarity resolution, richer API filters and QA review remain pending.

The extraction prompt uses one active version, `brain-extraction-current`. Use `--rebuild` to regenerate completed historical jobs explicitly.

## Decisions

- The conceptual graph replaces the current meeting-item graph.
- Decisions, actions and risks are retained as evidence-backed facts/metadata rather than primary graph nodes.
- Identity resolution is hybrid and conservative.
- The first frontend release is read-only and animates a loaded graph; it does not stream indexing in real time.
- Existing memory tables remain during migration until the new graph is backfilled and validated.

## Files Changed

- `docs/features/concept-graph.md`
- `backend/app/contracts.py`
- `backend/app/brain.py`
- `backend/tests/test_brain.py`
- `backend/app/concept_resolver.py`
- `backend/app/memory_contracts.py`
- `backend/app/memory_graph.py`
- `backend/app/models.py`
- `backend/app/memory_worker.py`
- `backend/app/brain_jobs.py`
- `backend/app/config.py`
- `backend/app/backfill_memory.py`
- `backend/app/memory_api.py`
- `backend/migrations/versions/0010_global_concept_graph.py`
- `backend/tests/test_memory_intelligence.py`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/features/brain/ConceptGraph.tsx`
- `frontend/src/features/brain/BrainPage.tsx`
- `frontend/src/features/brain/brainApi.ts`
- `frontend/src/features/brain/brainTypes.ts`

## Validation

- `python -m pytest backend/tests/test_brain.py backend/tests/test_memory_contracts.py -q` — 10 passed.
- `python -m pytest backend/tests -q` — 157 passed, 3 warnings.
- `python -m pytest backend/tests/test_memory_backend.py backend/tests/test_memory_intelligence.py -q` — 22 passed.
- `python -m pytest backend/tests/test_brain.py backend/tests/test_backfill_memory.py backend/tests/test_brain_worker.py -q` — 15 passed.
- `python -m pytest backend/tests -q` — 158 passed, 3 warnings.
- `python -m app.backfill_memory --help` — confirms `--rebuild`.
- `npm run build` from `frontend/` — passed; Vite emitted a chunk-size warning.
- `python -m pytest backend/tests/test_memory_intelligence.py backend/tests/test_memory_backend.py backend/tests/test_backfill_memory.py -q` — 27 passed.
- `GET /api/memory/concept-graph` — returned 32 nodes and 17 relationships.
- `npm run test:e2e -- tests/e2e/brain.spec.ts --workers=1` — 9 passed, including Cytoscape pixel rendering, filtering, keyboard selection and empty/indexing states.
- Pylance diagnostics checked for the changed Python files — no errors.

## Risks

- Incorrect identity merges can damage trust in the graph.
- Historical backfill must remain resumable and idempotent.
- Large graphs require limits, filtering and progressive expansion.
- Transcript evidence is sensitive and must not leak through logs or unauthorized responses.
- Concept relationship endpoints must use the same accent-insensitive normalization as canonical concept keys.

## Next Action

Complete API filtering and independent QA/security review before release; the core graph, backfill and Brain E2E slice is now validated.
