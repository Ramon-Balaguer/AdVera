"""Lease-fenced job lifecycle shared by the Brain and Memory workers (docs/redis.md).

PostgreSQL is the source of truth: a job is claimed with an atomic conditional UPDATE, every
later write is fenced by the lease token, stale leases are requeued or failed, and queued jobs
whose Redis message may have been lost are republished by reconciliation.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import utcnow


class LeaseLost(Exception):
    pass


async def claim(
    session: AsyncSession, model: Any, job_id: str, token: str, *, running_status: str = "running"
) -> bool:
    now = utcnow()
    result = await session.execute(
        update(model)
        .where(model.id == job_id, model.status == "queued", model.attempts < model.max_attempts)
        .values(
            status=running_status,
            lease_token=token,
            attempts=model.attempts + 1,
            error=None,
            started_at=now,
            updated_at=now,
        )
    )
    await session.commit()
    return result.rowcount == 1


async def fenced_update(
    session: AsyncSession,
    model: Any,
    job_id: str,
    token: str,
    /,
    running_statuses: Sequence[str] = ("running",),
    **values: Any,
) -> bool:
    result = await session.execute(
        update(model)
        .where(
            model.id == job_id,
            model.lease_token == token,
            model.status.in_(tuple(running_statuses)),
        )
        .values(**values, updated_at=utcnow())
    )
    return result.rowcount == 1


async def reconcile(
    session: AsyncSession,
    model: Any,
    *,
    lease_seconds: int,
    republish_after_seconds: int,
    running_statuses: Sequence[str] = ("running",),
    now: datetime | None = None,
) -> list[str]:
    """Requeue or fail stale leases; return queued ids to republish.

    Each stale job is recovered with an UPDATE that repeats the staleness test, so a heartbeat
    that lands between the read and the write keeps its lease instead of being overwritten.
    """
    now = now or utcnow()
    cutoff = now - timedelta(seconds=lease_seconds)
    stale = (
        await session.execute(
            select(model.id, model.attempts, model.max_attempts).where(
                model.status.in_(tuple(running_statuses)), model.updated_at < cutoff
            )
        )
    ).all()
    job_ids: list[str] = []
    for job_id, attempts, max_attempts in stale:
        exhausted = attempts >= max_attempts
        values = (
            {"status": "failed", "error": "LEASE_EXPIRED", "completed_at": now}
            if exhausted
            else {"status": "queued"}
        )
        result = await session.execute(
            update(model)
            .where(
                model.id == job_id,
                model.status.in_(tuple(running_statuses)),
                model.updated_at < cutoff,
            )
            .values(**values, lease_token=None, updated_at=now)
        )
        if result.rowcount == 1 and not exhausted:
            job_ids.append(job_id)
    await session.flush()
    queued = (
        await session.execute(
            select(model).where(
                model.status == "queued",
                model.updated_at < now - timedelta(seconds=republish_after_seconds),
            )
        )
    ).scalars()
    for job in queued:
        job.updated_at = now
        job_ids.append(job.id)
    await session.commit()
    return job_ids


async def with_heartbeat(
    work: Awaitable, beat: Callable[[], Awaitable[None]], interval: float
) -> Any:
    """Run `work`, calling `beat` every `interval` seconds to keep the lease fresh."""
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                return task.result()
            await beat()
    except BaseException:
        if not task.done():
            task.cancel()
        raise
