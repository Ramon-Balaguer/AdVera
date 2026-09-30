# Feature: Rebuild live capture waveforms per track
Status: complete
Last updated: 2026-09-30

## Objective

While recording, show one live waveform per captured track so the user can see that each source is actually being captured: the microphone, plus the system playback when the desktop agent records it (`dual-track-playback-live-metrics.md`).

## Scope

- A scrolling canvas waveform per track, holding about 12 s of RMS history with the newest level on the right.
- Browser mode: the microphone track, with an RMS level computed every 100 ms from the captured PCM.
- Agent mode: the microphone and system tracks, from the agent's per-track levels (10 Hz) relayed over `WS /ws/capture-agent/{id}/{track}/levels`.
- Waveforms appear only during active capture and disappear after stop (`post-recording-playback-controls-only.md`).

Out of scope: playback waveforms of stored audio, and a synchronized playhead.

## Acceptance criteria

1. Browser recording shows a drawn `microphone` waveform.
2. Agent recording shows drawn `microphone` and `system` waveforms, next to the per-track byte counters.
3. No waveform remains after the recording stops.
4. The waveforms show only aggregate RMS levels, never PCM or transcript content.

## Implementation state

Implemented.

## Decisions

- Levels are scaled 4x for visibility because speech RMS is small. The display clips at full height.
- The level bars from the previous increment are replaced by the waveforms.

## Files changed

- `frontend/src/features/meeting/LiveWaveform.tsx` (new), `frontend/src/features/meeting/{useMicrophoneCapture.ts,useAgentCapture.ts,CaptureControls.tsx}`, `frontend/src/styles.css`
- `frontend/tests/e2e/{microphone-capture,agent-capture}.spec.ts`

## Validation

The Playwright E2E counts painted canvas pixels. With Chromium's fake microphone the `microphone` waveform is drawn; with mocked agent levels both `microphone` and `system` waveforms are drawn; all are absent after stop. 8/8 E2E pass.

## Risks

Rendering at 10 Hz per track re-renders the capture panel. That is negligible for two tracks, but it should be revisited if more tracks are ever added.

## Next action

None.
