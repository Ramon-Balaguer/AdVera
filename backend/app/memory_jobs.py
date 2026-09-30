"""Memory index jobs and query runs (docs/redis.md §3-4).

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

from app.config import Settings
from app.job_queue import JobQueue
from app.memory_indexing import PROJECTION_VERSION
from app.models import MemoryIndexJob, MemoryQueryRun, utcnow
from app.runtime_settings import RuntimeSettings

logger = logging.getLogger("advera.memory_jobs")


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
) -> MemoryIndexJob:
    provider = "sentence-transformers"
    key = index_key(meeting_id, input_sha256, provider, settings.embedding_model)
    job = (
        await session.execute(select(MemoryIndexJob).where(MemoryIndexJob.idempotency_key == key))
    ).scalar_one_or_none()
    if job is None:
        job = MemoryIndexJob(
            meeting_id=meeting_id,
            idempotency_key=key,
            input_sha256=input_sha256,
            projection_version=PROJECTION_VERSION,
            provider=provider,
            model=settings.embedding_model,
            model_version="1",
            status="queued",
            max_attempts=settings.memory_max_attempts,
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
) -> MemoryQueryRun:
    run = MemoryQueryRun(
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
        max_attempts=settings.memory_query_max_attempts,
    )
    session.add(run)
    await session.flush()
    return run


async def publish(queue: JobQueue, job_id: str, kind: str) -> bool:
    try:
        await queue.publish(job_id)
    except Exception as error:
        logger.warning("memory %s %s not published: %s", kind, job_id, type(error).__name__)
        return False
    return True
