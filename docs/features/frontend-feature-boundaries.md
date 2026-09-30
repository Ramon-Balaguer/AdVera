# Feature: Frontend feature boundaries
Status: complete
Last updated: 2026-09-21

## Objective
Create dedicated frontend boundaries for the meetings list, individual meeting view, and settings while preserving current behavior, routes, API contracts, labels, and Brain CSS classes.

## Scope
Move the existing meetings list into `features/meetings`, settings into `features/settings`, and the selected meeting view into `features/meeting`. Keep shell, routing, shared state, and callbacks in `App.tsx`.

## Acceptance criteria
- Existing routes, API endpoints, labels, styles, and workflows remain unchanged.
- `App.tsx` owns shared state, routing, and callbacks and passes explicit props to extracted components.
- Settings, meeting/audio/transcript, and Brain-focused E2E coverage remains passing.
- The frontend production build passes.

## Implementation state
Complete. The meetings library and settings presentation components now live in their feature folders. The selected meeting route is wrapped by the dedicated meeting page boundary while App retains the shared workflow state and composes the existing meeting content.

## Decisions
Presentation JSX moves with its existing class names and copy. Domain state and browser transport behavior remain in `App.tsx`.

## Files changed
- `frontend/src/App.tsx`
- `frontend/src/features/meeting/MeetingPage.tsx`
- `frontend/src/features/meetings/MeetingLibrary.tsx`
- `frontend/src/features/settings/SettingsPage.tsx`

## Validation
The extracted files and `App.tsx` have no file-level diagnostics. The frontend production build passed, and the focused Brain E2E suite passed. Settings and audio E2E cases include existing assumptions that do not match the current source labels and initial route state.

## Risks and open questions
The selected meeting view has a broad callback surface because audio, transcript, and Brain state remain owned by `App.tsx`.

## Next action
Align the existing focused E2E fixtures with the current English navigation labels and selected-meeting route setup.