"""The monitor's decisions about workers and queues, and the heartbeat behind them."""

import asyncio
import json

from redis.exceptions import ConnectionError as RedisConnectionError

from app import monitor_api
from app.consumer import HEARTBEAT_PREFIX, HEARTBEAT_TTL_SECONDS, Heartbeat


def beat(worker, **extra):
    return {
        "worker": worker,
        "host": "h1",
        "pid": 7,
        "started_at": "2026-10-04T10:00:00+00:00",
        **extra,
    }


def by_name(statuses):
    return {status.name: status for status in statuses}


def test_a_worker_with_a_heartbeat_is_up_and_one_without_is_down():
    workers = by_name(monitor_api.worker_states([beat("summary", job_id="job-1")]))
    assert workers["summary"].state == "up"
    assert workers["summary"].instances[0].job_id == "job-1"
    assert workers["summary"].since is not None
    assert [w.state for n, w in workers.items() if n != "summary"] == ["down"] * 3


def test_when_the_heartbeats_cannot_be_read_no_worker_is_called_down():
    assert {w.state for w in monitor_api.worker_states(None)} == {"unknown"}


def test_a_queue_is_stalled_only_when_work_is_waiting_and_its_worker_is_down():
    up, down = (
        by_name(monitor_api.worker_states([beat("summary")]))["summary"],
        by_name(monitor_api.worker_states([]))["summary"],
    )
    assert monitor_api.queue_state(down, queued=2, pending=0) == "stalled"
    assert monitor_api.queue_state(down, queued=0, pending=0) == "ok"
    assert monitor_api.queue_state(up, queued=2, pending=0) == "busy"
    assert monitor_api.queue_state(up, queued=0, pending=1) == "busy"
    assert monitor_api.queue_state(up, queued=0, pending=0) == "ok"
    unknown = by_name(monitor_api.worker_states(None))["summary"]
    assert monitor_api.queue_state(unknown, queued=5, pending=0) == "unknown"


class FakeRedis:
    def __init__(self, fail=False):
        self.values, self.expiries, self.fail = {}, {}, fail

    async def set(self, key, value, ex=None):
        if self.fail:
            raise RedisConnectionError("down")
        self.values[key], self.expiries[key] = value, ex

    async def delete(self, key):
        self.values.pop(key, None)


async def test_the_heartbeat_names_the_loop_the_host_and_the_job_and_expires():
    redis = FakeRedis()
    heartbeat = Heartbeat(redis, "brain-index")
    heartbeat.job_id = "job-9"
    await heartbeat.beat()
    [(key, value)] = redis.values.items()
    assert key.startswith(f"{HEARTBEAT_PREFIX}brain-index:")
    assert json.loads(value)["job_id"] == "job-9" and json.loads(value)["worker"] == "brain-index"
    assert redis.expiries[key] == HEARTBEAT_TTL_SECONDS


async def test_a_clean_stop_removes_the_heartbeat_at_once():
    redis = FakeRedis()
    heartbeat = Heartbeat(redis, "summary")
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat.run(stop))
    for _ in range(100):
        if redis.values:
            break
        await asyncio.sleep(0.01)
    assert redis.values
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert not redis.values


async def test_a_redis_failure_never_stops_the_heartbeat_loop():
    heartbeat = Heartbeat(FakeRedis(fail=True), "summary")
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat.run(stop))
    await asyncio.sleep(0.05)
    assert not task.done()  # it keeps trying; the key simply is not there
    stop.set()
    await asyncio.wait_for(task, timeout=5)
