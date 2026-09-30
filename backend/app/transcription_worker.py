"""Definitive transcription worker (ADR 0002, 0003, 0005, 0008, 0014).

Consumes `advera:transcription:jobs`, reads the complete stored tracks, runs the definitive
provider per non-empty track with the explicit fallback, and atomically publishes
`transcript.json` only when valid segments exist. Logs carry job ids and error codes only:
never audio, transcript text or provider messages.

Run with `python -m app.transcription_worker`.
"""

import asyncio
import logging
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from redis.exceptions import RedisError
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import brain_jobs, memory_jobs, runtime_settings
from app.asr import (
    AsrRole,
    AsrSegment,
    ProviderConfigurationError,
    ProviderError,
    TranscriptionEngine,
    build_engine,
)
from app.config import Settings, get_settings
from app.database import create_engine, create_sessionmaker
from app.diarization import (
    DiarizationEngine,
    EcapaEncoder,
    LocalDiarizationProvider,
    SpeechSpan,
    speaker_label,
)
from app.job_queue import (
    TRANSCRIPTION_CONSUMER_GROUP,
    JobQueue,
    RedisStreamQueue,
    create_redis,
)
from app.models import Meeting, TranscriptionJob, utcnow
from app.storage import MeetingStorage, Track
from app.transcription_jobs import claim, fenced_update, reconcile
from app.transcripts import (
    DiarizationProvenance,
    TrackProvenance,
    TranscriptDocument,
    TranscriptProvenance,
    TranscriptSegment,
    distinct_languages,
    merge_segments,
    parse_definitive,
    segments_sha256,
)

logger = logging.getLogger("advera.transcription_worker")

CONSUMER_GROUP = TRANSCRIPTION_CONSUMER_GROUP

EngineFactory = Callable[[str, AsrRole, Settings], TranscriptionEngine]


class LeaseLost(Exception):
    pass


@dataclass
class JobFailure(Exception):
    code: str
    retryable: bool


@dataclass
class TrackResult:
    segments: list[TranscriptSegment]
    provenance: TrackProvenance


# Within a track, measured ASR progress covers this share; diarization and the rest finish it.
ASR_PROGRESS_SHARE = 0.9
PROGRESS_POLL_SECONDS = 2.0
MIN_PROGRESS_STEP = 0.01


class TrackProgress:
    """Latest measured fraction of the current track, written from the provider thread."""

    def __init__(self) -> None:
        self.fraction = 0.0

    def update(self, fraction: float) -> None:
        self.fraction = max(self.fraction, min(1.0, max(0.0, float(fraction))))


