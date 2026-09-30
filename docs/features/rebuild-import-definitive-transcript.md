# Feature: Rebuild import to definitive transcript
Status: partial
Last updated: 2026-09-30

## Objective

Deliver the first vertical slice of the rebuild. A user creates a meeting, imports one audio or video file, and receives the definitive transcript through the durable asynchronous transcription path, then can play the audio from any segment. This exercises the source-of-truth boundary that every later increment depends on (ADR 0002) without the live pipeline.

## Scope

In scope:
- Meeting create, list, detail, rename and delete. Delete removes the database rows first and then the meeting storage directory (`meeting-deletion-data-retention.md`).
- `POST /api/meetings/{id}/imports`: one multipart file, extension and MIME allowlist, a 5 GiB default size limit, conversion to `system.pcm` (mono PCM16, 16 kHz) with `ffmpeg`, the uploaded source retained under the meeting directory, and a second import rejected while a job is active (ADR 0012, `meeting-media-import.md`).
- A durable `TranscriptionJob`: commit in PostgreSQL, then publish only `{job_id}` to `advera:transcription:jobs`. A dedicated worker uses a consumer group, leases with heartbeat, bounded retries, stale-lease recovery and republication of queued jobs (ADR 0008, `redis.md`).
- The ASR provider boundary with definitive and fallback roles (ADR 0003). WhisperX is the default and MOSS is not part of this slice (ADR 0007). The provider receives no language code (ADR 0014); each segment carries its track's detected language (`definitive-transcription-segment-language.md`).
- Per-track progress `0/N → N/N` with the `stage` axis (`incremental-transcription-worker-progress.md`).
- `transcript.json` written atomically only when valid segments exist. The meeting becomes `ready` with `primary_language` set to the distinct segment languages.
- `GET /api/meetings/{id}/transcription` as the durable status contract, plus `GET /transcript` and `GET /audio/{track}` (WAV synthesized on the fly with byte-range support).
- `attendee_count` derived from the definitive transcript (ADR 0011).
- Frontend: meeting list, meeting page, import modal with upload progress, bounded status polling and the definitive transcript with click-to-seek.

Out of scope: authentication (ADR 0015), browser or native capture, the live pipeline, MOSS, speaker diarization (a follow-up increment behind `DiarizationEngine`; WhisperX segments carry `speaker: null` until then), reprocessing, Brain and Memory scheduling (the worker has no downstream consumer yet), archiving and job cancellation.

## Acceptance criteria

1. The import request returns once the media is stored, converted and the job is queued, without waiting for ASR.
2. The job row exists in `queued` before the Redis `XADD`, and the stream message contains only `job_id`.
3. If Redis is unavailable at enqueue, the job stays `queued` and the worker's reconciliation republishes it.
4. The worker processes each non-empty track independently, and the definitive provider falls back to the configured fallback provider on failure.
5. A valid result writes `transcript.json` atomically. Every segment has `id`, `start`, `end`, `text`, `track`, `language` and `speaker`, and the meeting becomes `ready` with `primary_language` populated.
6. An empty or invalid ASR result never publishes a transcript. Provider failures retry up to `max_attempts`, while deterministic failures (`EMPTY_TRANSCRIPT`, `NO_AUDIO`, `INPUT_CHANGED`) fail at once. A failed job leaves the job and the meeting `failed` with a sanitized error code, and the audio and any prior transcript are preserved.
7. A stale lease is recovered and the job completes. A lost lease prevents further writes.
8. Progress is monotonic, `processed_tracks/total_tracks`, and reaches `1.0` with `stage=completed`.
9. `attendee_count` is `null` without a definitive transcript and otherwise the number of distinct non-empty speakers.
10. Logs never contain transcript text, PCM, provider payloads or `ffmpeg` output.
11. Migrations upgrade and downgrade cleanly on PostgreSQL 16 + pgvector. Integration tests pass against real PostgreSQL and Redis with a deterministic fake provider.
12. The frontend builds, and the Playwright flow (create → import → transcript visible → click-to-seek) passes.

## Implementation state

Implemented. Acceptance criteria 1-12 pass locally, including a real GPU run. The record stays `partial` because three things are still missing: an independent QA/Security review, a first CI run on a remote, and a Catalan smoke. No Catalan TTS voice is installed, so Catalan needs audio from a licensed or public corpus.

Speaker diarization is not part of this slice. WhisperX segments therefore carry `speaker: null`, and `attendee_count` is `0` for real transcripts until the `DiarizationEngine` increment.

## Decisions

