# Feature: Transcript card review UI
Status: complete
Last updated: 2026-09-18

## Objective
Bring the transcript review surface closer to the AdVera workspace reference design without inventing unavailable ASR or intelligence metadata.

## Scope
- Dark, dense transcript cards for provisional and definitive segments.
- Search filtering with explicit query highlighting.
- Clickable timestamps that start synchronized persisted audio from the segment start.
- Stable speaker color, speaker fallback, speaker id and track badges.
- Provisional/live versus definitive/verified state indicators.
- Timestamp-to-audio provenance hint and copyable segment reference.
- Responsive card layout that preserves readable text on mobile.

## Acceptance criteria
- Existing provisional and definitive tabs remain available.
- Cards show timestamp, text, state, speaker fallback and track when present.
- Clicking a timestamp starts audio at that segment when persisted audio exists.
- The active segment is visually distinguished during playback.
- Search filters cards and highlights only the user-entered query.
- Confidence, per-segment language, decisions and tasks are not fabricated because they are not in the current contract.
- Empty, pending and failed transcript states remain intact.

## Decisions
- The visual design uses the existing Geist and Material Symbols setup.
- Speaker colors are deterministic and presentation-only; they are not persisted facts.
- The link action copies a local segment hash reference; it does not claim to create a shareable external URL.
- Intelligence badges remain in the locked Brain panel until structured, provenance-backed outputs exist.

## Files changed
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/features/transcript-card-review-ui.md`

## Validation
- Frontend build passed in the frontend container with `npm run build`.
- Browser snapshot confirmed the redesigned search control and preserved empty-state behavior.
- Segment-card rendering is ready for validation with a persisted transcript containing segments.

## Risks and next action
The current browser meeting has no transcript segments, so visual card rendering was not exercised with live data in this pass. Validate timestamp seeking, active-card highlighting and mobile wrapping with a completed meeting containing provisional and definitive segments.
