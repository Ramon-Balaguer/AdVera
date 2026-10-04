"""System monitor: services, workers, queues, jobs and recent work (rebuild-system-monitor.md).

Read only. A worker is up when its loop wrote a heartbeat in the last seconds (`consumer.py`);
queues come from the Redis streams and jobs from PostgreSQL. A datastore that does not answer
turns its part of the page into `unknown` or `down`, never into an error: the page has to keep
working exactly when something is failing.
"""

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import runtime_settings
from app.config import Settings, get_settings
from app.consumer import HEARTBEAT_PREFIX
from app.database import get_session
from app.job_queue import (
    BRAIN_INDEX_GROUP,
    BRAIN_QUERY_GROUP,
    SUMMARY_CONSUMER_GROUP,
    TRANSCRIPTION_CONSUMER_GROUP,
    RedisStreamQueue,
)
from app.models import (
    BrainIndexJob,
    BrainQueryRun,
    Meeting,
    SummaryJob,
    TranscriptionJob,
)

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]

RECENT = 15  # jobs listed per kind
AVERAGE_OVER = 20  # completed jobs the average duration is taken from
FAILURES = 3  # last failures listed per kind
QUERY_TEXT_CHARS = 80  # a search is shown shortened
CONSUMER_GONE_SECONDS = 3600  # a consumer idle for longer belongs to a container that is gone
WORKERS = ("transcription", "summary", "brain-index", "brain-query")
TERMINAL = ("completed", "failed", "empty")  # any other status except queued is "running"
DATASTORE_ERRORS = (RedisError, SQLAlchemyError, OSError)

WorkerState = Literal["up", "down", "unknown"]
QueueState = Literal["ok", "busy", "stalled", "unknown"]


class ServiceStatus(BaseModel):
    name: str
    ok: bool
    latency_ms: int | None = None


class LlmStatus(BaseModel):
    configured: bool
    base_url: str
    model: str


class WorkerInstance(BaseModel):
    host: str
    pid: int | None = None
    started_at: datetime | None = None
    job_id: str | None = None


class WorkerStatus(BaseModel):
    name: str
    state: WorkerState
    instances: list[WorkerInstance]
    since: datetime | None = None


class ConsumerInfo(BaseModel):
    name: str
    idle_seconds: float
    pending: int


class QueueStatus(BaseModel):
    name: str
    state: QueueState
    stream_length: int | None = None
    pending: int | None = None
    lag: int | None = None
    consumers: list[ConsumerInfo] = []
    consumers_gone: int = 0


class Failure(BaseModel):
    id: str
    error: str | None
    at: datetime | None


class JobStats(BaseModel):
    name: str
    queued: int
    running: int
    completed: int
    failed: int
    oldest_queued_seconds: float | None = None
    stale: int = 0  # running, but not updated for longer than the lease
    completed_last_hour: int
    average_seconds: float | None = None
    last_failures: list[Failure] = []


class RecentJob(BaseModel):
    id: str
    status: str
    attempts: int
    max_attempts: int
    error: str | None
    meeting_id: str | None = None
    title: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None


class Monitor(BaseModel):
    generated_at: datetime
    services: list[ServiceStatus]
    llm: LlmStatus
    workers: list[WorkerStatus]
    queues: list[QueueStatus]
    jobs: list[JobStats]
    recent: dict[str, list[RecentJob]]


def _kinds(settings: Settings) -> dict[str, tuple[Any, int]]:
    """Job table and lease (seconds) of each kind of work."""
    return {
        "transcription": (TranscriptionJob, settings.transcription_lease_seconds),
        "summary": (SummaryJob, settings.summary_lease_seconds),
        "brain-index": (BrainIndexJob, settings.summary_lease_seconds),
        "brain-query": (BrainQueryRun, settings.summary_lease_seconds),
    }


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def worker_states(heartbeats: list[dict[str, Any]] | None) -> list[WorkerStatus]:
    """One status per expected loop. `None` means the heartbeats could not be read."""
    result: list[WorkerStatus] = []
    for name in WORKERS:
        if heartbeats is None:
            result.append(WorkerStatus(name=name, state="unknown", instances=[]))
            continue
        instances = [
            WorkerInstance(
                host=str(item.get("host", "")),
                pid=item.get("pid"),
                started_at=_aware(_parse_time(item.get("started_at"))),
                job_id=item.get("job_id"),
            )
            for item in heartbeats
            if item.get("worker") == name
        ]
        started = [i.started_at for i in instances if i.started_at]
        result.append(
            WorkerStatus(
                name=name,
                state="up" if instances else "down",
                instances=instances,
                since=min(started) if started else None,
            )
        )
    return result


