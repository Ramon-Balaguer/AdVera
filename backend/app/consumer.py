"""The consumer loop shared by the Summary, Brain and transcription workers (docs/redis.md).

It replays the consumer's own pending messages, reconciles stale jobs against PostgreSQL
periodically and survives an outage of either datastore. Redis is transport only (ADR 0008):
PostgreSQL holds the job state, so a job interrupted by an outage keeps its lease and is
recovered by `reconcile()`; the loop just waits and goes on instead of ending the process.
"""

import asyncio
import contextlib
import json
import logging
import os
import socket
import time
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.job_queue import RedisStreamQueue

logger = logging.getLogger("advera.consumer")

# Either datastore being down is transient: reading, acknowledging, reconciling and recording a
# failure all touch Redis or PostgreSQL, so any of them can raise one of these.
RECOVERABLE = (RedisError, OSError, SQLAlchemyError)
OUTAGE_WAIT_SECONDS = 5
# A message idle for longer than a lease belongs to a consumer that is gone.
STALE_AFTER_FACTOR = 1
HEARTBEAT_PREFIX = "advera:heartbeat:"
HEARTBEAT_SECONDS = 5
HEARTBEAT_TTL_SECONDS = 15


def lease_ms(settings: Settings) -> int:
    return int(max(settings.summary_lease_seconds, settings.transcription_lease_seconds) * 1000)


async def _handle(messages, queue, worker, heartbeat: "Heartbeat | None" = None) -> None:
    for message_id, job_id in messages:
        try:
            if job_id:
                if heartbeat:
                    heartbeat.job_id = job_id
                await worker.process(job_id)
        finally:
            if heartbeat:
                heartbeat.job_id = None
            await queue.ack(message_id)


class Heartbeat:
    """Tells the monitor page that this loop is alive (docs/redis.md).

    Every few seconds the loop writes `advera:heartbeat:<worker>:<host>` with a short expiry, so
    the key is there while the process lives and disappears soon after it stops or dies. The
    job being processed is included. A failing Redis never stops the worker: the heartbeat
    just goes missing, which is what the page should show.
    """

    def __init__(self, redis, worker: str) -> None:
        self.redis = redis
        self.worker = worker
        self.host = socket.gethostname()
        self.key = f"{HEARTBEAT_PREFIX}{worker}:{self.host}"
        self.started_at = datetime.now(UTC).isoformat()
        self.job_id: str | None = None

    async def beat(self) -> None:
        value = json.dumps(
            {
                "worker": self.worker,
                "host": self.host,
                "pid": os.getpid(),
                "started_at": self.started_at,
                "job_id": self.job_id,
            }
        )
        await self.redis.set(self.key, value, ex=HEARTBEAT_TTL_SECONDS)

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                try:
                    await self.beat()
                except RECOVERABLE as error:
                    logger.debug("%s heartbeat not written: %s", self.worker, type(error).__name__)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
        finally:
            with contextlib.suppress(*RECOVERABLE):
                await self.redis.delete(self.key)  # a clean stop shows as down at once


async def consume(
    queue: RedisStreamQueue,
    worker,
    settings: Settings,
    stop: asyncio.Event,
    name: str = "worker",
) -> None:
    """`name` identifies the loop in the logs and in the heartbeat the monitor reads."""
    redis = getattr(queue, "redis", None)
    heartbeat = Heartbeat(redis, name) if redis is not None else None
    beating = asyncio.create_task(heartbeat.run(stop)) if heartbeat else None
    try:
        await _consume(queue, worker, settings, stop, name, heartbeat)
    finally:
        if beating:
            beating.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beating


async def _consume(queue, worker, settings, stop, name, heartbeat) -> None:
    consumer = socket.gethostname()
    read_pending = True
    last_reconcile = 0.0
    while not stop.is_set():
        try:
            await queue.ensure_group()
            if time.monotonic() - last_reconcile >= settings.transcription_reconcile_seconds:
                await worker.reconcile()
                await _handle(
                    await queue.claim_stale(consumer, STALE_AFTER_FACTOR * lease_ms(settings)),
                    queue,
                    worker,
                    heartbeat,
                )
                last_reconcile = time.monotonic()
            messages = await queue.read(consumer, pending=read_pending)
            read_pending = read_pending and bool(messages)
            await _handle(messages, queue, worker, heartbeat)
        except RECOVERABLE as error:
            logger.warning("%s worker waiting for a datastore: %s", name, type(error).__name__)
            await asyncio.sleep(OUTAGE_WAIT_SECONDS)
