"""FastAPI application and router registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from app import (
    audio,
    brain_api,
    capture_agent,
    concept_graph_api,
    facts_api,
    meeting_brain_api,
    meetings,
    monitor_api,
    notes_api,
    people_api,
    settings_api,
    summary_api,
    tags_api,
    timeline_api,
    upload_limit,
)
from app.audio_sessions import AudioSessionManager
from app.config import get_settings
from app.contracts import HealthResponse
from app.database import check_connectivity, create_engine, create_sessionmaker
from app.job_queue import (
    BRAIN_INDEX_GROUP,
    BRAIN_QUERY_GROUP,
    SUMMARY_CONSUMER_GROUP,
    TRANSCRIPTION_CONSUMER_GROUP,
    RedisStreamQueue,
    create_redis,
)
from app.storage import SAMPLE_RATE, SAMPLE_WIDTH, MeetingStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    await check_connectivity(engine)
    redis = create_redis(settings.redis_url)
    app.state.engine = engine
    app.state.redis = redis
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.storage = MeetingStorage(settings.audio_storage_path)
    app.state.audio_sessions = AudioSessionManager(
        app.state.storage,
        max_track_bytes=settings.capture_max_seconds * SAMPLE_RATE * SAMPLE_WIDTH,
    )
    app.state.capture_agents = capture_agent.CaptureAgentRegistry(app.state.audio_sessions)
    app.state.transcription_queue = RedisStreamQueue(
        redis, settings.transcription_queue_name, TRANSCRIPTION_CONSUMER_GROUP
    )
    app.state.summary_queue = RedisStreamQueue(
        redis, settings.summary_queue_name, SUMMARY_CONSUMER_GROUP
    )
    app.state.brain_index_queue = RedisStreamQueue(
        redis, settings.brain_index_queue_name, BRAIN_INDEX_GROUP
    )
    app.state.brain_query_queue = RedisStreamQueue(
        redis, settings.brain_query_queue_name, BRAIN_QUERY_GROUP
    )
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def _package_version() -> str:
    # The release workflow stamps the real version into the package at build time.
    try:
        return version("advera-backend")
    except PackageNotFoundError:
        return "0.0.0"


app = FastAPI(title="AdVera API", version=_package_version(), lifespan=lifespan)
app.add_middleware(upload_limit.UploadLimitMiddleware)
app.include_router(tags_api.router)  # before meetings: /api/meetings/tags
app.include_router(meetings.router)
app.include_router(notes_api.router)
app.include_router(people_api.router)
app.include_router(audio.router)
app.include_router(capture_agent.router)
app.include_router(settings_api.router)
app.include_router(monitor_api.router)
app.include_router(summary_api.router)
app.include_router(brain_api.router)
app.include_router(concept_graph_api.router)
app.include_router(timeline_api.router)
app.include_router(facts_api.router)
app.include_router(meeting_brain_api.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
