"""The Redis stream queue stays small and recovers messages of a consumer that died."""

import asyncio
import uuid

import pytest

from app import job_queue
from app.job_queue import RedisStreamQueue

pytestmark = pytest.mark.integration


@pytest.fixture
async def queue(redis):
    stream = f"advera:test:queue:{uuid.uuid4().hex}"
    queue = RedisStreamQueue(redis, stream, "test-workers")
    await queue.ensure_group()
    yield queue
    await redis.delete(stream)


async def test_the_stream_is_bounded_whatever_is_published(queue, monkeypatch):
    monkeypatch.setattr(job_queue, "STREAM_MAXLEN", 100)
    for index in range(1_000):
        await queue.publish(f"job-{index}")
    # Trimming is approximate (whole blocks), so allow a little over the limit.
    assert await queue.redis.xlen(queue.stream) < 300


async def test_an_acknowledged_message_leaves_the_stream_and_the_pending_list(queue):
    await queue.publish("job-a")
    [(message_id, job_id)] = await queue.read("worker-1")
    assert job_id == "job-a"
    assert (await queue.redis.xpending(queue.stream, queue.group))["pending"] == 1

    await queue.ack(message_id)

    assert await queue.redis.xlen(queue.stream) == 0
    assert (await queue.redis.xpending(queue.stream, queue.group))["pending"] == 0


async def test_a_message_never_acknowledged_by_a_dead_consumer_is_taken_over(queue):
    await queue.publish("job-a")
    [(message_id, _)] = await queue.read("dead-container")
    await asyncio.sleep(0.05)

    taken = await queue.claim_stale("worker-2", min_idle_ms=10)

    assert taken == [(message_id, "job-a")]
    await queue.ack(message_id)
    assert (await queue.redis.xpending(queue.stream, queue.group))["pending"] == 0


async def test_a_recent_message_is_not_taken_from_a_consumer_that_may_still_be_working(queue):
    await queue.publish("job-a")
    await queue.read("busy-worker")

    assert await queue.claim_stale("worker-2", min_idle_ms=60_000) == []
