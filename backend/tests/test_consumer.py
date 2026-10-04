"""The shared consumer loop survives a datastore outage (Redis or PostgreSQL)."""

import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from app import consumer
from app.config import Settings


class FakeQueue:
    """A queue that hands out the given messages once, then nothing."""

    def __init__(self, messages: list[tuple[str, str]], read_fails: list[Exception] | None = None):
        self.messages = list(messages)
        self.read_fails = list(read_fails or [])
        self.acked: list[str] = []
        self.stale: list[tuple[str, str]] = []
        self.claimed_after: int | None = None

    async def ensure_group(self) -> None:
        pass

    async def read(self, _consumer: str, *, pending: bool = False):
        if self.read_fails:
            raise self.read_fails.pop(0)
        await REAL_SLEEP(0)
        return [self.messages.pop(0)] if self.messages and not pending else []

    async def ack(self, message_id: str) -> None:
        self.acked.append(message_id)

    async def claim_stale(self, _consumer: str, min_idle_ms: int):
        self.claimed_after = min_idle_ms
        stale, self.stale = self.stale, []
        return stale


class FakeWorker:
    def __init__(self, reconcile_fails: list[Exception] | None = None):
        self.reconcile_fails = list(reconcile_fails or [])
        self.processed: list[str] = []
        self.reconciles = 0

    async def reconcile(self) -> None:
        self.reconciles += 1
        if self.reconcile_fails:
            raise self.reconcile_fails.pop(0)

    async def process(self, job_id: str) -> None:
        self.processed.append(job_id)


def db_down() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


REAL_SLEEP = asyncio.sleep


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The five-second wait after an outage is skipped; it still yields to the event loop."""

    async def instant(_seconds: float) -> None:
        await REAL_SLEEP(0)

    monkeypatch.setattr(consumer.asyncio, "sleep", instant)


async def run_until(queue, worker, done) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(
        consumer.consume(queue, worker, Settings(_env_file=None), stop, name="test")
    )
    try:
        for _ in range(200):
            if done():
                break
            await REAL_SLEEP(0.01)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)


async def test_a_postgresql_outage_during_reconciliation_does_not_end_the_worker():
    # Before this fix the exception left the loop and took the whole worker process down.
    queue = FakeQueue([("1-0", "job-a")])
    worker = FakeWorker(reconcile_fails=[db_down(), db_down()])
    await run_until(queue, worker, lambda: worker.processed == ["job-a"])
    assert worker.processed == ["job-a"] and queue.acked == ["1-0"]
    assert worker.reconciles >= 3  # failed twice, then recovered


async def test_a_redis_outage_does_not_end_the_worker_either():
    queue = FakeQueue([("1-0", "job-a")], read_fails=[RedisConnectionError("down")])
    worker = FakeWorker()
    await run_until(queue, worker, lambda: worker.processed == ["job-a"])
    assert worker.processed == ["job-a"]


async def test_a_job_that_fails_on_the_database_is_acknowledged_and_the_loop_goes_on():
    class Failing(FakeWorker):
        async def process(self, job_id: str) -> None:
            if job_id == "job-a":
                raise db_down()  # even recording the failure could not reach PostgreSQL
            await super().process(job_id)

    queue = FakeQueue([("1-0", "job-a"), ("2-0", "job-b")])
    worker = Failing()
    await run_until(queue, worker, lambda: worker.processed == ["job-b"])
    # The first message is acknowledged (its job keeps its lease and reconcile() recovers it).
    assert queue.acked == ["1-0", "2-0"] and worker.processed == ["job-b"]


async def test_messages_left_by_a_dead_consumer_are_taken_over_and_acknowledged():
    queue = FakeQueue([])
    queue.stale = [("9-0", "orphan-job")]
    worker = FakeWorker()
    await run_until(queue, worker, lambda: worker.processed == ["orphan-job"])
    assert queue.acked == ["9-0"]
    # Idle for longer than the longest lease (20 minutes for Brain), so a live job is not taken.
    assert queue.claimed_after == 1_200_000
