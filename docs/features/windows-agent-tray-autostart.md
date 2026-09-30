# Feature: Windows agent tray and autostart
Status: in progress
Last updated: 2026-09-17

## Problem and target user

The local `agent` must be available when a Windows user starts a session, without requiring a terminal to remain open. Users also need a visible way to inspect the agent and exit it. Starting the process must not start an audio recording.

## Desired outcome

The agent can run as a Windows system-tray process with its localhost API active, registers itself for the current user's login, and exposes a menu to inspect status, toggle autostart and exit.

## Smallest useful increment

Add `advera-agent --tray`, a background Uvicorn server, a tray icon/menu, and a per-user `HKCU` Run entry. Keep native audio capabilities `not_verified` until OS-specific adapters are implemented.

## Scope

- Windows tray process.
- Autostart for the current Windows user.
- Toggle and exit actions.
- Localhost API remains available at `127.0.0.1:8765`.
- No automatic audio capture at login.
- No permanent secrets or meeting data in registry values or logs.

Out of scope: installer/signing, Windows WASAPI capture, macOS/Linux tray packaging and automatic recording.

## Acceptance criteria

- `advera-agent --tray` starts the local API and tray process.
- The configuration wizard enables current-user autostart only after backend health validation.
- Tray menu can disable and re-enable autostart.
- Tray exit requests server shutdown and terminates the resident process.
- Starting Windows or the agent does not create a capture session.
- Non-Windows environments do not attempt Windows registry writes.
- Existing frontend-controlled capture remains explicit.

## States and failure behavior

- API unavailable: frontend reports agent unavailable.
- Port occupied: Uvicorn reports startup failure; no false available state is shown.
- Native adapter unverified: tray/API remain available but capabilities report `not_verified`.
- Exit during a future recording must be handled by the capture session layer before native capture ships.

## Data and provenance constraints

- Registry contains only the executable startup command.
- No audio, transcript, tokens or meeting identifiers are stored by autostart.
- The agent still requires explicit frontend session control for recording.

## Implementation record

Added `--tray`, `agent.autostart`, a tray runner, a `__main__` entrypoint and Windows-safe autostart helpers. Autostart is now enabled only by the configuration wizard after backend validation; the tray menu can open the wizard or remove the entry. Native capture remains deliberately unverified.

Files changed:

- `agent/pyproject.toml`
- `agent/agent/__main__.py`
- `agent/agent/main.py`
- `agent/agent/tray.py`
- `agent/agent/autostart.py`
- `agent/tests/test_autostart.py`
- `docs/features/windows-agent-tray-autostart.md`

## Validation

Pending agent tests and a Windows GUI smoke test. Linux test coverage verifies that registry operations are a no-op outside Windows.

## Risks and open questions

- A production Windows release needs a signed installer and a stable executable path before registry autostart is enabled.
- Tray behavior and shutdown should be tested on supported Windows versions.
- A future capture session must define safe shutdown semantics before allowing exit during recording.

## Next action

Build/package the agent for Windows and run a manual tray/autostart smoke test, then implement the verified WASAPI adapters.
