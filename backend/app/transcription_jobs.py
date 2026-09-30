"""Durable TranscriptionJob lifecycle (ADR 0008, docs/redis.md).

A job is committed in PostgreSQL before its id is published. Claims and every later write
are fenced by a lease token so two consumers never process the same job.
"""

import asyncio
import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.asr import definitive_model_name
from app.config import Settings
from app.job_queue import JobQueue
from app.models import Meeting, TranscriptionJob, utcnow
from app.storage import MeetingStorage

logger = logging.getLogger("advera.transcription_jobs")

ACTIVE_STATUSES = ("queued", "running")


def idempotency_key(meeting_id: str, input_sha256: str, provider: str, model: str) -> str:
    raw = f"{meeting_id}:{input_sha256}:{provider}:{model}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def latest_job(session: AsyncSession, meeting_id: str) -> TranscriptionJob | None:
    result = await session.execute(
        select(TranscriptionJob)
        .where(TranscriptionJob.meeting_id == meeting_id)
        .order_by(TranscriptionJob.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def active_job(session: AsyncSession, meeting_id: str) -> TranscriptionJob | None:
    result = await session.execute(
        select(TranscriptionJob)
        .where(
            TranscriptionJob.meeting_id == meeting_id,
            TranscriptionJob.status.in_(ACTIVE_STATUSES),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_or_reuse_job(
    session: AsyncSession,
    *,
    meeting_id: str,
    input_sha256: str,
    total_tracks: int,
    provider: str,
    model: str,
    max_attempts: int,
) -> TranscriptionJob:
    """Create a queued job, or reuse the job with the same idempotency key.

    A failed job with the same key is reset to `queued`; a queued, running or completed job is
    returned unchanged. The caller commits and then publishes when the job is `queued`.
    """
    key = idempotency_key(meeting_id, input_sha256, provider, model)
    existing = (
        await session.execute(
            select(TranscriptionJob).where(TranscriptionJob.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing is None:
        job = TranscriptionJob(
            meeting_id=meeting_id,
            idempotency_key=key,
            input_sha256=input_sha256,
            provider=provider,
            model=model,
            status="queued",
            max_attempts=max_attempts,
            total_tracks=total_tracks,
        )
        session.add(job)
        await session.flush()
        return job
    if existing.status == "failed":
        existing.status = "queued"
        existing.attempts = 0
        existing.max_attempts = max_attempts
        existing.progress = 0.0
        existing.stage = None
        existing.track = None
        existing.processed_tracks = 0
        existing.total_tracks = total_tracks
        existing.lease_token = None
        existing.error = None
        existing.completed_at = None
        existing.updated_at = utcnow()
    return existing


async def queue_meeting_transcription(
    session: AsyncSession, storage: MeetingStorage, settings: Settings, meeting: Meeting
) -> TranscriptionJob:
    """Create or reuse the definitive job for the meeting's stored tracks and commit it.

    Shared by media import and capture stop, so both use one durable boundary (ADR 0008).
    The caller publishes the job id after this commit when the job is `queued`.
    """
    tracks = storage.non_empty_tracks(meeting.id)
    input_sha256 = await asyncio.to_thread(storage.tracks_sha256, meeting.id, tracks)
    provider = settings.asr_definitive_provider
    job = await create_or_reuse_job(
        session,
        meeting_id=meeting.id,
        input_sha256=input_sha256,
        total_tracks=len(tracks),
        provider=provider,
        model=definitive_model_name(provider, settings),
        max_attempts=settings.transcription_max_attempts,
    )
    meeting.status = "ready" if job.status == "completed" else "processing"
    await session.commit()
    return job


async def publish(queue: JobQueue, job_id: str) -> bool:
    """Publish a committed job. On failure the job stays queued for reconciliation."""
    try:
        await queue.publish(job_id)
    except Exception as error:  # Redis unavailable: PostgreSQL keeps the durable state
        logger.warning("transcription job %s not published: %s", job_id, type(error).__name__)
        return False
    return True


async def claim(session: AsyncSession, job_id: str, lease_token: str) -> bool:
    now = utcnow()
    result = await session.execute(
        update(TranscriptionJob)
        .where(
            TranscriptionJob.id == job_id,
            TranscriptionJob.status == "queued",
            TranscriptionJob.attempts < TranscriptionJob.max_attempts,
        )
        .values(
            status="running",
            lease_token=lease_token,
            attempts=TranscriptionJob.attempts + 1,
            stage="transcribing",
            track=None,
            processed_tracks=0,
            progress=0.0,
            error=None,
            started_at=now,
            updated_at=now,
        )
    )
    await session.commit()
    return result.rowcount == 1


async def fenced_update(session: AsyncSession, job_id: str, token: str, /, **values: Any) -> bool:
    """Update a running job only while this worker still holds its lease `token`."""
    result = await session.execute(
        update(TranscriptionJob)
        .where(
            TranscriptionJob.id == job_id,
            TranscriptionJob.lease_token == token,
            TranscriptionJob.status == "running",
        )
        .values(**values, updated_at=utcnow())
    )
    return result.rowcount == 1


async def reconcile(
    session: AsyncSession,
    *,
    lease_seconds: int,
    republish_after_seconds: int,
    now: datetime | None = None,
    has_valid_transcript: Callable[[str], bool] | None = None,
) -> list[str]:
    """Recover stale leases and return queued job ids whose message may have been lost.

    Each stale job is recovered with an UPDATE that repeats the staleness test, so a heartbeat
    that lands between the read and the write keeps its lease instead of being overwritten.
    """
    now = now or utcnow()
    cutoff = now - timedelta(seconds=lease_seconds)
    stale = (
        await session.execute(
            select(
                TranscriptionJob.id,
                TranscriptionJob.meeting_id,
                TranscriptionJob.attempts,
                TranscriptionJob.max_attempts,
            ).where(TranscriptionJob.status == "running", TranscriptionJob.updated_at < cutoff)
        )
    ).all()
    job_ids: list[str] = []
    for job_id, meeting_id, attempts, max_attempts in stale:
        exhausted = attempts >= max_attempts
        values = (
            {"status": "failed", "stage": "failed", "error": "LEASE_EXPIRED", "completed_at": now}
            if exhausted
            else {"status": "queued", "stage": "requeued"}
        )
        result = await session.execute(
            update(TranscriptionJob)
            .where(
                TranscriptionJob.id == job_id,
                TranscriptionJob.status == "running",
                TranscriptionJob.updated_at < cutoff,
            )
            .values(**values, lease_token=None, updated_at=now)
        )
        if result.rowcount != 1:
            continue  # the worker beat in the meantime: it still owns the job
        if exhausted:
            # A meeting that still has a valid transcript stays readable (ADR 0008).
            keeps = has_valid_transcript is not None and await asyncio.to_thread(
                has_valid_transcript, meeting_id
            )
            await session.execute(
                update(Meeting)
                .where(Meeting.id == meeting_id)
                .values(status="ready" if keeps else "failed")
            )
            logger.warning("transcription job %s failed: LEASE_EXPIRED", job_id)
        else:
            job_ids.append(job_id)
            logger.info("transcription job %s requeued after stale lease", job_id)
    await session.flush()

    queued = (
        await session.execute(
            select(TranscriptionJob).where(
                TranscriptionJob.status == "queued",
                TranscriptionJob.updated_at < now - timedelta(seconds=republish_after_seconds),
            )
        )
    ).scalars()
    for job in queued:
        job.updated_at = now
        job_ids.append(job.id)
    await session.commit()
    return job_ids
