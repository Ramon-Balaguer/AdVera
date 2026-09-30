# Brain Session Tabs Without Horizontal Scroll
Status: partial
Last updated: 2026-09-22

## Objective
Remove horizontal scrolling from the Brain session panel tabs and keep the full `Resumen` content visible above them.

## Product brief
- **Problem:** At narrow widths, the six categories exceed the available width and the bar shows horizontal scrolling.
- **Target user:** A person reviewing a meeting and consulting its intelligence results.
- **Desired outcome:** The summary remains available for reference while the user explores the other categories through a clear horizontal tab strip without lateral scrolling.
- **Smallest useful increment:** Render the full `Resumen` content above horizontal tabs with persistent labels and an underline for the active category.

## Scope
- **In scope:** Tab layout in the Brain panel on the meeting page; responsive visual behavior.
- **Out of scope:** Changing categories, data, API, intelligence states, or the content of each result.

## Acceptance criteria
- The full `Resumen` content remains visible above the category tabs.
- There is no horizontal scrolling in the category bar.
- Decisiones, Temas, Acciones, Preguntas, and Riesgos remain selectable.
- The selected category retains its selected style and displays its corresponding content below the tabs.
- Category labels are always visible; the selected category has a clear underline active state.
- `Temas` is the first navigable category tab.
- The brain results scrollbar uses the same rounded, thin visual treatment as the transcript scrollbar.
- The frontend compiles successfully.

## States and failures
- The current active selection is preserved.
- The panel's empty, loading, error, and retry states remain unchanged.
- At reduced widths, labels may occupy multiple lines without overflowing.

## Data and provenance constraints
There are no changes to data, contracts, persistence, provenance, or transcript.

## Dependencies and constraints
- Preserve the existing React/TypeScript and CSS patterns.
- Do not add dependencies.
- Validate with the frontend build.

## Assumptions and open questions
- `Resumen` is reference content, not one of the navigable category tabs.
- The horizontal tab strip must remain usable in the available panel width without horizontal scrolling.
- There are no open questions for this increment.

## Implementation state
Delivered.

## Next action
Keep the English feature-record convention for future Product Owner briefs and feature records.
