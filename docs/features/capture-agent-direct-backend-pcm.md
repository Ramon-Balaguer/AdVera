# Capture Agent Direct Backend PCM
Status: partial
Last updated: 2026-09-26

## Objective

Move native PCM transport ownership from the frontend to the backend. The Capture Agent sends each track directly to the backend; the frontend remains responsible for control, metrics and presentation events.

## Scope

- Associate `capture_session_id` with the target `meeting_id`.
- Route per-track PCM frames from the Capture Agent into the meeting audio session.
- Remove frontend PCM proxying while preserving browser microphone fallback.
- Preserve existing audio persistence, live VAD/transcription and lifecycle events.
- Make microphone and system track cursors, levels and metrics independent.
- Deliver per-track PCM metrics in `audio.received` and keep visual levels on the independent per-track `levels` sockets.

Out of scope: changing PCM format, ASR providers, definitive transcription or historical audio migration.

## Acceptance criteria

- A native capture session is explicitly associated with one meeting.
- Agent microphone and system PCM frames are persisted by the backend in the matching meeting tracks.
- The frontend does not open the agent PCM proxy or forward native PCM bytes.
- The frontend continues to receive `audio.ready`, `audio.received`, `audio.stopped` and metrics; each `audio.received` includes the track metrics while visual levels arrive independently.
- Unknown or inactive capture sessions cannot write audio into a meeting.
- Existing browser microphone fallback continues to send PCM through the meeting audio WebSocket.
- Tests cover direct dual-track routing, lifecycle rejection and frontend absence of the PCM proxy.

## States and failures

The capture association is active only between `capture.start` and audio session stop. Invalid sessions, tracks, meetings and stale connections are rejected. Queue overflow drops the oldest frame and remains observable through existing metrics; it must not block the control channel.

## Data and provenance

Frames remain `pcm_s16le`, mono, 16 kHz. The backend retains meeting, capture session, track, sequence, byte and frame metrics. Native PCM is never emitted through frontend events or logs.

## Decisions

- The backend owns native PCM ingestion and meeting audio persistence.
- The frontend keeps the meeting WebSocket for lifecycle and derived events.
- Browser capture remains a fallback path during this migration.
- The architecture decision is recorded in ADR 0010.

## Files changed

- `backend/app/capture_agent.py`
- `backend/app/audio.py`
- `frontend/src/App.tsx`
- `backend/tests/integration/test_audio_websocket.py`
- `docs/adr/0010-capture-agent-direct-backend-pcm.md`
- `docs/adr/README.md`
- `docs/meeting-processing-flow.md`

## Validation

- `backend/tests/test_audio.py` and `backend/tests/integration/test_audio_websocket.py`: 10 passed, including independent track cursor and level assertions.
- Frontend source diagnostics: no errors in `frontend/src/App.tsx`.
- Frontend source search: no native PCM proxy references remain in `frontend/src`.
- `npm run build` passed.
- Playwright audio reconnection tests were blocked before the audio flow because the configured backend was unavailable (`ECONNREFUSED` on `/api/settings`).

## Risks

In-memory queues remain process-local; a backend restart requires the existing durable audio-session recovery path. Agent reconnection does not replay frames that were already dropped, so sequence and metrics remain the source of operational diagnosis.

## Next action

Run the frontend E2E suite with the backend available. The global `sequence` remains only for event ordering and reconnect compatibility; `track_sequence` is the independent cursor for each track.