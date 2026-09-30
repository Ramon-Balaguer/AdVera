# ADR 0005: Independent Microphone and System Audio Tracks

## Status

Accepted.

## Context

AdVera captures microphone and system audio separately. Mixing them before ASR loses track provenance and makes speaker attribution and playback auditing harder.

## Decision

Persist microphone and system PCM independently, submit each available non-empty track independently to definitive ASR, and retain the track identifier on every transcript segment. Track results are merged only by chronological ordering for the unified transcript view. Speaker labels are scoped to each track and are not assumed to identify the same person across tracks.

## Consequences

- A missing or empty track does not block a valid result from the other track.
- Provenance can identify the source audio for every segment.
- Global speaker reconciliation and cross-track overlap handling remain explicit future work.
- Reprocessing must use the stored track files, not a reconstructed mixed stream.

## Validation and rollback

Validate one-track, two-track, empty-track and track-provenance tests. Rollback by processing the preserved source tracks with the previous provider path; no destructive migration is required.

## Related records

- `docs/features/dual-track-playback-live-metrics.md`
- `docs/features/per-track-pcm-websockets.md`
- `docs/features/moss-definitive-provider.md`
