# Feature: Agent microphone waveform
Status: in progress
Last updated: 2026-09-17

## Problem and target user

The Windows agent currently exposes only control endpoints. The frontend waveform is generated from the browser microphone, so a user cannot verify that the installed agent can access a Windows microphone.

## Desired outcome

The agent captures the Windows default microphone and publishes operational RMS levels locally. The frontend displays those levels as the agent waveform and distinguishes agent capture from browser fallback.

## Smallest useful increment

Implement one Windows microphone adapter using `sounddevice`, a local WebSocket level stream, and frontend consumption of that stream. System audio remains explicitly unavailable.

## Scope

- Probe the default microphone.
- Start and stop a microphone capture session in the agent.
- Publish timestamped normalized RMS levels over a localhost WebSocket.
- Consume agent levels in the frontend waveform.
- Keep browser microphone transport as an explicit fallback only.
- Relay agent PCM through the existing backend audio WebSocket.
- Report microphone, system audio, permission and device failures explicitly.

Out of scope: Windows system-audio loopback, direct agent-to-backend authorization, device selection UI, persistent raw audio storage, and transcript changes.

## Acceptance criteria

- Agent capabilities report microphone availability when a default input device is usable.
- Starting a microphone-only agent session opens the input device and returns a session id.
- The levels WebSocket reports source, session id, timestamp and normalized level.
- The PCM WebSocket reports native `int16` mono 16 kHz frames for the active session.
- The frontend waveform uses agent levels when the agent session is active.
- Silent input produces low levels without being reported as disconnected.
- Device or permission failure is visible and does not claim active capture.
- System audio remains `unsupported` or `not_verified` and is never shown as active.
- Existing browser/backend audio flow remains available as fallback.
- Stopping the session releases the input device and closes the level stream.

## States and failure behavior

`available`, `starting`, `active_signal`, `active_silence`, `permission_required`, `unsupported`, `device_unavailable`, `agent_disconnected` and `error` are represented without claiming native audio when no samples are available.

## Data and provenance constraints

Only aggregate RMS levels and active PCM frames are sent over local WebSockets. Raw audio is not logged by this increment. Levels are operational telemetry and never transcript evidence; `original.pcm` remains the backend source of truth.

## Dependencies and assumptions

The Windows package includes `sounddevice` and its PortAudio runtime. The default Windows input device is sufficient for the first increment. The local browser origin is already configured in the agent.

## Implementation record

Implemented `sounddevice` microphone probing/capture, the microphone-only session contract, local levels and PCM WebSockets, frontend agent waveform selection, native PCM relay through the existing backend WebSocket, fallback messaging, and tests/build validation.

## Validation

Agent tests pass, the frontend build passes, static diagnostics are clean, and a real Windows device probe reports the C922 Pro Stream Webcam as available. A Windows end-to-end UI smoke test and native PCM forwarding validation remain.

## Risks and open questions

The frontend remains the relay for the backend WebSocket, so the agent is the audio source but not yet a direct backend client. A future slice can move the backend connection into the agent after an authorization contract is defined.

## Next action

Add an explicit source/provenance field to the backend audio session and evaluate moving the backend WebSocket client into the agent.
