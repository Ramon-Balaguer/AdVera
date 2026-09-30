# Feature: Agent recording notification
Status: complete
Last updated: 2026-09-17

## Problem and target user
A Windows user can start a native capture session from the AdVera frontend without a clear local signal from the resident agent that recording has actually begun.

## Desired outcome
The tray agent shows one generic Windows notification after all requested native tracks start successfully.

## Scope
- Notify once when a native agent session reaches `recording`.
- Use the existing tray icon notification capability.
- Keep the server and tests safe when no tray is running or the platform does not support notifications.

Out of scope: browser-only capture, per-track notifications, stop notifications, notification history/preferences and meeting content in notifications.

## Acceptance criteria
- A successful `POST /sessions` emits exactly one notification when a notifier is registered.
- Unavailable tracks, failed capture startup and duplicate active sessions emit no notification.
- The message is generic and contains no recording ID, transcript, audio or credentials.
- Notification failures do not fail session creation or stop capture.
- Running the agent without tray remains supported.

## States and failure behavior
- `starting`: no notification.
- `recording`: notify once after every requested capture has started.
- `503` or `409`: no notification.
- Unsupported notification backend: capture continues and the failure is logged without meeting data.

## Data and provenance constraints
The event is tied to the agent's effective transition to `AgentStatus.RECORDING`. No notification data is persisted and no meeting content is included.

## Dependencies and assumptions
The tray uses `pystray.Icon.notify` on Windows. The HTTP app may run without a tray icon, in which case notification delivery is a no-op.

## Implementation record
- `main.py` invokes a safe notifier hook only after every requested capture has started and the session is set to `recording`.
- `tray.py` connects the hook to `pystray.Icon.notify` with the generic message `AdVera está grabando`.
- Notification exceptions are logged and do not interrupt capture.
- Headless mode leaves the hook as a no-op.

## Validation
- Focused agent tests: `7 passed`.
- The tests verify one notification after successful capture startup and zero notifications after a startup failure.
- Static diagnostics report no errors in the touched Python files.

## Risks and open questions
Some Windows notification settings or tray backends may suppress the balloon. A future product decision may add a notification when recording stops.

## Next action
Implement the notifier callback and validate the success and failure paths.
