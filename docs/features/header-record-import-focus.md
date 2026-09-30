# Feature: Header record/import navigation focus
Status: complete
Last updated: 2026-09-26

## Problem and target user

The `+ Grabar / Importar` header button only focused the new-meeting field when the meetings list was already mounted. From an open meeting, the field did not exist, so the click had no visible effect.

## Desired outcome

The button always returns the user to the meetings list and places focus in the meeting name field so pressing Enter submits the existing new-meeting form.

## Smallest useful increment

Navigate to `/meetings` and focus the new-meeting input after the list mounts.

## Scope

- Header record/import button navigation.
- Focus handoff in the meetings library.
- Preserve the existing form submission behavior.

Out of scope: changing meeting creation, recording transport or import APIs.

## Acceptance criteria

- Clicking the header button from an open meeting navigates to the meetings list.
- The new meeting name input receives focus after navigation.
- Pressing Enter uses the existing form submit handler.
- Repeated clicks also request focus reliably.

## States and failure behavior

The focus request waits until the meetings library is ready. Existing loading and error states remain unchanged.

## Data and provenance constraints

No API, persistence or transcript behavior changes.

## Decisions and assumptions

Focus is requested with a monotonically increasing counter so each click is observable by the child component, including clicks made while already on the list. No ADR is required.

## Files changed

- `frontend/src/App.tsx`
- `frontend/src/features/meetings/MeetingLibrary.tsx`
- `docs/features/header-record-import-focus.md`

## Validation

- `npm run build`: passed.

## Risks and open questions

The browser controls focus only after the list is ready; this avoids attempting to focus an input that has not mounted.

## Next action

Verify the interaction manually in the running frontend or through the existing Playwright environment.