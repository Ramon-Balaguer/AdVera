# Feature: Tray local traffic diagnostics
Status: complete
Last updated: 2026-09-19

## Problem and target user

The capture agent tray shows only a general status, so a user cannot tell whether microphone and system audio are actually being sent during a recording.

## Desired outcome

A local-only diagnostic window shows live traffic for each track without sending telemetry to the backend or exposing audio or meeting content.

## Smallest useful increment

Add a `Diagnostico de trafico` tray action that opens a Tkinter window with connection state, session state, frames, bytes, last activity and sanitized errors for `microphone` and `system`.

## Scope

- In-memory thread-safe diagnostics shared by the remote transport and tray.
- Live Tkinter view refreshed while open.
- Separate microphone/system counters.
- Connection, session and stale-state indicators.
- No telemetry endpoint, persistence or outbound diagnostics messages.
- No persistence, audio preview or recording controls.

## Acceptance criteria

- The tray opens and closes the diagnostic window without stopping capture or transmission.
- Connection and session states update from the remote transport.
- Microphone and system frames and bytes are counted independently after successful sends.
- Last activity is visible per track and freezes when disconnected.
- Errors are sanitized and never expose audio, tokens or private URLs.
- A new session resets the previous session counters.
- The window remains usable while the backend is disconnected or reconnecting.

## States and failure behavior

The view supports disconnected, connecting, connected, reconnecting, recording and stopped states. Missing tracks show no activity rather than misleading counters. Closing the view leaves the agent running.

## Data and provenance constraints

Telemetry is process-local and ephemeral. It stores only operational counters, timestamps, technical session identifiers and sanitized error codes. It never stores PCM, levels, transcripts or meeting content.

## Decisions

- Counters reset at each `capture.start`.
- Bytes count only after the WebSocket accepts the frame send.
- Tkinter runs in a dedicated UI thread so pystray and the remote asyncio loop remain responsive.

## Implementation state

Completed: the tray opens a local Tkinter diagnostic window, and the remote transport updates thread-safe per-track counters after successful sends. No diagnostic data is sent to the backend.

## Files changed

- `agent/agent/stats.py`
- `agent/agent/stats_window.py`
- `agent/agent/remote.py`
- `agent/agent/tray.py`
- `agent/tests/test_stats.py`
- `agent/tests/test_tray.py`
- `docs/features/tray-send-statistics.md`

## Validation

- Agent suite: 20 passed.
- Static diagnostics: no errors in changed implementation files.
- Metrics are local-only and are updated after successful WebSocket sends.

## Risks and next action

Tkinter behavior should be smoke-tested on Windows with the resident tray. The first version does not persist metrics or provide channel-level replay after reconnect.
