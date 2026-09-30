"""Durable BrainJob lifecycle (docs/redis.md §2; ADR 0008, 0009).

A Brain job is created only after the definitive transcript is saved and committed. Its
idempotency key combines meeting, transcript hash, provider, model, prompt version and output
language, so repeating a request never duplicates work for the same input, while a different
language is a distinct job (ADR 0009).
"""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain import PROMPT_VERSION
from app.config import Settings
from app.job_queue import JobQueue
from app.models import BrainExtraction, BrainJob, utcnow
from app.runtime_settings import RuntimeSettings

logger = logging.getLogger("advera.brain_jobs")

ACTIVE_STATUSES = ("queued", "running")


def idempotency_key(
    meeting_id: str, input_sha256: str, provider: str, model: str, prompt: str, language: str
) -> str:
    raw = f"{meeting_id}:{input_sha256}:{provider}:{model}:{prompt}:{language}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_or_reuse(
    session: AsyncSession,
    *,
    meeting_id: str,
    input_sha256: str,
    runtime: RuntimeSettings,
    settings: Settings,
    force: bool = False,
) -> BrainJob:
    """Create a queued job for this input, or reuse it. `force` re-queues a finished job."""
    key = idempotency_key(
        meeting_id,
        input_sha256,
        runtime.llm_provider,
        runtime.llm_model,
        PROMPT_VERSION,
        runtime.llm_output_language,
    )
    job = (
        await session.execute(select(BrainJob).where(BrainJob.idempotency_key == key))
    ).scalar_one_or_none()
    if job is None:
        job = BrainJob(
            meeting_id=meeting_id,
            idempotency_key=key,
            input_sha256=input_sha256,
            provider=runtime.llm_provider,
            model=runtime.llm_model,
            base_url=runtime.llm_base_url,
            prompt_version=PROMPT_VERSION,
            language=runtime.llm_output_language,
            status="queued",
            max_attempts=settings.brain_max_attempts,
        )
        session.add(job)
        await session.flush()
        return job
    if job.status == "failed" or (force and job.status == "completed"):
        job.status = "queued"
        job.attempts = 0
        job.max_attempts = settings.brain_max_attempts
        job.base_url = runtime.llm_base_url
        job.lease_token = None
        job.error = None
        job.completed_at = None
        job.updated_at = utcnow()
        if force:
            existing = (
                await session.execute(
                    select(BrainExtraction).where(BrainExtraction.job_id == job.id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                await session.delete(existing)
    return job


async def latest_job(session: AsyncSession, meeting_id: str) -> BrainJob | None:
    return (
        await session.execute(
            select(BrainJob)
            .where(BrainJob.meeting_id == meeting_id)
            .order_by(BrainJob.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def active_job(session: AsyncSession, meeting_id: str) -> BrainJob | None:
    return (
        await session.execute(
            select(BrainJob)
            .where(BrainJob.meeting_id == meeting_id, BrainJob.status.in_(ACTIVE_STATUSES))
            .limit(1)
        )
    ).scalar_one_or_none()


async def publish(queue: JobQueue, job_id: str) -> bool:
    try:
        await queue.publish(job_id)
    except Exception as error:  # Redis unavailable: the queued job is reconciled later
        logger.warning("brain job %s not published: %s", job_id, type(error).__name__)
        return False
    return True