class TranscriptionWorker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: MeetingStorage,
        queue: JobQueue,
        settings: Settings,
        engine_factory: EngineFactory = build_engine,
        diarizer: DiarizationEngine | None = None,
        brain_queue: JobQueue | None = None,
        memory_queue: JobQueue | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.storage = storage
        self.queue = queue
        self.settings = settings
        self.engine_factory = engine_factory
        self.diarizer = diarizer
        self.brain_queue = brain_queue
        self.memory_queue = memory_queue
        self._engines: dict[str, TranscriptionEngine] = {}

    def _engine(self, provider: str) -> TranscriptionEngine:
        if provider not in self._engines:
            self._engines[provider] = self.engine_factory(provider, "definitive", self.settings)
        return self._engines[provider]

    async def process(self, job_id: str) -> None:
        token = str(uuid.uuid4())
        async with self.sessionmaker() as session:
            if not await claim(session, job_id, token):
                return
            job = await session.get(TranscriptionJob, job_id)
            meeting = await session.get(Meeting, job.meeting_id) if job else None
        if job is None or meeting is None:
            return
        logger.info("transcription job %s claimed (attempt %s)", job_id, job.attempts)
        try:
            await self._run(job, token)
        except LeaseLost:
            logger.warning("transcription job %s lost its lease", job_id)
        except JobFailure as failure:
            await self._fail(job, token, failure)
        except Exception as error:
            logger.error("transcription job %s internal error: %s", job_id, type(error).__name__)
            await self._fail(job, token, JobFailure("INTERNAL_ERROR", retryable=True))

    async def _write(self, job_id: str, token: str, **values) -> None:
        async with self.sessionmaker() as session:
            if not await fenced_update(session, job_id, token, **values):
                raise LeaseLost
            await session.commit()

    async def _run(self, job: TranscriptionJob, token: str) -> None:
        meeting_id = job.meeting_id
        tracks = self.storage.non_empty_tracks(meeting_id)
        if not tracks:
            raise JobFailure("NO_AUDIO", retryable=False)
        input_sha256 = await asyncio.to_thread(self.storage.tracks_sha256, meeting_id, tracks)
        if input_sha256 != job.input_sha256:
            raise JobFailure("INPUT_CHANGED", retryable=False)
        await self._write(job.id, token, total_tracks=len(tracks))

        results: dict[Track, TrackResult] = {}
        speakers_so_far = 0
        for index, track in enumerate(tracks):
            await self._write(job.id, token, track=track, stage="transcribing")
            progress = TrackProgress()
            results[track] = await self._with_heartbeat(
                job.id,
                token,
                self._transcribe_track(job, token, track, speakers_so_far, progress),
                progress=lambda p=progress, i=index: (
                    (i + ASR_PROGRESS_SHARE * p.fraction) / len(tracks)
                ),
            )
            diarization = results[track].provenance.diarization
            speakers_so_far += diarization.speakers if diarization else 0
            await self._write(
                job.id,
                token,
                processed_tracks=index + 1,
                progress=(index + 1) / len(tracks),
            )

        await self._write(job.id, token, stage="finalizing", track=None)
        segments = merge_segments({track: result.segments for track, result in results.items()})
        if not segments:
            raise JobFailure("EMPTY_TRANSCRIPT", retryable=False)
        languages = distinct_languages(segments)
        document = TranscriptDocument(
            meeting_id=meeting_id,
            generated_at=utcnow(),
            segments_sha256=segments_sha256(segments),
            primary_language=languages,
            provenance=TranscriptProvenance(
                job_id=job.id,
                input_sha256=input_sha256,
                tracks=[result.provenance for result in results.values()],
            ),
            segments=segments,
        )
        duration = max(self.storage.track_duration(meeting_id, track) for track in tracks)

        # Publish only while the lease is held, then commit job and meeting together.
        await self._write(job.id, token)
        await asyncio.to_thread(
            self.storage.write_transcript, meeting_id, document.model_dump(mode="json")
        )
        async with self.sessionmaker() as session:
            now = utcnow()
            completed = await fenced_update(
                session,
                job.id,
                token,
                status="completed",
                stage="completed",
                progress=1.0,
                lease_token=None,
                completed_at=now,
            )
            if not completed:
                raise LeaseLost
            await session.execute(
                update(Meeting)
                .where(Meeting.id == meeting_id)
                .values(status="ready", primary_language=languages, duration=duration)
            )
            await session.commit()
        logger.info(
            "transcription job %s completed: %s segments, %s tracks",
            job.id,
            len(segments),
            len(tracks),
        )
        await self._schedule_brain(meeting_id, document.segments_sha256)
        await self._schedule_memory(meeting_id, document.segments_sha256)

    async def _schedule_memory(self, meeting_id: str, input_sha256: str) -> None:
        """Index the committed definitive transcript for Memory (docs/redis.md §3)."""
        if self.memory_queue is None:
            return
        try:
            async with self.sessionmaker() as session:
                index_job = await memory_jobs.create_or_reuse_index_job(
                    session,
                    meeting_id=meeting_id,
                    input_sha256=input_sha256,
                    settings=self.settings,
                )
                await session.commit()
            if index_job.status == "queued":
                await memory_jobs.publish(self.memory_queue, index_job.id, "index")
        except Exception as error:
            logger.warning("memory scheduling for %s failed: %s", meeting_id, type(error).__name__)

    async def _schedule_brain(self, meeting_id: str, input_sha256: str) -> None:
        """Brain runs only after the definitive transcript is committed (ADR 0002, 0008).

        The LLM settings are snapshotted on the job (ADR 0009). A Brain scheduling problem
        never affects the transcript that was just published.
        """
        if self.brain_queue is None:
            return
        try:
            runtime = runtime_settings.load(self.settings)
            async with self.sessionmaker() as session:
                brain_job = await brain_jobs.create_or_reuse(
                    session,
                    meeting_id=meeting_id,
                    input_sha256=input_sha256,
                    runtime=runtime,
                    settings=self.settings,
                )
                await session.commit()
            if brain_job.status == "queued":
                await brain_jobs.publish(self.brain_queue, brain_job.id)
        except Exception as error:
            logger.warning("brain scheduling for %s failed: %s", meeting_id, type(error).__name__)

    async def _transcribe_track(
        self,
        job: TranscriptionJob,
        token: str,
        track: Track,
        speaker_offset: int = 0,
        progress: TrackProgress | None = None,
    ) -> TrackResult:
        progress = progress or TrackProgress()
        path = self.storage.track_path(job.meeting_id, track)
        source_sha256 = await asyncio.to_thread(self.storage.tracks_sha256, job.meeting_id, [track])
        definitive = self.settings.asr_definitive_provider
        fallback = self.settings.asr_fallback_provider
        fallback_reason: str | None = None
        retryable = False
        try:
            engine = self._engine(definitive)
            raw = await asyncio.to_thread(engine.transcribe, path, progress.update)
        except ProviderError as error:
            retryable = not isinstance(error, ProviderConfigurationError)
            if not fallback or fallback == definitive:
                logger.warning("transcription job %s track %s: %s", job.id, track, error.code)
                raise JobFailure("ASR_FAILED", retryable=retryable) from None
            fallback_reason = error.code
            logger.warning(
                "transcription job %s track %s: %s, falling back to %s",
                job.id,
                track,
                error.code,
                fallback,
            )
            await self._write(job.id, token, stage="fallback")
            try:
                engine = self._engine(fallback)
                progress.fraction = 0.0  # the fallback starts the track again
                raw = await asyncio.to_thread(engine.transcribe, path, progress.update)
            except ProviderError as fallback_error:
                retryable = retryable or not isinstance(fallback_error, ProviderConfigurationError)
                logger.warning(
                    "transcription job %s track %s fallback: %s", job.id, track, fallback_error.code
                )
                raise JobFailure("ASR_FAILED", retryable=retryable) from None

        segments = normalize_segments(track, raw)
        diarization = await self._diarize(path, segments, speaker_offset)
        language = next((segment.language for segment in segments if segment.language), None)
        return TrackResult(
            segments=segments,
            provenance=TrackProvenance(
                track=track,
                source_sha256=source_sha256,
                provider=engine.name,
                model=engine.model,
                language=language,
                fallback_reason=fallback_reason,
                segment_count=len(segments),
                diarization=diarization,
            ),
        )

    async def _diarize(
        self, path, segments: list[TranscriptSegment], speaker_offset: int
    ) -> DiarizationProvenance | None:
        """Label speakers per track. Provider labels (MOSS) stay authoritative (ADR 0003).

        Labels continue numbering across tracks so they stay unique within the meeting, which
        keeps the derived attendee count correct (ADR 0011) without claiming that speakers on
        different tracks are different or the same people (ADR 0005).
        """
        if not segments:
            return None
        if any(segment.speaker for segment in segments):
            speakers = len({segment.speaker for segment in segments if segment.speaker})
            return DiarizationProvenance(
                provider="asr", model="asr", status="provider", speakers=speakers
            )
        if self.diarizer is None:
            return None
        spans = [SpeechSpan(segment.start, segment.end) for segment in segments]
        try:
            result = await asyncio.to_thread(self.diarizer.diarize, path, spans)
        except Exception as error:
            # Speaker labels are an enhancement: a diarization failure never fails the transcript.
            logger.warning("diarization failed: %s", type(error).__name__)
            return DiarizationProvenance(
                provider="local", model="unknown", status="unavailable", speakers=0
            )
        for segment, label in zip(segments, result.labels, strict=True):
            segment.speaker = None if label is None else speaker_label(speaker_offset + label)
        return DiarizationProvenance(
            provider=result.provider,
            model=result.model,
            status=result.status,
            speakers=result.speaker_count,
            parameters=result.parameters,
        )

    async def _with_heartbeat(self, job_id: str, token: str, work, progress=None):
        """Keep the lease fresh while a long provider call runs, and persist measured progress.

        Progress is written at most every PROGRESS_POLL_SECONDS and only when it grew by
        MIN_PROGRESS_STEP, so it stays monotonic and cheap; otherwise a plain heartbeat keeps
        the lease alive every `transcription_heartbeat_seconds`.
        """
        task = asyncio.ensure_future(work)
        heartbeat = self.settings.transcription_heartbeat_seconds
        poll = min(PROGRESS_POLL_SECONDS, heartbeat) if progress else heartbeat
        written = progress() if progress else 0.0
        since_beat = 0.0
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=poll)
                if done:
                    return task.result()
                since_beat += poll
                current = progress() if progress else written
                if current - written >= MIN_PROGRESS_STEP:
                    await self._write(job_id, token, progress=round(current, 4))
                    written, since_beat = current, 0.0
                elif since_beat >= heartbeat:
                    await self._write(job_id, token)
                    since_beat = 0.0
        except BaseException:
            if not task.done():
                task.cancel()
            raise

    async def _fail(self, job: TranscriptionJob, token: str, failure: JobFailure) -> None:
        async with self.sessionmaker() as session:
            current = await session.get(TranscriptionJob, job.id)
            if current is None or current.lease_token != token or current.status != "running":
                return
            retry = failure.retryable and current.attempts < current.max_attempts
            now = utcnow()
            values = {"lease_token": None, "error": failure.code, "track": None}
            if retry:
                values |= {"status": "queued", "stage": "retrying"}
            else:
                values |= {"status": "failed", "stage": "failed", "completed_at": now}
            if not await fenced_update(session, job.id, token, **values):
                return
            if not retry:
                # The audio and any previous transcript are preserved (ADR 0008). A meeting that
                # still has a valid transcript is "ready": it is readable, only the job failed.
                readable = await asyncio.to_thread(self._has_valid_transcript, job.meeting_id)
                await session.execute(
                    update(Meeting)
                    .where(Meeting.id == job.meeting_id)
                    .values(status="ready" if readable else "failed")
                )
            await session.commit()
        if retry:
            logger.warning("transcription job %s requeued: %s", job.id, failure.code)
            try:
                await self.queue.publish(job.id)
            except Exception as error:
                logger.warning(
                    "transcription job %s republish deferred: %s", job.id, type(error).__name__
                )
        else:
            logger.warning("transcription job %s failed: %s", job.id, failure.code)

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            job_ids = await reconcile(
                session,
                lease_seconds=self.settings.transcription_lease_seconds,
                republish_after_seconds=self.settings.transcription_reconcile_seconds,
                has_valid_transcript=self._has_valid_transcript,
            )
        for job_id in job_ids:
            await self.queue.publish(job_id)

    def _has_valid_transcript(self, meeting_id: str) -> bool:
        """True when the stored transcript is valid AND was made from the audio the meeting has
        now. A transcript of replaced audio must not be presented as the meeting's (ADR 0002)."""
        try:
            document = parse_definitive(self.storage.read_transcript(meeting_id))
            if document is None:
                return False
            tracks = self.storage.non_empty_tracks(meeting_id)
            return bool(tracks) and (
                document.provenance.input_sha256 == self.storage.tracks_sha256(meeting_id, tracks)
            )
        except (OSError, ValueError):
            return False


