"""GET /api/monitor against real PostgreSQL and Redis."""

import json
import uuid

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from app import monitor_api
from app.consumer import HEARTBEAT_PREFIX
from app.models import BrainQueryRun
from tests.integration.test_import_transcription import create_meeting, import_wav

pytestmark = pytest.mark.integration


@pytest.fixture
async def heartbeats(redis):
    """Writes heartbeats like the workers do, and removes them afterwards."""
    keys = []

    async def write(worker, **extra):
        key = f"{HEARTBEAT_PREFIX}{worker}:test-{uuid.uuid4().hex[:6]}"
        keys.append(key)
        value = {
            "worker": worker,
            "host": "test-host",
            "pid": 1,
            "started_at": "2026-10-04T10:00:00+00:00",
        }
        await redis.set(key, json.dumps(value | extra), ex=30)

    # Other runs (or the real workers on this Redis) must not leak into these tests.
    for key in [key async for key in redis.scan_iter(match=f"{HEARTBEAT_PREFIX}*")]:
        await redis.delete(key)
    yield write
    for key in keys:
        await redis.delete(key)


def monitor(api):
    response = api.get("/api/monitor")
    assert response.status_code == 200
    return response.json()


def named(items):
    return {item["name"]: item for item in items}


async def test_an_idle_system_with_all_workers_up_is_all_ok(api, heartbeats):
    for worker in monitor_api.WORKERS:
        await heartbeats(worker)
    body = monitor(api)

    assert {s["name"]: s["ok"] for s in body["services"]} == {
        "api": True,
        "redis": True,
        "postgres": True,
    }
    assert {w["state"] for w in body["workers"]} == {"up"}
    assert {q["state"] for q in body["queues"]} == {"ok"}
    assert [j["queued"] for j in body["jobs"]] == [0, 0, 0, 0]


async def test_a_worker_shows_the_job_it_is_working_on_and_a_missing_one_is_down(api, heartbeats):
    await heartbeats("summary", job_id="job-42")
    workers = named(monitor(api)["workers"])

    assert workers["summary"]["state"] == "up"
    assert workers["summary"]["instances"][0]["job_id"] == "job-42"
    assert workers["transcription"]["state"] == "down"


async def test_waiting_work_with_its_worker_down_is_a_stalled_queue(
    api, recording_queue, tmp_path, heartbeats
):
    meeting = create_meeting(api, "Reunión de prueba")
    assert import_wav(api, meeting["id"], tmp_path).status_code in (200, 202)

    body = monitor(api)
    queues, jobs = named(body["queues"]), named(body["jobs"])
    assert jobs["transcription"]["queued"] == 1
    assert jobs["transcription"]["oldest_queued_seconds"] >= 0
    assert queues["transcription"]["state"] == "stalled"

    await heartbeats("transcription")
    assert named(monitor(api)["queues"])["transcription"]["state"] == "busy"


async def test_recent_work_names_the_meeting_and_shortens_a_search(
    api, recording_queue, tmp_path, sessionmaker
):
    meeting = create_meeting(api, "Sincro semanal")
    import_wav(api, meeting["id"], tmp_path)
    async with sessionmaker() as session:
        session.add(
            BrainQueryRun(
                query="¿Qué decidimos sobre " + "el almacenamiento " * 20,
                status="failed",
                error="LLM_UNAVAILABLE",
                input_sha256="x" * 64,
                top_k=10,
                max_results=5,
                filters={},
                provider="ollama",
                model="m",
                model_version="v",
                base_url="http://llm.test",
                max_attempts=1,
            )
        )
        await session.commit()

    recent = monitor(api)["recent"]
    assert recent["transcription"][0]["title"] == "Sincro semanal"
    assert recent["transcription"][0]["meeting_id"] == meeting["id"]
    search = recent["brain-query"][0]
    assert search["status"] == "failed" and search["error"] == "LLM_UNAVAILABLE"
    assert len(search["title"]) == monitor_api.QUERY_TEXT_CHARS and search["title"].endswith("…")
    failures = named(monitor(api)["jobs"])["brain-query"]["last_failures"]
    assert failures[0]["error"] == "LLM_UNAVAILABLE"


async def test_a_redis_outage_leaves_the_page_working_with_unknown_workers(api, monkeypatch):
    async def down(*args, **kwargs):
        raise RedisConnectionError("down")

    redis = api.app.state.redis
    monkeypatch.setattr(redis, "ping", down)
    monkeypatch.setattr(redis, "xlen", down)
    body = monitor(api)

    assert {s["name"]: s["ok"] for s in body["services"]}["redis"] is False
    assert {w["state"] for w in body["workers"]} == {"unknown"}
    assert {q["state"] for q in body["queues"]} == {"unknown"}
    assert named(body["services"])["postgres"]["ok"] is True


async def test_a_postgresql_outage_leaves_the_page_working_without_jobs(api, monkeypatch):
    async def down(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(monitor_api, "_stats", down)
    body = monitor(api)

    assert named(body["services"])["postgres"]["ok"] is False
    assert body["jobs"] == [] and all(not rows for rows in body["recent"].values())
    assert named(body["services"])["redis"]["ok"] is True
