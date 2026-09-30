# Post-recording playback controls only
Status: complete
Last updated: 2026-09-26

## Objective

Keep the completed meeting audio dock focused on playback by hiding live waveform tracks after capture ends.

## Scope

- Hide microphone and system waveform tracks outside an active capture.
- Hide capture telemetry and technical audio format metadata outside an active capture.
- Preserve playback controls, duration, transport status, session messages, and persisted audio.
- Keep waveform rendering during active capture.
- No backend, API, persistence, transcript, or provenance changes.

## Acceptance criteria

- Active capture continues to show both waveform tracks.
- After capture stops, neither waveform track nor its playhead is rendered.
- After capture stops, capture telemetry and technical audio metadata are hidden.
- Persisted audio remains playable and playback controls remain available.
- Missing or unavailable audio keeps the existing disabled playback behavior.

## Implementation state

Implemented in the meeting audio dock and covered by a stopped-capture waveform assertion.

## Decisions

- Waveforms are a live capture visualization, not a playback dependency.
- The frontend transport state is the source for deciding whether live waveforms are visible.

## Files changed

- `frontend/src/App.tsx`
- `frontend/tests/e2e/audio-reconnection.spec.ts`

## Validation

- `npm run build` from `frontend/`: passed.
- `git diff --check`: passed.
- Focused Playwright execution was attempted with the frontend server running, but the existing audio-reconnection scenarios remain unstable in transport setup and fail before reliably reaching the post-stop assertion.

## Risks

The live capture state must continue to render waveforms while connecting, recording, and reconnecting.

## Next action

Stabilize the existing audio-reconnection E2E fixture's transport lifecycle before using it as a release gate for this visual state.