# ADR 0016: Imported media keeps only the extracted audio

## Status

Accepted (2026-09-30).

## Context

ADR 0012 decided that an import "stores the uploaded source, converts it to mono PCM16 at 16 kHz, writes it to `system.pcm`". The feature record `meeting-media-import.md` both retained the uploaded file "for provenance and conversion retry" and deleted the video source after verification. The product owner decided on 2026-09-30 that AdVera keeps only the audio of an imported recording.

## Decision

An import writes the upload to a temporary file inside the meeting directory, converts it with `ffmpeg` and verifies the extracted PCM (non-empty and aligned to 16-bit samples). Then it deletes the uploaded file. This applies to every import, audio or video, and to both successful and failed conversions. The only persisted artifact is `system.pcm`, plus the transcript produced from it.

The rest of ADR 0012 is unchanged: one multipart file, allowlisted media, the system track, and the existing asynchronous definitive transcription job.

## Consequences

- Video frames and the original container, codec and metadata are never stored. This reduces disk use and exposure of sensitive content.
- A failed conversion cannot be retried from the server. The user uploads the file again.
- Provenance of an import is the `system.pcm` hash recorded on the transcription job and in the transcript. The original file's hash is not kept.
- Deleting a meeting still removes its whole storage directory (`meeting-deletion-data-retention.md`).

## Validation and rollback

Integration tests assert that a successful video import leaves only `system.pcm` in the meeting directory, and that a failed extraction leaves no uploaded file. Rollback means keeping the temporary file under a stable name, which is the ADR 0012 behavior. Data deleted under this decision cannot be restored.

## Related records

- [ADR 0012: External media import uses the system track](0012-external-media-import.md)
- [Rebuild imported media keeps audio only](../features/rebuild-import-audio-only.md)