def queue_state(worker: WorkerStatus, queued: int, pending: int | None) -> QueueState:
    if worker.state == "unknown":
        return "unknown"
    if queued and worker.state == "down":
        return "stalled"
    return "busy" if queued or pending or any(i.job_id for i in worker.instances) else "ok"


async def _read_heartbeats(redis) -> list[dict[str, Any]]:
    keys = [key async for key in redis.scan_iter(match=f"{HEARTBEAT_PREFIX}*", count=100)]
    values = await redis.mget(keys) if keys else []
    found: list[dict[str, Any]] = []
    for value in values:
        try:
            item = json.loads(value) if value else None
        except ValueError:
            continue
        if isinstance(item, dict):
            found.append(item)
    return found


async def _queue_status(kind: str, queue, worker: WorkerStatus, queued: int) -> QueueStatus:
    length = await queue.redis.xlen(queue.stream)
    group: dict[str, Any] = {}
    consumers: list[ConsumerInfo] = []
    try:
        groups = await queue.redis.xinfo_groups(queue.stream)
        group = next((g for g in groups if g.get("name") == queue.group), {})
        if group:
            for item in await queue.redis.xinfo_consumers(queue.stream, queue.group):
                consumers.append(
                    ConsumerInfo(
                        name=str(item.get("name")),
                        idle_seconds=round(float(item.get("idle", 0)) / 1000, 1),
                        pending=int(item.get("pending", 0)),
                    )
                )
    except RedisError:
        pass  # the stream does not exist yet: nothing has been published
    alive = [c for c in consumers if c.idle_seconds < CONSUMER_GONE_SECONDS]
    return QueueStatus(
        name=kind,
        state=queue_state(worker, queued, group.get("pending")),
        stream_length=length,
        pending=group.get("pending"),
        lag=group.get("lag"),
        consumers=alive,
        consumers_gone=len(consumers) - len(alive),
    )


async def _stats(session: AsyncSession, kind: str, model: Any, lease: int) -> JobStats:
    now = datetime.now(UTC)
    counts = dict(
        (await session.execute(select(model.status, func.count()).group_by(model.status))).all()
    )
    running = sum(n for s, n in counts.items() if s not in TERMINAL and s != "queued")
    oldest = (
        await session.execute(select(func.min(model.created_at)).where(model.status == "queued"))
    ).scalar_one()
    stale = (
        await session.execute(
            select(func.count()).where(
                model.status.notin_(TERMINAL + ("queued",)),
                model.updated_at < now - timedelta(seconds=lease),
            )
        )
    ).scalar_one()
    last_hour = (
        await session.execute(
            select(func.count()).where(
                model.status == "completed", model.completed_at >= now - timedelta(hours=1)
            )
        )
    ).scalar_one()
    done = (
        await session.execute(
            select(model.started_at, model.completed_at)
            .where(model.status == "completed", model.started_at.is_not(None))
            .order_by(model.completed_at.desc())
            .limit(AVERAGE_OVER)
        )
    ).all()
    durations = [(_aware(b) - _aware(a)).total_seconds() for a, b in done if a and b]
    failures = (
        await session.execute(
            select(model.id, model.error, model.updated_at)
            .where(model.status == "failed")
            .order_by(model.updated_at.desc())
            .limit(FAILURES)
        )
    ).all()
    return JobStats(
        name=kind,
        queued=counts.get("queued", 0),
        running=running,
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        oldest_queued_seconds=(now - _aware(oldest)).total_seconds() if oldest else None,
        stale=stale,
        completed_last_hour=last_hour,
        average_seconds=round(sum(durations) / len(durations), 1) if durations else None,
        last_failures=[Failure(id=i, error=e, at=_aware(t)) for i, e, t in failures],
    )


