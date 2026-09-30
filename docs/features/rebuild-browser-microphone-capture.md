# Feature: Rebuild browser microphone capture
Status: partial
Last updated: 2026-09-30

## Objective

Record the browser microphone into the meeting's independent `microphone` track (`original.pcm`) over the meeting WebSocket. Stopping enters the same durable definitive transcription job as media import (ADR 0004, 0005, 0008). This is the fallback path when no desktop agent is connected (ADR 0010).

## Scope

In scope:
- `WS /ws/meetings/{meeting_id}/audio` commands:
  - `start`, answered by `audio.ready` with `session_id`, `next_sequence` and the PCM format;
  - binary PCM frames, each acknowledged by `audio.received` with the global and per-track sequence and per-track metrics;
  - `stop`, answered by `audio.stopped` and then `transcript.queued` or `transcript.failed`;
  - `audio.error` codes for protocol errors.
- A backend-owned `AudioSessionManager`:
  - one active session per meeting, per-track cursors, and an atomic `audio_session.json` manifest;
  - a disconnect leaves the session recoverable;
  - `resume` appends without truncating and rejects stale cursors (`audio-session-reconnection.md`);
  - the manifest allows resuming after a process restart.
- `GET /api/meetings/{id}/audio-metrics` for recovery (spec §20).
- Frontend:
  - `AudioWorklet` capture, downsampled to 16 kHz PCM16 in 4096-sample frames;
  - level meter and backend-confirmed duration;
  - reconnection with bounded backoff, a queue of 64 frames and `resume` (`frontend-audio-reconnection.md`);
  - "Continuar" and "Finalizar" for a recording interrupted by a lost tab or a restart.
- Send-after-close safety on every event (`audio-websocket-close-safety.md`).

Out of scope: the live transcript (next increment), the capture lock after Brain and Memory, and multi-client recording.

## Acceptance criteria

1. Start sets the meeting to `recording`. Frames are acknowledged in order and persisted to `original.pcm`.
2. Stop persists the track, commits a `TranscriptionJob`, publishes its id, and returns `transcript.queued` without waiting for ASR.
3. Frames before `start`, frames not aligned to 16-bit samples and invalid commands are rejected without touching stored audio.
4. A disconnect keeps the session recoverable. `resume` continues the sequence and appends. Stale or unknown cursors are rejected.
5. Stopping with no audio queues no job and returns the meeting to `scheduled`.
6. Start is rejected while a transcription job is active.
7. The captured microphone reaches the definitive transcript with `track = "microphone"`.
8. In the UI, "Importar" is disabled while recording, and a dropped socket resumes with `session_id` and the client cursor.

## Implementation state

Implemented. Kept `partial` until independent QA/Security review and a manual check with a real browser microphone.

## Decisions

- Browser frames are raw PCM. The server assigns sequences, and the client cursor is the number of frames it has sent, so a lower cursor on resume means duplicates.
- A new session truncates the meeting's tracks. The previous definitive transcript stays until a new valid one replaces it (ADR 0008).
- Progress after stop is delivered through the durable HTTP status endpoint (polling), not the audio socket. ADR 0008 allows either.

## Files changed

- `backend/app/audio.py`, `backend/app/audio_sessions.py` (new), `backend/app/transcription_jobs.py` (`queue_meeting_transcription`, shared with import), `backend/app/meetings.py`, `backend/app/main.py`
- `backend/tests/integration/test_audio_websocket.py` (new)
- `frontend/public/pcm-capture-worklet.js`, `frontend/src/features/meeting/{useMicrophoneCapture.ts,CaptureControls.tsx,MeetingPage.tsx}`, `frontend/src/api.ts`, `frontend/src/styles.css`
- `frontend/tests/e2e/microphone-capture.spec.ts` (new), `frontend/playwright.config.ts` (Chromium fake microphone)

## Validation

- Integration (real PostgreSQL and Redis): 8 WebSocket tests.
  - A full session reaches the job, and the job reaches the transcript.
  - Invalid frames and commands are rejected.
  - Disconnect and resume append without truncating; a stale cursor is rejected.
  - Resuming from the manifest after a simulated restart works.
  - Stopping without audio, a busy meeting, and a new session replacing earlier tracks all behave as specified.
- E2E with Chromium's fake microphone and a mocked socket:
  - Frames are 8192-byte PCM16.
  - Start → stop reaches "Grabación guardada".
  - "Importar" is disabled while recording.
  - A dropped socket resumes with `{resume: true, session_id, next_sequence: 2}`.
  - The E2E exposed a real defect, now fixed: the page refreshed the meeting before the backend confirmed the session, so "Importar" stayed enabled. The UI now reacts to `audio.ready`.

## Risks

Frames in flight at the moment of a network loss cannot be replayed; the resume reports them as `missing_frames`. Browser throttling can delay reconnect timers.

## Next action

The live pipeline (VAD, windows, overlap, stitching and provisional events) on top of this session.
