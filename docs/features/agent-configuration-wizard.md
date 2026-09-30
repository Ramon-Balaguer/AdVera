# Feature: Agent configuration wizard
Status: in progress
Last updated: 2026-09-17

## Problem and target user

The Windows agent can expose a local API, but users cannot configure which AdVera backend it should use or safely reverse the Windows startup registration.

## Desired outcome

A native wizard lets the user enter a backend URL, verify the AdVera health contract at `<base-url>/api/health` (with `<base-url>/health` compatibility fallback), save only validated configuration, register the current-user Windows autostart, and remove that registration later.

## Smallest useful increment

Tkinter wizard available through `python -m agent --configure` and the tray menu. It stores configuration under the user's application configuration directory and controls `HKCU` autostart only after a successful health check.

## Scope

- Backend URL input and normalization.
- Connectivity validation against `/api/health`, with `/health` compatibility fallback.
- AdVera health contract validation (`service=advera-api`, `status=ok`).
- Atomic local configuration persistence.
- Register and unregister current-user Windows autostart.
- Reopen wizard from tray.
- No audio capture during configuration or agent startup.

Out of scope: credentials, tokens, installer signing, remote configuration, proxy setup and native audio adapters.

## Acceptance criteria

- Invalid URLs are rejected before any request.
- Trailing slashes are normalized and `/health` is appended exactly once.
- Timeout, network error, non-2xx and incompatible JSON show an error and do not register autostart.
- Successful health validation enables saving and Windows registration.
- The wizard displays configured and autostart state on reopen.
- “Desregistrar inicio” removes only the agent's own registry entry.
- The tray no longer enables autostart without validated backend configuration.
- Starting the wizard or agent never starts an audio session.

## States and failure behavior

- Unconfigured, invalid URL, checking, backend available, backend unavailable, incompatible backend, configuration saved.
- Autostart registered or not registered.
- Corrupt configuration is ignored and can be replaced from the wizard.

## Data and provenance constraints

- Local configuration stores only backend URL and last health status.
- Registry stores only the agent startup command.
- No audio, transcripts, meeting IDs, credentials or tokens are stored.

## Implementation record

Added `agent.config` for URL validation, health checks and atomic persistence; added `agent.wizard` with a single backend URL field; added CLI `--configure`; added tray menu integration; and made autostart activation conditional on successful validation. `main.py` and `tray.py` retain the saved local server settings internally while the wizard keeps them out of the normal user flow.

Files changed:

- `agent/agent/config.py`
- `agent/agent/wizard.py`
- `agent/agent/main.py`
- `agent/agent/tray.py`
- `agent/tests/test_config.py`
- `docs/features/agent-configuration-wizard.md`

## Validation

Pending agent test suite and Windows GUI smoke test. Non-Windows tests cover URL, persistence, health failure and registry no-op behavior.

## Risks and open questions

- Tkinter availability should be confirmed in the Windows distribution package.
- A signed installer should replace the Python command in the registry for production.
- The backend URL is currently unauthenticated and must not contain credentials.
- Changing host, port or origins requires restarting the resident agent so its HTTP server can rebind and rebuild CORS middleware.

## Next action

Run the wizard on Windows, validate `/health` against the local backend, inspect the registry entry, then test unregister and tray restart.
