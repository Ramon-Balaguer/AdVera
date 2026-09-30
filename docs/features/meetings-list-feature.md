# Feature: Meetings list frontend feature
Status: in progress
Last updated: 2026-09-21

## Problem and target user
The meetings list UI is embedded in the application shell, making the meeting-library workflow difficult to own and test independently.

## Desired outcome
The meetings list has a dedicated frontend feature boundary while users keep the same list, create, open, delete, loading, empty, and error behavior.

## Scope
Extract the existing meetings list component, related types/helpers, and callbacks into `frontend/src/features/meetings/`. Preserve `/meetings`, API contracts, labels, styles, and navigation behavior.

## Acceptance criteria
- The existing meetings list renders through the meetings feature.
- Create, open, and delete actions behave exactly as before.
- Loading, empty, ready, and error states remain unchanged.
- Existing focused tests and frontend build pass.

## States and failure behavior
Preserve current loading, empty, API error, create failure, and delete failure behavior.

## Data and provenance constraints
No API, persistence, transcript, or provenance changes.

## Dependencies and assumptions
The application shell continues to own route selection and shared meeting state. Existing CSS remains global during this extraction.

## Implementation record
Pending extraction and validation.

## Validation
Pending.

## Risks and open questions
The component currently depends on shell callbacks and shared meeting types; keep the first extraction prop-driven.

## Next action
Extract the meetings list and run focused frontend validation.