async def _recent(session: AsyncSession, kind: str, model: Any) -> list[RecentJob]:
    if kind == "brain-query":
        statement = select(model, model.query).order_by(model.created_at.desc()).limit(RECENT)
        rows = [(job, None, shown) for job, shown in (await session.execute(statement)).all()]
    else:
        statement = (
            select(model, Meeting.id, Meeting.title)
            .join(Meeting, Meeting.id == model.meeting_id, isouter=True)
            .order_by(model.created_at.desc())
            .limit(RECENT)
        )
        rows = (await session.execute(statement)).all()
    result: list[RecentJob] = []
    for job, meeting_id, title in rows:
        if kind == "brain-query" and title and len(title) > QUERY_TEXT_CHARS:
            title = title[: QUERY_TEXT_CHARS - 1] + "…"
        started, completed = _aware(job.started_at), _aware(job.completed_at)
        result.append(
            RecentJob(
                id=job.id,
                status=job.status,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                error=job.error,
                meeting_id=meeting_id,
                title=title,
                created_at=_aware(job.created_at),
                started_at=started,
                completed_at=completed,
                duration_seconds=(completed - started).total_seconds()
                if started and completed
                else None,
            )
        )
    return result


@router.get("", response_model=Monitor)
async def get_monitor(request: Request, session: Session, settings: AppSettings) -> Monitor:
    redis = request.app.state.redis
    queues = {
        "transcription": RedisStreamQueue(
            redis, settings.transcription_queue_name, TRANSCRIPTION_CONSUMER_GROUP
        ),
        "summary": RedisStreamQueue(redis, settings.summary_queue_name, SUMMARY_CONSUMER_GROUP),
        "brain-index": RedisStreamQueue(redis, settings.brain_index_queue_name, BRAIN_INDEX_GROUP),
        "brain-query": RedisStreamQueue(redis, settings.brain_query_queue_name, BRAIN_QUERY_GROUP),
    }
    services = [ServiceStatus(name="api", ok=True)]

    heartbeats: list[dict[str, Any]] | None = None
    started = time.monotonic()
    try:
        await redis.ping()
        latency = round((time.monotonic() - started) * 1000)
        heartbeats = await _read_heartbeats(redis)
        services.append(ServiceStatus(name="redis", ok=True, latency_ms=latency))
    except DATASTORE_ERRORS:
        services.append(ServiceStatus(name="redis", ok=False))
    workers = worker_states(heartbeats)

    jobs: list[JobStats] = []
    recent: dict[str, list[RecentJob]] = {kind: [] for kind in WORKERS}
    started = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
        latency = round((time.monotonic() - started) * 1000)
        for kind, (model, lease) in _kinds(settings).items():
            jobs.append(await _stats(session, kind, model, lease))
            recent[kind] = await _recent(session, kind, model)
        services.append(ServiceStatus(name="postgres", ok=True, latency_ms=latency))
    except DATASTORE_ERRORS:
        jobs, recent = [], {kind: [] for kind in WORKERS}
        services.append(ServiceStatus(name="postgres", ok=False))

    queued = {job.name: job.queued for job in jobs}
    by_worker = {worker.name: worker for worker in workers}
    statuses: list[QueueStatus] = []
    for kind, queue in queues.items():
        try:
            statuses.append(await _queue_status(kind, queue, by_worker[kind], queued.get(kind, 0)))
        except DATASTORE_ERRORS:
            statuses.append(QueueStatus(name=kind, state="unknown"))

    runtime = runtime_settings.load(settings)
    return Monitor(
        generated_at=datetime.now(UTC),
        services=services,
        llm=LlmStatus(
            configured=runtime.llm_configured,
            base_url=runtime.llm_base_url,
            model=runtime.llm_model,
        ),
        workers=workers,
        queues=statuses,
        jobs=jobs,
        recent=recent,
    )
