"""Brain index jobs and query runs (docs/redis.md §3-4).

An index job is keyed by meeting, transcript hash, embedding provider/model and projection
version, so re-requesting the same input reuses one job. A query run is committed before its
id is published; if Redis is unavailable it is failed explicitly (`QUEUE_UNAVAILABLE`) rather
than left queued forever.
"""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain_indexing import PROJECTION_VERSION
from app.config import Settings
from app.job_queue import JobQueue
from app.models import BrainIndexJob, BrainQueryRun, SummaryJob, utcnow
from app.runtime_settings import RuntimeSettings

logger = logging.getLogger("advera.brain_jobs")


def index_key(meeting_id: str, input_sha256: str, provider: str, model: str) -> str:
    raw = f"{meeting_id}:{input_sha256}:{provider}:{model}:{PROJECTION_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_or_reuse_index_job(
    session: AsyncSession,
    *,
    meeting_id: str,
    input_sha256: str,
    settings: Settings,
    force: bool = False,
) -> BrainIndexJob:
    provider = "sentence-transformers"
    key = index_key(meeting_id, input_sha256, provider, settings.embedding_model)
    job = (
        await session.execute(select(BrainIndexJob).where(BrainIndexJob.idempotency_key == key))
    ).scalar_one_or_none()
    if job is None:
        job = BrainIndexJob(
            meeting_id=meeting_id,
            idempotency_key=key,
            input_sha256=input_sha256,
            projection_version=PROJECTION_VERSION,
            provider=provider,
            model=settings.embedding_model,
            model_version="1",
            status="queued",
            max_attempts=settings.brain_max_attempts,
        )
        session.add(job)
        await session.flush()
        return job
    if job.status == "failed" or (force and job.status == "completed"):
        job.status = "queued"
        job.attempts = 0
        job.lease_token = None
        job.error = None
        job.completed_at = None
        job.updated_at = utcnow()
    return job


CONCEPT_PROJECTION_VERSION = "brain-concepts-v2"  # v2: also projects the facts (ADR 0024)


def concept_key(meeting_id: str, summary_job_id: str, input_sha256: str) -> str:
    raw = f"concepts:{meeting_id}:{summary_job_id}:{input_sha256}:{CONCEPT_PROJECTION_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_or_reuse_concept_job(
    session: AsyncSession, *, summary_job: SummaryJob, settings: Settings, force: bool = False
) -> BrainIndexJob:
    """The job that projects one completed Summary extraction into the concept graph (ADR 0019).

    It is tied to the Summary job (`source_summary_job_id`), so a later extraction for the same
    meeting makes an older job stale instead of being overwritten by it.
    """
    key = concept_key(summary_job.meeting_id, summary_job.id, summary_job.input_sha256)
    job = (
        await session.execute(select(BrainIndexJob).where(BrainIndexJob.idempotency_key == key))
    ).scalar_one_or_none()
    if job is None:
        job = BrainIndexJob(
            meeting_id=summary_job.meeting_id,
            source_summary_job_id=summary_job.id,
            kind="concepts",
            idempotency_key=key,
            input_sha256=summary_job.input_sha256,
            projection_version=CONCEPT_PROJECTION_VERSION,
            provider="summary",
            model=summary_job.model,
            model_version=summary_job.prompt_version,
            status="queued",
            max_attempts=settings.brain_max_attempts,
        )
        session.add(job)
        await session.flush()
        return job
    if job.status == "failed" or (force and job.status == "completed"):
        job.status = "queued"
        job.attempts = 0
        job.lease_token = None
        job.error = None
        job.completed_at = None
        job.updated_at = utcnow()
    return job


async def schedule_concept_projection(
    sessionmaker, queue: JobQueue, settings: Settings, summary_job
):
    """Summary completion hook. A scheduling problem never affects the extraction just stored."""
    try:
        async with sessionmaker() as session:
            job = await create_or_reuse_concept_job(
                session, summary_job=summary_job, settings=settings
            )
            await session.commit()
        if job.status == "queued":
            await publish(queue, job.id, "concepts")
    except Exception as error:
        logger.warning(
            "concept projection scheduling for %s failed: %s", summary_job.id, type(error).__name__
        )


def query_hash(query: str, filters: dict[str, Any], top_k: int) -> str:
    raw = json.dumps({"q": query, "f": filters, "k": top_k}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_query_run(
    session: AsyncSession,
    *,
    query: str,
    filters: dict[str, Any],
    top_k: int,
    runtime: RuntimeSettings,
    settings: Settings,
) -> BrainQueryRun:
    run = BrainQueryRun(
        query=query,
        status="queued",
        input_sha256=query_hash(query, filters, top_k),
        top_k=top_k,
        filters=filters,
        provider=runtime.llm_provider,
        model=runtime.llm_model,
        model_version=settings.embedding_model,
        base_url=runtime.llm_base_url,
        language=runtime.llm_output_language,
        max_attempts=settings.brain_query_max_attempts,
    )
    session.add(run)
    await session.flush()
    return run


async def publish(queue: JobQueue, job_id: str, kind: str) -> bool:
    try:
        await queue.publish(job_id)
    except Exception as error:
        logger.warning("brain %s %s not published: %s", kind, job_id, type(error).__name__)
        return False
    return True
