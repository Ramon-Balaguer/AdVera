# Feature: Rebuild visual identity (trial branch)
Status: in progress
Last updated: 2026-10-02

## Objective

Try the visual identity in `docs/design` on the running app, on the branch `design/visual-identity`, so the operator can decide whether to keep it before it reaches `main`.

## Scope

In scope:
- Design tokens of `docs/design/advera_visual_identity/DESIGN.md`: canvas and surface layers, hairline borders, the indigo, cyan and violet accents and the status colours, 4/8 px radii, focus glow; dark only.
- Geist as the typeface, bundled with the app (`@fontsource-variable/geist`), no request to Google Fonts.
- The AdVera logo (`docs/design/advera_logo`) in the navigation and as the favicon.
- A left navigation dock (240 px) instead of the top bar; a single top row on narrow screens.
- The meeting page in two columns on wide screens (≥ 1280 px): the transcript on the left; Brain, speakers and notes on the right, sticky. Transcript segments, panels, tables, badges, citations and inputs styled as in the mock-ups.

Out of scope: what the mock-ups show but the app does not do (GPU telemetry, confidence per segment, ⌘K search, layer toggles, exports, merkle hashes); no new behaviour.

## Acceptance criteria

1. Every page uses the design's surfaces, type and accents; nothing loads from the internet.
2. The meeting page shows the transcript and the analysis side by side on a wide screen.
3. No behaviour changes: the end-to-end tests pass unchanged except where they relied on page order.

## Implementation state

Applied on the branch; not merged. Decision pending from the operator.

## Decisions

The theme is one stylesheet (`frontend/src/theme.css`) loaded after `styles.css`, so dropping the branch, or the file, returns to the previous look.

## Files changed

- `frontend/src/theme.css`, `frontend/src/Logo.tsx`, `frontend/public/favicon.svg` (new)
- `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/index.html`, `frontend/src/features/meeting/MeetingPage.tsx`, `frontend/package.json`
- `frontend/tests/e2e/notes-speakers.spec.ts` (the notes "Guardar" button is found inside its panel)

## Validation

- `npm run build`; Playwright 48 passed.
- Checked on screen: meeting, meeting list and Memory pages.

## Risks

- Dark only: the app no longer follows a light system theme.

## Next action

Operator decision: merge the branch into `main` or drop it.