def build_diarizer(settings: Settings) -> DiarizationEngine | None:
    if settings.diarization_provider == "none":
        return None
    encoder = EcapaEncoder(
        settings.diarization_model, settings.diarization_cache_dir, settings.asr_device
    )
    return LocalDiarizationProvider(
        encoder,
        threshold=settings.diarization_threshold,
        min_speakers=settings.diarization_min_speakers,
        max_speakers=settings.diarization_max_speakers,
    )


def normalize_segments(track: Track, raw: list[AsrSegment]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for segment in sorted(raw, key=lambda item: (item.start, item.end)):
        text = segment.text.strip()
        if not text:
            continue
        start = max(0.0, float(segment.start))
        end = max(start, float(segment.end))
        segments.append(
            TranscriptSegment(
                id=f"{track}-{len(segments):05d}",
                start=start,
                end=end,
                text=text,
                track=track,
                language=segment.language,
                speaker=segment.speaker,
            )
        )
    return segments


async def run(settings: Settings, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    queue = RedisStreamQueue(redis, settings.transcription_queue_name, CONSUMER_GROUP)
    worker = TranscriptionWorker(
        create_sessionmaker(engine),
        MeetingStorage(settings.audio_storage_path),
        queue,
        settings,
        diarizer=build_diarizer(settings),
        brain_queue=RedisStreamQueue(redis, settings.brain_queue_name, "brain-workers"),
        memory_queue=RedisStreamQueue(
            redis, settings.memory_index_queue_name, "memory-index-workers"
        ),
    )
    consumer = f"{socket.gethostname()}"
    read_pending = True
    last_reconcile = 0.0
    logger.info("transcription worker started (consumer %s)", consumer)
    try:
        while not stop.is_set():
            try:
                await queue.ensure_group()
                if time.monotonic() - last_reconcile >= settings.transcription_reconcile_seconds:
                    await worker.reconcile()
                    last_reconcile = time.monotonic()
                messages = await queue.read(consumer, pending=read_pending)
                read_pending = read_pending and bool(messages)
                for message_id, job_id in messages:
                    try:
                        if job_id:
                            await worker.process(job_id)
                    finally:
                        await queue.ack(message_id)
            except (RedisError, OSError, SQLAlchemyError) as error:
                # Redis or PostgreSQL is down: wait and retry. A job interrupted by a database
                # outage keeps its lease and is recovered by reconciliation.
                logger.warning(
                    "transcription worker waiting for a datastore: %s", type(error).__name__
                )
                await asyncio.sleep(5)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
