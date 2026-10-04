# Feature: Meeting view frontend feature
Status: in progress
Last updated: 2026-09-21

## Problem and target user
The individual meeting visualization, audio controls, transcript views, evidence links, and session Summary panel are embedded in the application shell.

## Desired outcome
The meeting detail workflow has a dedicated frontend feature boundary without changing its route or behavior.

## Scope
Extract the existing individual meeting view into `frontend/src/features/meeting/`, keeping `/meetings/:meetingId`, audio and transcript contracts, evidence deep links, capture behavior, Summary actions, labels, and styles unchanged.

## Acceptance criteria
- The existing meeting detail route renders through the meeting feature.
- Audio playback/capture, transcript tabs, search, evidence deep links, and Summary actions behave as before.
- Loading, processing, definitive, failed, and unavailable states remain unchanged.
- Existing focused tests and frontend build pass.

## States and failure behavior
Preserve current meeting-not-found, audio, transcript, capture, playback, and Summary status states.

## Data and provenance constraints
The definitive transcript remains the source of truth. No API payloads, provenance, hashes, or transcript states change.

## Dependencies and assumptions
The shell continues to own shared capture state and handlers in the first extraction; the feature receives explicit props.

## Implementation record
Pending extraction and validation.

## Validation
Pending.

## Risks and open questions
The view has substantial coupling to capture and playback state; use a prop-driven boundary before deeper hook relocation.

## Next action
Extract the meeting view and run focused audio, transcript, and evidence validation.
