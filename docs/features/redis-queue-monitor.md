# Feature: Redis Queue Monitor
Status: complete
Last updated: 2026-09-25

## Problem and target user

Operators and developers can see durable PostgreSQL job summaries but cannot inspect what is currently retained or pending in the Redis Streams that activate workers.

## Desired outcome

The Monitor page shows every configured Redis job stream, its current size, consumer-group activity, and a bounded list of safe job references for operational diagnosis.

## Scope

- Inspect the transcription, Summary, Brain index and Brain query streams.
- Show stream length, consumer groups, pending counts, consumers and lag when Redis provides them.
- Show a bounded recent entry list containing only Redis entry IDs, derived enqueue times and `job_id`.
- Preserve the rest of the Monitor response when Redis is unavailable or one stream fails.
- Refresh through the existing five-second Monitor polling.

Out of scope: queue mutation, acknowledgement, retry, replay, cancellation, raw Redis payloads, transcript/audio content, prompts, provider data and historical charts.

## Acceptance criteria

- The Monitor lists all four configured streams, including empty or missing streams.
- Each stream reports a bounded, safe view of recent entries and group metrics.
- Redis unavailability or a per-stream error is visible without hiding other Monitor sections.
- No raw message fields other than `job_id` cross the API boundary.
- A large stream cannot cause an unbounded API response.

## States and failure behavior

- `available`: stream metadata and entries were read.
- `empty`: Redis is reachable and the stream has no entries.
- `unavailable`: Redis or an individual inspection operation failed.
- `truncated`: more entries exist than the display limit.

## Data and provenance constraints

Redis is operational transport only; PostgreSQL remains authoritative for job lifecycle and results. The API uses an allowlist of configured stream names and never returns raw message payloads, meeting content, secrets or provider errors.

## Dependencies and assumptions

The existing `/api/monitor` polling endpoint and the four queue settings are reused. Consumer groups follow the worker conventions already used by Summary, Transcription and Brain workers.

## Implementation record

- Add read-only Redis stream inspection to the existing monitor snapshot.
- Add Monitor cards with stream metrics and safe recent entries.
- Keep the response bounded to eight entries per stream.

## Validation

- `pytest backend/tests/test_monitor.py -q`: 3 passed.
- Redis payload redaction is covered with a fake stream client.
- Frontend build remains blocked by the pre-existing `cytoscape` and `capture_locked` errors documented in the previous Monitor work.

## Risks and open questions

Redis stream IDs and job IDs are operational identifiers and should remain restricted to Monitor access controls when authentication is added. Group lag may be unavailable on older Redis versions and is therefore nullable.

## Next action

Validate against a running Redis/PostgreSQL development stack when available; queue inspection is read-only and does not require a migration or ADR.
