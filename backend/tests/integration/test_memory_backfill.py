"""The historical backfill queues jobs for meetings with a definitive transcript."""

import sys
import uuid

import pytest
from sqlalchemy import select

from app import memory_backfill
from app.models import BrainJob, MemoryIndexJob
from tests.integration.test_brain_pipeline import llm_configured  # noqa: F401
from tests.integration.test_concept_graph import concept, extraction, project
from tests.integration.test_import_transcription import create_meeting

pytestmark = pytest.mark.integration

ZERO = {"meetings": 0, "index_jobs": 0, "brain_jobs": 0, "concept_jobs": 0}


@pytest.fixture
def backfill_settings(settings, monkeypatch):
    """The backfill reads its own settings: point it at the test stack and private queues."""
    unique = uuid.uuid4().hex
    own = settings.model_copy(
        update={
            "memory_index_queue_name": f"advera:test:index:{unique}",
            "brain_queue_name": f"advera:test:brain:{unique}",
        }
    )
    monkeypatch.setattr(memory_backfill, "get_settings", lambda: own)
    return own


async def two_meetings(api, sessionmaker, storage, settings, tmp_path):
    first, *_ = await project(
        api, sessionmaker, storage, settings, tmp_path, extraction([concept("Kafka")]), "Primera"
    )
    second, *_ = await project(
        api, sessionmaker, storage, settings, tmp_path, extraction([concept("Redis")]), "Segunda"
    )
    return first, second


async def jobs(sessionmaker, model):
    async with sessionmaker() as session:
        return (await session.execute(select(model))).scalars().all()


async def test_meetings_without_a_definitive_transcript_are_left_alone(
    api,
    sessionmaker,
    backfill_settings,
    llm_configured,  # noqa: F811
):
    create_meeting(api, "Sin transcripción")
    assert await memory_backfill.backfill(False, False) == ZERO
    assert await jobs(sessionmaker, MemoryIndexJob) == []


async def test_a_memory_index_job_is_queued_once_per_meeting_and_not_again(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    backfill_settings,
    llm_configured,  # noqa: F811
):
    await two_meetings(api, sessionmaker, storage, settings, tmp_path)

    first = await memory_backfill.backfill(False, False)
    assert (first["meetings"], first["index_jobs"], first["brain_jobs"]) == (2, 2, 0)
    # Running it twice creates no new job: the same queued ones are reused (and published again,
    # which is harmless because a job is claimed with a lease).
    again = await memory_backfill.backfill(False, False)
    assert again["meetings"] == 2
    index_jobs = [j for j in await jobs(sessionmaker, MemoryIndexJob) if j.kind != "concepts"]
    assert len(index_jobs) == 2


async def test_brain_jobs_are_queued_only_when_asked_and_the_model_is_configured(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    backfill_settings,
    llm_configured,  # noqa: F811
):
    await two_meetings(api, sessionmaker, storage, settings, tmp_path)

    # The existing Brain jobs of these meetings are completed: reused, nothing to publish.
    assert (await memory_backfill.backfill(True, False))["brain_jobs"] == 0
    # --rebuild forces a new run of the completed ones.
    rebuilt = await memory_backfill.backfill(True, True)
    assert (rebuilt["index_jobs"], rebuilt["brain_jobs"]) == (2, 2)
    queued = [j for j in await jobs(sessionmaker, BrainJob) if j.status == "queued"]
    assert len(queued) == 2


async def test_brain_is_not_queued_when_no_model_is_configured(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    backfill_settings,
    llm_configured,  # noqa: F811
):
    await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    from app import runtime_settings

    runtime = runtime_settings.load(settings).model_copy(update={"llm_base_url": ""})
    runtime_settings.save(settings, runtime)

    counts = await memory_backfill.backfill(True, True)
    assert (counts["index_jobs"], counts["brain_jobs"]) == (2, 0)


async def test_the_run_can_be_limited_to_some_meetings_and_skip_titles(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    backfill_settings,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)

    only_first = await memory_backfill.backfill(False, False, meeting_ids=[first["id"]])
    assert only_first["meetings"] == 1
    skipping = await memory_backfill.backfill(False, False, exclude_titles=[" primera "])
    assert skipping["meetings"] == 1  # the title is compared trimmed and ignoring case
    none_left = await memory_backfill.backfill(
        False, False, meeting_ids=[second["id"]], exclude_titles=["Segunda"]
    )
    assert none_left["meetings"] == 0


async def test_reproject_queues_the_projection_again_without_calling_the_model(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    backfill_settings,
    llm_configured,  # noqa: F811
):
    first, _ = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    brain_jobs_before = len(await jobs(sessionmaker, BrainJob))

    counts = await memory_backfill.backfill(False, False, [first["id"]], reproject=True)

    assert counts == {**ZERO, "meetings": 1, "concept_jobs": 1}
    assert len(await jobs(sessionmaker, BrainJob)) == brain_jobs_before
    # Nothing has been extracted for a meeting without a Brain result: nothing to project.
    blank = create_meeting(api, "Sin extracción")
    assert (await memory_backfill.backfill(False, False, [blank["id"]], reproject=True))[
        "concept_jobs"
    ] == 0


def test_the_command_line_passes_its_options_to_the_backfill(monkeypatch, capsys):
    received = {}

    async def fake(*args):
        received["args"] = args
        return {"meetings": 0}

    monkeypatch.setattr(memory_backfill, "backfill", fake)
    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill", "--concepts", "--rebuild", "--meeting", "a", "--exclude-title", "t"],
    )

    memory_backfill.main()

    assert received["args"] == (True, True, ["a"], ["t"], False)
    assert "meetings" in capsys.readouterr().out
