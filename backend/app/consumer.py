"""The consumer loop shared by the Brain, Memory and transcription workers (docs/redis.md).

It replays the consumer's own pending messages, reconciles stale jobs against PostgreSQL
periodically and survives an outage of either datastore. Redis is transport only (ADR 0008):
PostgreSQL holds the job state, so a job interrupted by an outage keeps its lease and is
recovered by `reconcile()`; the loop just waits and goes on instead of ending the process.
"""

import asyncio
import logging
import socket
import time

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


def lease_ms(settings: Settings) -> int:
    return int(max(settings.brain_lease_seconds, settings.transcription_lease_seconds) * 1000)


async def _handle(messages, queue, worker) -> None:
    for message_id, job_id in messages:
        try:
            if job_id:
                await worker.process(job_id)
        finally:
            await queue.ack(message_id)


async def consume(
    queue: RedisStreamQueue,
    worker,
    settings: Settings,
    stop: asyncio.Event,
    name: str = "worker",
) -> None:
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
                )
                last_reconcile = time.monotonic()
            messages = await queue.read(consumer, pending=read_pending)
            read_pending = read_pending and bool(messages)
            await _handle(messages, queue, worker)
        except RECOVERABLE as error:
            logger.warning("%s waiting for a datastore: %s", name, type(error).__name__)
            await asyncio.sleep(OUTAGE_WAIT_SECONDS)
