# ADR 0004: Audio Capture and Live Delivery Contracts

## Status

Accepted.

## Context

Browser and native capture clients send PCM while users need live status and transcript updates. Capture must survive malformed input and preserve a trustworthy finalization boundary.

## Decision

Use WebSocket transport for active audio capture, live status and progress/result delivery. PCM input is signed 16-bit, mono, 16 kHz. The original audio is persisted before definitive processing, and the final transcript is produced from that complete source rather than from provisional text. Durable job state and HTTP status endpoints remain recovery boundaries for background work; bounded polling is a fallback only where a WebSocket is unavailable or unjustified.

## Consequences

- WebSocket contracts require explicit lifecycle, sequence, acknowledgement, disconnect and failure states.
- Clients can render provisional feedback without making it authoritative.
- Reconnect and recovery must use durable state rather than assuming an in-memory socket survived.
- Audio format changes are contract changes and require compatibility planning.

## Validation and rollback

Validate WebSocket integration tests, malformed-command tests, sequence/byte acknowledgements, disconnect behavior and finalization failure preservation. Rollback by keeping the existing HTTP status endpoint as recovery while disabling the new live stream path.

## Related records

- `docs/features/stable-audio-transcription-pipeline.md`
- `docs/features/per-track-pcm-websockets.md`
- `docs/features/brain-query-results-websocket.md`
