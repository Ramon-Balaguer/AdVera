# Feature: Rebuild deletion of several meetings at once
Status: complete
Last updated: 2026-10-01

## Objective

Let the user select several meetings in the meeting list and delete them together, with a confirmation hard enough that it cannot happen by a stray click (operator request: "a sum or something like that").

## Scope

In scope: a checkbox per row and one in the header (every visible meeting; indeterminate when some are selected); a bar with the number selected, "Borrar seleccionadas" and "Quitar selección"; a confirmation that states what is lost (audio, transcript, memory) and enables "Confirmar borrado" only when a random sum of two two-digit numbers is answered correctly. Meetings are deleted one by one through the existing `DELETE /api/meetings/{id}`, so every rule of a single deletion applies (`409 MEETING_BUSY` for a live session; derived Memory data removed). Progress is shown; meetings that could not be deleted are listed with the reason and stay selected. Changing the tag filter clears the selection, so nothing hidden is deleted.

Out of scope: a bulk endpoint, undo.

## Acceptance criteria

1. Several meetings can be selected, individually or all visible ones at once.
2. Deletion needs the sum answered correctly.
3. A meeting that cannot be deleted is reported and stays selected; the others are deleted.
4. Only visible meetings can be deleted.

## Implementation state

Implemented and deployed.

## Decisions

No new endpoint: one request per meeting keeps a single deletion path and its protections.

## Files changed

- `frontend/src/features/meetings/MeetingsPage.tsx`, `frontend/src/styles.css`
- `frontend/tests/e2e/tags-graph.spec.ts`

## Validation

- E2E (mocked): select two meetings, a wrong sum keeps the button disabled, the right one deletes; a busy meeting is reported and stays selected; the header box selects every visible meeting.

## Risks

- None known.

## Next action

None.
