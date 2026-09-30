# Feature: Rebuild transcript that follows playback
Status: complete
Last updated: 2026-09-30

## Objective

While a meeting plays, highlight the transcript segment under the playhead and scroll so it stays in view. Before this change a segment was highlighted only when clicked, and the highlight did not move with the audio.

## Scope

From `transcript-card-review-ui.md` ("The active segment is visually distinguished during playback") and the meeting workspace design ("Autoscroll con audio activo"):

- The synchronized player (`rebuild-synced-multitrack-playback.md`) reports the meeting position after every seek and every 250 ms while playing.
- Every segment that contains the position is highlighted. Tracks overlap, so a microphone and a system segment can both be active. In a silence, the last segment that started stays active.
- The segment chosen explicitly (click, Brain citation, Memory deep link) counts from 1 s before its start, because citation links carry whole seconds (`?at=12` for a segment at 12.4 s).
- When the latest active segment changes, it is scrolled smoothly to the centre.
- A "Seguir la reproducción" toggle (on by default) stops the scrolling so the user can read elsewhere; the highlight keeps moving.

Out of scope: word-level highlighting, and pausing the follow automatically when the user scrolls.

## Acceptance criteria

1. During playback the highlight advances phrase by phrase, and only the phrase under the playhead is active.
2. A seek far down the meeting highlights that phrase and brings it into view.
3. With following off, the highlight moves and the page does not scroll.
4. A Memory citation still highlights the cited segment and positions the audio at the cited second.

## Implementation state

Implemented.

## Files changed

- `frontend/src/features/meeting/{MeetingPage,SyncedPlayer}.tsx`, `frontend/src/styles.css`
- `frontend/tests/e2e/synced-playback.spec.ts`

## Validation

- `npm run build` passes.
- Playwright 15/15. The new test uses 30 one-second phrases on alternating tracks (taller than the viewport) and covers criteria 1–3; `memory.spec.ts` covers criterion 4. That spec first failed on the rounded `?at=12` link, which led to the 1 s rule above.

## Risks

The highlight lags the audio by up to one sync tick (250 ms). Transcripts with thousands of segments are filtered linearly on every tick; this is negligible at the current meeting sizes.

## Next action

None.
