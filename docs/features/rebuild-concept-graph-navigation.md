# Feature: Rebuild concept graph navigation
Status: complete
Last updated: 2026-10-01

## Objective

Make the concept graph easier to move around, as the operator asked after using it: a faster wheel zoom, nodes further apart, the whole graph visible on load, and a minimap that shows where the view is while zoomed in.

## Scope

In scope: `frontend/src/features/memory/ConceptGraph.tsx` and the new `minimap.ts`. Wheel sensitivity 3.5 (0.25 before; the operator asked three times for more speed). The cose layout spreads nodes further apart. Unconnected groups, which cose stacked in a single column too tall to fit, are packed in rows shaped like the canvas, and the whole graph is fitted; a graph laid out while hidden is fitted when it appears. A minimap in the bottom right corner draws every node and edge and outlines the visible area in amber; clicking or dragging on it centres the view there.

Out of scope: editing the graph (it stays read-only), keyboard control of the minimap (the concept list remains the keyboard and screen reader way to select a concept).

## Acceptance criteria

1. The wheel zooms at least twice as fast as the previous setting.
2. On load, every group of concepts is inside the view.
3. The minimap sits in the bottom right corner, follows zoom and pan, and moves the view when used.

## Implementation state

Implemented and deployed.

## Decisions

The minimap is drawn by the app on a small canvas, without a Cytoscape extension, because the known extension is unmaintained; it is decorative for assistive technology (`aria-hidden`).

## Files changed

- `frontend/src/features/memory/ConceptGraph.tsx`, `frontend/src/features/memory/minimap.ts` (new), `frontend/src/styles.css`
- `frontend/tests/e2e/tags-graph.spec.ts`

## Validation

- `npm run build`; Playwright (37 tests), including the minimap's position over the canvas and a click on it.
- Real graph inspected: before the packing, the graph measured about 630 × 4,560 px and only its top was visible.

## Risks

- Sensitivity above the Cytoscape default makes a single wheel notch zoom a lot on some mice and touchpads.

## Next action

None.
