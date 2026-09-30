# Feature: Native dual-track audio agent
Status: partial
Last updated: 2026-09-17

## Problem and target user

The browser currently captures only the microphone. Users recording meetings need the other participants' audio from the system output as a separate original track, while the agent must work across Windows, macOS and Linux without silently claiming unsupported capture.

## Desired outcome

AdVera has a versioned contract for a local native agent that reports capabilities, captures `microphone` and `system` independently, and joins the active recording when the frontend starts it.

## Smallest useful increment

Define and validate the cross-platform control/data contract for capabilities, capture sessions, tracks and per-track frames. Report Windows as the first target for a real adapter; macOS and Linux remain `not_verified` until their OS-specific backends and permissions are tested.

## Scope

- Capability and permission states.
- Capture session and track identity.
- Independent per-track sequences and monotonic capture timestamps.
- PCM format metadata and provenance fields.
- Explicit fallback states when the agent or system audio is unavailable.
- Contract tests for valid and invalid messages.

Out of scope for this increment: native WASAPI/CoreAudio/PipeWire capture, installers, signing, backend multi-track persistence, and automatic frontend activation.

## Acceptance criteria

- A capability response distinguishes agent unavailable, permission required, available, unsupported and not verified.
- `microphone` and `system` are distinct track identifiers.
- A frame cannot omit its track, sequence, timestamp or format.
- Sequences are scoped per track rather than global.
- The contract can represent a degraded microphone-only session explicitly.
- Contract tests run without an operating-system audio device.

## States and failure behavior

- `not_installed`, `starting`, `permission_required`, `available`, `recording`, `stopping`, `unsupported`, `not_verified`, `error`.
- System audio unavailable must not be represented as a successful dual-track session.
- OS adapters must return a diagnostic code without storing audio in logs.

## Data and provenance constraints

- Original tracks remain separate and immutable.
- No audio content or secrets are included in contract tests.
- Every track carries format, device, OS and agent version metadata for later hashes and transcript provenance.
- Definitive intelligence remains restricted to definitive transcript processing.

## Dependencies and assumptions

- The agent runs locally with explicit user consent.
- The frontend controls activation; the agent does not capture silently.
- A later IPC slice will use a loopback-only channel and an ephemeral session token.
- Windows WASAPI loopback is the first real capture adapter; macOS and Linux require separate validation.

## Implementation record

Added a standalone `agent` project with a localhost control plane, capability reporting, explicit dual-track session lifecycle and CORS restricted to the local frontend origins. The frontend now performs an agent preflight at recording start, requests a dual session only when both tracks are verified, and reports an explicit microphone-only fallback otherwise. Backend protocol models and contract tests cover track identity, per-track cursor data and explicit fallback states. Native OS capture remains pending.

Files changed:

- `backend/app/contracts.py`
- `backend/tests/test_capture_agent_contracts.py`
- `agent/pyproject.toml`
- `agent/agent/models.py`
- `agent/agent/capabilities.py`
- `agent/agent/main.py`
- `agent/tests/test_agent.py`
- `agent/README.md`
- `frontend/src/App.tsx`
- `docs/features/native-dual-track-audio-agent.md`

## Validation

Agent tests pass, backend contract and full suites pass, and the frontend build/E2E remain the release checks. Native OS adapter tests are not yet available.

## Risks and open questions

- System audio permissions and loopback APIs differ substantially by OS.
- Clock drift and device changes require an adapter-level synchronization policy.
- The browser-to-agent control channel needs origin validation and an ephemeral token before shipping.

## Next action

Implement the Windows WASAPI dual-track adapter behind this control plane, then add backend multi-track persistence and real agent frame transport as separate feature records.
