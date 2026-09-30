# ADR 0010: Capture Agent Direct Backend PCM

## Status

Accepted.

## Context

The native Capture Agent already connects to the backend, but the frontend opens a second per-track proxy socket and forwards the PCM frames through the meeting audio WebSocket. This adds latency and makes the browser a transport dependency for native capture.

## Decision

The backend owns native PCM ingestion. A `capture_session_id` is associated with one `meeting_id` when the meeting audio session starts. Per-track agent WebSockets publish PCM directly into that meeting's backend audio session. The frontend receives only lifecycle events, levels, metrics and derived transcript events. Browser microphone PCM remains supported as a fallback through the meeting WebSocket.

The PCM contract remains `pcm_s16le`, mono, 16 kHz. Invalid or inactive session associations are rejected, and bounded queues prevent native audio from blocking the agent control channel. Each track owns its frame counter, cursor and instantaneous RMS level. `audio.received` carries the track-local cursor and metrics; the independent per-track levels sockets carry the visual RMS updates. The legacy global sequence remains only for event ordering and reconnection compatibility.

## Consequences

- Native audio no longer depends on the frontend staying connected as a relay.
- Audio persistence, VAD and live transcription have one backend owner.
- Microphone and system failures, cursors and levels can be observed independently.
- The backend must coordinate capture and meeting-session lifecycles.
- Native frames lost during an in-memory queue overflow or backend restart are not replayed by this increment.

## Validation and rollback

Validate direct dual-track integration, invalid-session rejection, frontend absence of the PCM proxy and browser fallback. Roll back by restoring the existing frontend proxy path while retaining the control and level contracts.

## Related records

- `docs/features/capture-agent-direct-backend-pcm.md`
- `docs/adr/0004-audio-capture-and-live-delivery.md`
- `docs/features/per-track-pcm-websockets.md`