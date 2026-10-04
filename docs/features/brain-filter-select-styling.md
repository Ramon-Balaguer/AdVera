# Brain Filter Select Styling
Status: partial
Last updated: 2026-09-22

## Objective

Apply the existing Brain form-control styling to the status selector and entity-type checkboxes.

## Product brief

- **Problem:** The status selector and entity-type checkboxes render with browser-default typography, spacing, and appearance instead of matching the surrounding Brain controls.
- **Target user:** AdVera users filtering corporate brain and graph data.
- **Desired outcome:** Brain filters are readable and visually consistent with the page.
- **Smallest useful increment:** Share the existing filter control styles with Brain `select` elements and replace the checkbox UA styling.

## Scope

- **In scope:** Brain status selector and entity-type checkbox typography, spacing, colors, border, checked, and focus states.
- **Out of scope:** Filter values, query behavior, APIs, persistence, and data provenance.

## Acceptance criteria

- The status selector uses the inherited application font and Brain control styling.
- The graph type selector remains visually consistent with the status selector.
- Entity-type checkboxes have a stable custom size and visible checked state.
- Focus remains visibly distinguishable.
- Existing filter behavior and mobile layout remain unchanged.

## States and failures

- The empty/default option remains selected and readable.
- Keyboard focus remains visible.
- Query and graph loading/error states are unchanged.

## Data and provenance constraints

Presentation-only; no data, API contract, transcript, or provenance changes.

## Implementation state

Delivered.

## Decisions and assumptions

- Reuse the existing shared Brain control rule instead of introducing a new component or dependency.

## Files changed

- `frontend/src/styles.css`
- `frontend/tests/e2e/brain.spec.ts`

## Validation

- Frontend build and focused Brain E2E test.

## Risks

Native date input behavior is intentionally unchanged.

## Next action

Keep selector styling covered when Brain controls are changed.
