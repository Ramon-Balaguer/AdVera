# Feature: Brain tag filter
Status: complete
Last updated: 2026-09-30

## Objective
Allow users to restrict global Brain queries to meetings assigned a matching manual tag.

## Scope
- Add a global tag select to the Brain query controls and query payload.
- Load only tags with active meeting assignments, including their meeting counts.
- Resolve manual tag concept assignments to meeting IDs before transcript evidence retrieval.
- Preserve existing node-type, meeting, date, speaker and language filters.

## Acceptance criteria
- A query with a tag returns evidence only from meetings assigned that tag.
- A non-matching tag returns an empty result without broadening the query.
- Existing filters continue to work, including the `Etiquetas` node-type filter.
- Tag filtering uses manual assignments and does not create intelligence from provisional transcript data.

## Implementation state
Implemented.

## Decisions
- Manual tags remain metadata represented by `BrainConceptAssignment` and `BrainConcept` with `concept_type="tag"`.
- The worker resolves tag filters to meeting IDs and reuses the existing SQL retrieval path.
- When no meetings match, a sentinel meeting ID produces an empty result without changing retrieval contracts.
- No ADR created: this is a query-filter extension within existing ownership and provenance boundaries.

## Files changed
- `backend/app/brain_contracts.py`
- `backend/app/brain_worker.py`
- `backend/tests/test_brain_backend.py`
- `frontend/src/features/brain/BrainPage.tsx`
- `frontend/src/features/brain/brainTypes.ts`

## Validation
- `backend/tests/test_brain_backend.py -k 'manual_tag_filter or query_worker_reports_empty_without_index'`: 2 passed.
- `frontend npm run build`: passed.
- Existing Pylance diagnostics in `brain_worker.py` remain unrelated to this change; the new helper introduces an untyped session diagnostic consistent with nearby worker helpers.

## Risks
- The selector currently supports one tag at a time; multi-tag selection remains future work.
- Full end-to-end worker coverage with persisted assignments is not included in this focused regression.

## Next action
Run the broader backend suite before release and add browser coverage if the Brain query workflow receives E2E coverage.
