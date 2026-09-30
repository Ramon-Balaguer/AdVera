"""FastAPI application and router registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import meetings
from app.config import get_settings
from app.contracts import HealthResponse
from app.database import check_connectivity, create_engine, create_sessionmaker
from app.job_queue import RedisStreamQueue, create_redis
from app.storage import MeetingStorage
from app.transcription_worker import CONSUMER_GROUP


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    await check_connectivity(engine)
    redis = create_redis(settings.redis_url)
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.storage = MeetingStorage(settings.audio_storage_path)
    app.state.transcription_queue = RedisStreamQueue(
        redis, settings.transcription_queue_name, CONSUMER_GROUP
    )
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


app = FastAPI(title="AdVera API", version="0.1.0", lifespan=lifespan)
app.include_router(meetings.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
