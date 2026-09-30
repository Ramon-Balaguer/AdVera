"""Integration fixtures against real PostgreSQL + pgvector and Redis.

Set TEST_DATABASE_URL (a database that may be wiped) and TEST_REDIS_URL, for example:
  TEST_DATABASE_URL=postgresql+asyncpg://advera:advera@localhost:15432/advera_test
  TEST_REDIS_URL=redis://localhost:16379/15
"""

import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.database import create_engine, create_sessionmaker
from app.job_queue import create_redis
from app.models import Base
from app.storage import MeetingStorage
from app.transcription_worker import TranscriptionWorker
from tests.fakes import FakeEngine, RecordingQueue

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REDIS_URL = os.environ.get("TEST_REDIS_URL")


def pytest_collection_modifyitems(config, items):
    if DATABASE_URL and REDIS_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL and TEST_REDIS_URL are required")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


async def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    admin = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        database="postgres",
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", parsed.database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await admin.close()


@pytest.fixture
async def database():
    """A clean schema per test (test fixtures may create schema: alembic-schema-ownership)."""
    await _ensure_database(DATABASE_URL)
    engine = create_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(database):
    return create_sessionmaker(database)


@pytest.fixture
def storage_root(tmp_path) -> Path:
    return tmp_path / "meetings"


@pytest.fixture
def storage(storage_root) -> MeetingStorage:
    return MeetingStorage(storage_root)


@pytest.fixture
def stream_name() -> str:
    return f"advera:test:transcription:{uuid.uuid4().hex}"


@pytest.fixture
def settings(storage_root, stream_name) -> Settings:
    return Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        redis_url=REDIS_URL,
        audio_storage_path=str(storage_root),
        transcription_queue_name=stream_name,
        transcription_heartbeat_seconds=1,
        runtime_settings_path=str(storage_root.parent / "runtime-settings.json"),
        # Tests script their engines under the name "whisperx".
        asr_definitive_provider="whisperx",
        asr_fallback_provider="whisperx",
    )


@pytest.fixture
def api(database, settings, monkeypatch):
    """TestClient over the real app, configured for the test database and storage."""
    for name, value in {
        "DATABASE_URL": settings.database_url,
        "REDIS_URL": settings.redis_url,
        "AUDIO_STORAGE_PATH": settings.audio_storage_path,
        "TRANSCRIPTION_QUEUE_NAME": settings.transcription_queue_name,
        "ASR_DEFINITIVE_PROVIDER": settings.asr_definitive_provider,
        "RUNTIME_SETTINGS_PATH": settings.runtime_settings_path,
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


@pytest.fixture
def recording_queue(api) -> RecordingQueue:
    queue = RecordingQueue()
    api.app.state.transcription_queue = queue
    return queue


@pytest.fixture
async def redis():
    client = create_redis(REDIS_URL)
    yield client
    await client.aclose()


def make_worker(
    sessionmaker, storage, queue, settings, engines: dict[str, FakeEngine], diarizer=None
):
    return TranscriptionWorker(
        sessionmaker,
        storage,
        queue,
        settings,
        engine_factory=lambda provider, role, _settings: engines[provider],
        diarizer=diarizer,
    )
