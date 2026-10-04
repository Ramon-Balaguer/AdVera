"""The three worker processes start, stop when asked and are wired from the settings."""

import asyncio

import pytest

from app import brain_worker, memory_worker, transcription_worker
from app.config import Settings

WORKERS = [brain_worker, memory_worker, transcription_worker]


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize("worker", WORKERS, ids=lambda module: module.__name__)
async def test_a_worker_that_is_already_asked_to_stop_starts_and_ends_cleanly(worker):
    # No datastore is contacted: the loop never runs, but the clients are built and closed.
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(worker.run(settings(), stop), timeout=10)


@pytest.mark.parametrize("worker", WORKERS, ids=lambda module: module.__name__)
def test_the_process_entry_point_runs_the_worker_with_the_environment_settings(worker, monkeypatch):
    received = []

    async def fake_run(given):
        received.append(given)

    monkeypatch.setattr(worker, "run", fake_run)
    monkeypatch.setattr(worker, "get_settings", lambda: "the-settings")

    worker.main()

    assert received == ["the-settings"]


def test_memory_embeddings_can_be_turned_off_or_use_bge_m3():
    assert memory_worker.build_embeddings(settings(embedding_provider="none")) is None
    provider = memory_worker.build_embeddings(settings(embedding_model="BAAI/bge-m3"))
    assert type(provider).__name__ == "BgeM3Provider"


def test_diarization_can_be_turned_off_or_use_the_local_provider():
    assert transcription_worker.build_diarizer(settings(diarization_provider="none")) is None
    diarizer = transcription_worker.build_diarizer(
        settings(diarization_threshold=0.5, diarization_min_speakers=1, diarization_max_speakers=4)
    )
    assert type(diarizer).__name__ == "LocalDiarizationProvider"
