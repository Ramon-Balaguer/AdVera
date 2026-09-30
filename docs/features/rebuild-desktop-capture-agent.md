# Feature: Rebuild desktop Capture Agent
Status: partial
Last updated: 2026-09-30

## Objective

Capture the Windows microphone and the system playback (the other meeting participants) as two independent tracks with a desktop agent. The backend owns the PCM ingestion; the frontend only controls and observes (ADR 0005, 0010).

## Scope

In scope:
- **Agent** (`agent/`, Python, Windows):
  - Outbound control WebSocket, with no local port and reconnection with bounded backoff (`outbound-capture-agent-websocket.md`).
  - `per-track` negotiation and one PCM WebSocket per track with a JSON handshake (`per-track-pcm-websockets.md`).
  - Microphone through `sounddevice` (`agent-microphone-waveform.md`) and system playback through the SoundCard WASAPI loopback, downmixed to mono (`windows-wasapi-loopback-system-track.md`).
  - Per-track bounded queues that drop the oldest frame, and RMS levels at 10 Hz.
  - Tray (pystray) with state, configuration, traffic diagnostics (`tray-send-statistics.md`), an autostart toggle and exit.
  - A generic "AdVera está grabando" notification (`agent-recording-notification.md`).
  - Current-user HKCU autostart (`windows-agent-tray-autostart.md`).
  - A Tkinter configuration wizard with URL validation and the `service=advera-api` health contract (`agent-configuration-wizard.md`).
  - A `--probe` command that reports track capabilities.
- **Backend** (`capture_agent.py`):
  - Agent registry and control channel with an optional `CAPTURE_AGENT_TOKEN` bearer.
  - The capture session is reserved and associated with the meeting's audio session before `capture.start` (`agent-pcm-e2e-delivery-fix.md`).
  - Per-track PCM is written straight into `original.pcm` and `system.pcm`, with bounded queues.
  - Metrics and `capture.error` are relayed to the meeting socket; levels go through `WS /ws/capture-agent/{id}/{track}/levels`.
  - `GET/POST/DELETE /api/capture-agent/...` (spec §20).
  - A meeting-socket `stop` also stops the agent.
- **Frontend:**
  - Agent recording with per-track levels and byte counters is the primary mode when an agent is connected; the browser microphone is the fallback.
  - The browser never carries native PCM.

Out of scope: a signed installer, macOS/Linux adapters (they report `not_verified`), device selection, replay of frames lost during an overflow or restart (ADR 0010), and the live transcript.

## Acceptance criteria

1. The agent opens no local port and connects outbound. A wrong token is rejected.
2. A dual-track session delivers microphone and system PCM on independent channels into `original.pcm` and `system.pcm`, without the browser relaying audio.
3. An unavailable adapter produces `capture.error` with a controlled code, and a later session starts cleanly.
4. A lost control channel reconnects. A lost agent fails the active capture and keeps stored audio.
5. Stopping from the meeting socket stops the agent, drains the tracks and queues the definitive job.
6. The frontend offers agent recording when tracks are available and otherwise falls back to the browser microphone.
7. Starting the agent, the tray or Windows never starts a recording.

## Implementation state

Implemented and verified with synthetic captures against the real backend. On this machine `--probe` reports both tracks available (microphone: C922 webcam mic; system: loopback of the default Bose QC45 output).

It stays `partial` until two things happen:
- a consented real-device capture (`scripts/agent_smoke.py`), a tray/wizard/autostart GUI smoke, and independent QA/Security review;
- a signed installer before any production autostart.

## Decisions

- The microphone uses `sounddevice`, not SoundCard. SoundCard's recorder asserts on this machine's C922 microphone mix format (`wFormatTag != 0xFFFE`); `sounddevice` delivers 16 kHz mono PCM16 directly. This matches the documented split (`agent-microphone-waveform.md` and `windows-wasapi-loopback-system-track.md`).
- Recording flow: the frontend opens the meeting socket with `{"type": "start", "source": "agent"}`, then calls `POST /api/capture-agent/sessions`. The backend associates the capture with the active meeting session (ADR 0010).
- In an agent-owned session the meeting socket rejects browser frames (`AGENT_CAPTURE_ACTIVE`). On resume it skips the client-cursor check, because the agent is the frame source.
- `/api/health` now returns `{"service": "advera-api", "status": "ok"}`, the contract the wizard validates.
- The legacy frontend PCM proxy `WS /ws/capture-agent/{id}/{track}/pcm` listed in spec §20 is not built: ADR 0010 removed the frontend as a native PCM transport. This is a reported spec/ADR discrepancy.
- One connected agent is supported, which matches the single-user deployment (ADR 0015).

## Files changed

- Agent: `agent/pyproject.toml`, `agent/agent/{__init__,__main__,config,capture,remote,diagnostics,autostart,wizard,tray}.py`, `agent/tests/{fakes,test_units,test_remote}.py`
- Backend: `backend/app/capture_agent.py` (new), `backend/app/audio.py`, `backend/app/audio_sessions.py`, `backend/app/contracts.py`, `backend/app/config.py`, `backend/app/main.py`
- Backend tests: `backend/tests/integration/test_capture_agent_e2e.py` (new), `backend/tests/test_health.py`
- Frontend: `frontend/src/features/meeting/{useAgentCapture.ts,CaptureControls.tsx}`, `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/tests/e2e/agent-capture.spec.ts` (new)
- Scripts and CI: `scripts/agent_smoke.py`, `scripts/agent_synthetic.py` (new), `.github/workflows/ci.yml` (agent job)

## Validation

- Agent: 13 tests.
  - URL normalization, the health contract, its fallback and priority, and the config round-trip.
  - Downmix and clipping, autostart as a no-op off Windows, and diagnostics counters.
  - The protocol against a fake backend: dual-track channels, notification, levels, stop drain, capture failure and recovery, reconnection, and a wrong token.
- Real E2E: a uvicorn server runs the actual app with PostgreSQL and Redis, and the actual `RemoteAgent` runs with synthetic captures.
  - 5 frames per track reach `original.pcm` and `system.pcm`.
  - Metrics are relayed and `stop` queues the job.
  - A wrong token is rejected; with no agent the API returns `503 AGENT_UNAVAILABLE`.
- Frontend E2E: agent mode starts with `source: "agent"` and requests both tracks, shows per-track bytes and levels, and sends zero binary frames from the browser. The browser fallback is offered when no agent is connected.
- Full chain, real agent + real backend + real frontend in a browser, with synthetic captures (`scripts/agent_synthetic.py`, no microphone or loopback touched):
  - The page detected the connected agent and offered "Grabar con el agente (micrófono + sistema)".
  - After 6 s both waveforms were drawn from the agent's real per-track levels, and both byte counters had grown (208 KiB each).
  - After stop, 85 frames and 696,320 bytes (21.76 s) were stored per track, both tracks were served as WAV, the meeting went to `processing`, and both waveforms disappeared.
- Real devices: `python -m agent --probe` → microphone and system `available`. No real capture was recorded without consent.
- The build found two defects, both fixed:
  - a Tkinter callback read the exception variable after Python had cleared it;
  - capture error codes were derived from arbitrary exception text.

## Risks

- A production autostart needs a signed installer instead of the Python command in the registry.
- Some Windows drivers expose no loopback endpoint, or change the default device mid-session.
- Frames dropped by queue overflow, or lost in a backend restart, are not replayed (ADR 0010).

## Next action

Run `python scripts/agent_smoke.py` against the stack with consent, optionally with `--play data/smoke/ca-two-speakers.wav` so the system track carries Catalan speech. Then run the tray and wizard GUI smoke on Windows.