- Track identifiers are `microphone` (`original.pcm`) and `system` (`system.pcm`), matching the capture agent contract (`native-dual-track-audio-agent.md`).
- The idempotency key is derived from the meeting, the source-track hash, the provider and the model (`async-transcription-on-meeting-close.md`). Re-importing identical media reuses a finished job instead of creating a duplicate, and a failed job with the same key is reset to `queued`.
- `max_attempts` defaults to 3. The docs fix this value only for Brain and Memory (`redis.md`), so the same value is used here.
- The uploaded source is retained. ADR 0012 says the backend "stores the uploaded source", but `meeting-media-import.md` also mentions deleting the video source after verification. The ADR wins.
- Stored error values are stable codes (`ASR_FAILED`, `EMPTY_TRANSCRIPT`, `NO_AUDIO`, `INPUT_CHANGED`, `LEASE_EXPIRED`, `INTERNAL_ERROR`), never provider messages (`post-recording-failure-classification.md`).
- `ASR_FAILED` and `INTERNAL_ERROR` are retryable. A provider configuration error, such as MOSS selected in this build or WhisperX not installed, is not retryable unless the fallback path failed for another reason.
- The worker keeps its lease alive with a heartbeat during long provider calls. It runs reconciliation every `TRANSCRIPTION_RECONCILE_SECONDS`, which requeues stale leases and republishes queued jobs whose message may have been lost. On startup it replays its own unacknowledged stream entries.
- Segment ids are `<track>-<n>`, stable within one transcript version. The document stores `segments_sha256` so later Brain and Memory jobs can key on the transcript hash.
- Playwright uses mocked API routes; the backend path is covered by the integration suite against real services.
- `requested_language` from spec §9 is not created, because reprocessing is out of scope.
- Status polling of the HTTP endpoint is the delivery path. An import opens no audio WebSocket, so polling is the justified fallback allowed by ADR 0004.

## Files changed

- Architecture/Data: `backend/app/models.py`, `backend/migrations/versions/0002_meetings_transcription_jobs.py`, `backend/app/meeting_contracts.py`, `backend/app/transcripts.py`
- Backend:
  - `backend/app/{config,database,storage,asr,asr_whisperx,job_queue,transcription_jobs,transcription_worker,media_import,audio_http,meetings,main}.py`
  - `backend/pyproject.toml`, `backend/Dockerfile`
- Tests: `backend/tests/{fakes,test_units}.py`, `backend/tests/integration/{conftest,test_import_transcription}.py`
- Frontend:
  - `frontend/src/{api,format,App}.tsx?`, `frontend/src/styles.css`
  - `frontend/src/features/meetings/MeetingsPage.tsx`, `frontend/src/features/meeting/{MeetingPage,MeetingImportModal}.tsx`
  - `frontend/tests/e2e/{import-transcript,api-health-gate}.spec.ts`
- Operations: `docker/compose.dev.yml` (the `transcription-worker` service, ASR model and device settings), `docker/compose.nvidia.yml`, `.github/workflows/ci.yml`

## Validation

- Backend: `pytest` → 35 passed against real PostgreSQL 16 + pgvector and Redis (`TEST_DATABASE_URL`, `TEST_REDIS_URL`). Without them, 18 pass and 16 are skipped. `ruff check` and `ruff format --check` are clean.
- Migrations: `alembic upgrade head` → `alembic check` (no drift between models and migrations) → `downgrade base` → `upgrade head`, on PostgreSQL 16 + pgvector.
- Frontend: `npm run build` passed. `npm run test:e2e` → 4 passed, covering the health gate, create → import → transcript → click-to-seek, and the unsupported-file error.
- Compose: `compose.dev.yml` and `compose.dev.yml + compose.nvidia.yml` validate. The full stack starts healthy on the RTX 3090, and `torch.cuda.is_available()` is true in the worker.
- Real smoke, WhisperX `small` on CUDA/float16, synthetic TTS speech (no meeting content), through `POST /imports` and the Redis worker:
  - Spanish: completed on the first attempt in 36 s, including model load; `primary_language=["es"]`, 3 aligned segments.
  - English: completed in 14 s; `["en"]`, 2 segments.
  - Worker logs contained only job ids and counts.
- Real UI in the in-app browser: the list shows status, duration and languages. Clicking the third Spanish segment starts playback at its timestamp (6.2 s) and highlights the segment.
- The smoke exposed and fixed one defect. redis-py 8.1 has a default socket read timeout equal to the 5 s `XREADGROUP` block, so an idle worker crashed with `redis.exceptions.TimeoutError`. The fix:
  - `create_redis()` sets a 30 s socket timeout.
  - The worker loop survives any `RedisError`.
  - The Compose worker restarts `unless-stopped`.
  - A regression test covers an idle blocking read.

## Risks

- In the English smoke WhisperX dropped the first short sentence ("Good morning everyone"), likely at VAD segmentation. The multilingual WER/CER dataset (spec §25) is still pending.
- `ffmpeg` conversion runs inside the import request as an external process. It does not block the event loop, but long videos make the request slow.
- WhisperX detects one language per track, not per segment, so multilingual audio in one track is labeled with a single language.
- The worker selects every non-empty track. Once microphone capture exists, an import into a meeting that already has `original.pcm` would also process the microphone track, whereas ADR 0012 queues "only the system track". This must be resolved in the capture increment.

## Next action

Run an independent QA/Security review of this slice, then a Catalan smoke with licensed or public-corpus audio. The next increment in the plan is browser microphone capture over the meeting WebSocket (ADR 0004, 0010) into `original.pcm` and the same job, followed by the live pipeline. Local diarization behind `DiarizationEngine` is a separate slice.
