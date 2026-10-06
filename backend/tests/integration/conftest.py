"""Integration fixtures against real PostgreSQL + pgvector and Redis.

Set TEST_DATABASE_URL and TEST_REDIS_URL, for example:
  TEST_DATABASE_URL=postgresql+asyncpg://advera:advera@127.0.0.1:15432/advera_test
  TEST_REDIS_URL=redis://127.0.0.1:16379/15

Use 127.0.0.1, not localhost: the Compose datastores listen on IPv4 loopback only, and a
`localhost` that tries ::1 first adds seconds to every connection.

Each pytest run works in its own throw-away database (`<name>_<random>`, dropped at the end),
so concurrent runs, or a run beside a manual session, never wipe each other's schema.
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

BASE_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REDIS_URL = os.environ.get("TEST_REDIS_URL")
RUN_ID = uuid.uuid4().hex[:8]
DATABASE_URL = (
    make_url(BASE_DATABASE_URL)
    .set(database=f"{make_url(BASE_DATABASE_URL).database}_{RUN_ID}")
    .render_as_string(hide_password=False)
    if BASE_DATABASE_URL
    else None
)


def pytest_collection_modifyitems(config, items):
    if BASE_DATABASE_URL and REDIS_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL and TEST_REDIS_URL are required")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


async def _admin(url: str):
    parsed = make_url(url)
    return await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        database="postgres",
    )


async def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    admin = await _admin(url)
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", parsed.database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await admin.close()


def pytest_sessionfinish(session, exitstatus):
    """Drop this run's database."""
    if not (BASE_DATABASE_URL and REDIS_URL):
        return
    import asyncio

    async def drop() -> None:
        admin = await _admin(DATABASE_URL)
        try:
            await admin.execute(
                f'DROP DATABASE IF EXISTS "{make_url(DATABASE_URL).database}" WITH (FORCE)'
            )
        finally:
            await admin.close()

    try:
        asyncio.run(drop())
    except Exception:  # a leftover database is harmless; never fail the run for it
        pass


@pytest.fixture
async def database():
    """A clean schema per test in this run's own database (alembic-schema-ownership allows
    fixtures to create schema). Tables are emptied, not dropped: it keeps setup fast."""
    await _ensure_database(DATABASE_URL)
    engine = create_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)  # no-op when tables exist
        tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
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
        # Tests script their engines under the name "faster-whisper".
        asr_definitive_provider="faster-whisper",
        asr_fallback_provider="faster-whisper",
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
