# Feature: English page names
Status: complete
Last updated: 2026-09-21

## Problem and target user
The frontend previously exposed the Summary page with a Spanish route and Spanish navigation labels. AdVera users need page names and routes to be consistently English.

## Desired outcome
Users can identify and open the page as `Summary` at `/summary`, with English page names in the primary navigation.

## Scope
Rename the canonical Summary route and page-facing navigation labels. Preserve internal feature names, API contracts, meeting content, and the existing Spanish UI copy outside page naming.

## Acceptance criteria
- The primary navigation exposes the page as `Summary`.
- Selecting it navigates to `/summary`.
- Direct navigation to `/summary` loads the existing Summary and Brain page.
- Other primary navigation page names are in English.
- Existing Summary, Brain, transcript, and evidence behavior remains unchanged.

## States and failure behavior
Existing Summary loading, empty, error, query, graph, timeline, and evidence states remain unchanged. The removed legacy route is no longer supported.

## Data and provenance constraints
No backend, database, transcript, provenance, or API changes are required.

## Dependencies and assumptions
The Summary source now lives under `features/summary`; `/api/brain` remains unchanged. This increment does not translate all controls, status messages, prompts, or generated meeting content.

## Implementation record
The canonical Summary route is `/summary`. Primary navigation page names are now English, the page heading is `Summary & Brain`, and the feature source, API wrapper, types, CSS classes, and test are named `summary`. Brain API contracts remain unchanged.

## Validation
`npm run build` passed. The focused Playwright suite `tests/e2e/summary.spec.ts` passed with 8 tests.

## Risks and open questions
Existing bookmarks using `/cerebro` are intentionally unsupported. Full UI localization is a separate product decision.

## Next action
No follow-up is required for this naming slice. Full UI localization remains a separate product decision.
