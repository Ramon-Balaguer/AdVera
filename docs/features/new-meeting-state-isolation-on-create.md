# Feature: New meeting state isolation on create
Status: in progress
Last updated: 2026-09-26

## Problem
Creating a new meeting can leave meeting-scoped UI data from a previously recorded meeting visible until the browser page is refreshed. This risks cross-meeting transcript, summary, audio, and status leakage.

## Target user and desired outcome
Users recording consecutive meetings should be able to create and open a new meeting and see only that meeting's state, without a manual page refresh.

## Smallest useful increment
Reset all frontend meeting-scoped state and capture resources whenever the active meeting id changes, then verify the create-and-open flow with an E2E regression test.

## Scope
In scope: frontend meeting navigation, meeting-scoped state reset, capture/reconnection cleanup, and regression coverage.

Out of scope: backend contracts, transcription, Summary extraction, brain indexing, and unrelated UX changes.

## Acceptance criteria
- Creating and opening a new meeting does not display transcript or live summary content from the previous meeting.
- Audio metrics, playback position, capture status, progress, search, and meeting-scoped Summary state start from the new meeting's state.
- Active capture and reconnection resources from the previous meeting are stopped when changing meetings.
- No browser refresh is needed.
- The focused frontend build and regression test pass.

## States and failure behavior
The new meeting starts in an idle, empty/unavailable state while its own audio, transcript, and Summary requests resolve. A failed request must not fall back to the previous meeting's data.

## Data and provenance constraints
The definitive transcript remains the source of truth. Provisional transcript and live summaries must never be reused across meeting ids. No backend payload or provenance contract changes.

## Dependencies and constraints
Use the existing React state ownership and Playwright E2E setup. Preserve the current API and route contracts.

## Assumptions and open questions
The leak is caused by meeting-scoped React state surviving `selectedId` changes and by resources continuing across navigation. The same isolation should apply when switching between any two meetings, not only immediately after creation.

## Decisions
Reset state at the `selectedId` ownership boundary and cancel/close resources there. Keep existing per-request cancellation for transcript and Summary loads.

## Files changed
Pending implementation.

## Validation
Pending.

## Risks
Navigating away during an active recording intentionally stops the local capture resources; the backend audio already persisted remains available for the original meeting.

## Next action
Implement the reset and run the focused E2E regression plus frontend build.
