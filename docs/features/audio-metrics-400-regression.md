# Bug: audio-metrics response regression
Status: complete
Last updated: 2026-09-18

## Problem
The active API was serving an older meetings module because the development Compose built the backend into the image without mounting `backend/app`. The frontend request to `/api/meetings/{meeting_id}/audio-metrics` therefore did not reach the current endpoint and returned 404 instead of metrics.

## Fix
Mounted `../backend/app:/app/app` in the development API service and recreated the container. Added an integration regression test that creates a valid meeting and requires `audio-metrics` to return HTTP 200 with the zeroed per-track schema when no audio exists.

## Acceptance check
`GET /api/meetings/{meeting_id}/audio-metrics` returns `200` for a valid meeting and includes `frames`, `bytes`, `duration_seconds`, and microphone/system metrics.

## Validation
- Backend compileall passed.
- Active API returned `200` from both the host and inside the container.
- Active response included microphone and system byte/frame metrics.
- Development Compose now keeps the active API code synchronized with the workspace.
- Full pytest execution remains unavailable because pytest is not installed in the local environment.

## Regression test
`backend/tests/integration/test_meetings_api.py::test_audio_metrics_returns_metrics_for_a_meeting_without_audio`
