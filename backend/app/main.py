"""FastAPI application and router registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import (
    audio,
    brain_api,
    capture_agent,
    concept_graph_api,
    meetings,
    memory_api,
    notes_api,
    people_api,
    settings_api,
    tags_api,
    upload_limit,
)
from app.audio_sessions import AudioSessionManager
from app.config import get_settings
from app.contracts import HealthResponse
from app.database import check_connectivity, create_engine, create_sessionmaker
from app.job_queue import TRANSCRIPTION_CONSUMER_GROUP, RedisStreamQueue, create_redis
from app.storage import SAMPLE_RATE, SAMPLE_WIDTH, MeetingStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    await check_connectivity(engine)
    redis = create_redis(settings.redis_url)
    app.state.engine = engine
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
    app.state.brain_queue = RedisStreamQueue(redis, settings.brain_queue_name, "brain-workers")
    app.state.memory_index_queue = RedisStreamQueue(
        redis, settings.memory_index_queue_name, "memory-index-workers"
    )
    app.state.memory_query_queue = RedisStreamQueue(
        redis, settings.memory_query_queue_name, "memory-query-workers"
    )
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


app = FastAPI(title="AdVera API", version="0.1.0", lifespan=lifespan)
app.add_middleware(upload_limit.UploadLimitMiddleware)
app.include_router(tags_api.router)  # before meetings: /api/meetings/tags
app.include_router(meetings.router)
app.include_router(notes_api.router)
app.include_router(people_api.router)
app.include_router(audio.router)
app.include_router(capture_agent.router)
app.include_router(settings_api.router)
app.include_router(brain_api.router)
app.include_router(memory_api.router)
app.include_router(concept_graph_api.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
