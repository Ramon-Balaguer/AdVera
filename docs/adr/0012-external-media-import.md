# ADR 0012: External media import uses the system track

## Status

Accepted (2026-09-26)

## Context

AdVera needs to process an existing audio or video recording from a meeting detail page. Imported media has no browser or capture-agent microphone track, while the definitive worker already accepts any non-empty stored track.

## Decision

The API accepts one multipart audio/video file at `/api/meetings/{meeting_id}/imports`. The backend stores the uploaded source, converts it to mono PCM16 at 16 kHz, writes it to `system.pcm`, and queues the existing asynchronous definitive transcription job with only the `system` track. Video conversion uses the runtime's `ffmpeg` executable. The frontend disables microphone capture while imported media is the meeting's only source.

## Consequences

- Existing transcription, provenance hashing, Brain, and Memory boundaries remain unchanged.
- Imported meetings may legitimately have no `original.pcm`; workers must continue selecting only non-empty tracks.
- Runtime images must provide `ffmpeg`, and upload size limits apply before conversion.
- Import history is not persisted in the relational schema in this increment; a future history or richer provenance contract requires a new ADR or superseding decision.

## Validation and rollback

Focused integration tests cover valid system-only imports and unsupported files. Rollback is to remove the import route and UI action; existing WebSocket capture and transcription paths remain independent.

## Related records
- [Meeting media import](../features/meeting-media-import.md)
- [ADR 0005: Independent microphone and system tracks](0005-dual-track-audio-processing.md)
- [ADR 0008: Asynchronous definitive transcription worker](0008-asynchronous-definitive-transcription-worker.md)