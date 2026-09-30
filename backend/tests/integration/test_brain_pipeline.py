"""Brain pipeline against real PostgreSQL and Redis with a scripted LLM (ADR 0002, 0009)."""

import json

import pytest
from sqlalchemy import select

from app import runtime_settings
from app.brain_worker import BrainWorker
from app.llm import LLMInvalidOutput, LLMResult, LLMUnavailable
from app.models import BrainExtraction, BrainJob, LLMRun
from tests.fakes import FakeEngine, RecordingQueue
from tests.integration.conftest import make_worker
from tests.integration.test_import_transcription import create_meeting, import_wav

pytestmark = pytest.mark.integration


class ScriptedLLM:
    name = "ollama"
    model = "scripted"

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def complete_json(self, system, user, schema, *, context_tokens):
        self.calls += 1
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


def good_output(segment_id="system-00000"):
    parsed = {
        "summary": "Resumen sintético.",
        "summary_evidence_ids": [segment_id],
        "topics": [{"text": "Tema", "evidence_ids": [segment_id]}],
        "decisions": [{"text": "Decisión", "evidence_ids": [segment_id], "state": "decided"}],
        "actions": [],
        "open_questions": [],
        "risks": [],
    }
    return LLMResult(raw=json.dumps(parsed), parsed=parsed)


@pytest.fixture
def llm_configured(settings):
    runtime = runtime_settings.load(settings).model_copy(
        update={
            "llm_base_url": "http://llm.test",
            "llm_model": "scripted",
            "llm_output_language": "en",
        }
    )
    runtime_settings.save(settings, runtime)
    return runtime


async def transcribe(api, sessionmaker, storage, settings, tmp_path, brain_queue):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    worker = make_worker(
        sessionmaker, storage, RecordingQueue(), settings, {"whisperx": FakeEngine()}
    )
    worker.brain_queue = brain_queue
    await worker.process(job_id)
    return meeting


def brain_worker(sessionmaker, storage, settings, llm, queue=None):
    return BrainWorker(
        sessionmaker,
        storage,
        queue or RecordingQueue(),
        settings,
        provider_factory=lambda job, s: llm,
    )


async def only_brain_job(sessionmaker) -> BrainJob:
    async with sessionmaker() as session:
        return (await session.execute(select(BrainJob))).scalar_one()


async def test_definitive_transcript_schedules_brain_and_worker_stores_the_result(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    brain_queue = RecordingQueue()
    meeting = await transcribe(api, sessionmaker, storage, settings, tmp_path, brain_queue)

    job = await only_brain_job(sessionmaker)
    assert brain_queue.published == [job.id]
    assert (job.status, job.model, job.language, job.base_url) == (
        "queued",
        "scripted",
        "en",
        "http://llm.test",
    )
    transcript = storage.read_transcript(meeting["id"])
    assert job.input_sha256 == transcript["segments_sha256"]
    assert api.get(f"/api/meetings/{meeting['id']}/brain").json()["state"] == "queued"

    llm = ScriptedLLM([good_output()])
    await brain_worker(sessionmaker, storage, settings, llm).process(job.id)

    body = api.get(f"/api/meetings/{meeting['id']}/brain").json()
    assert body["state"] == "completed"
    assert body["result"]["decisions"][0]["evidence"][0]["segment_id"] == "system-00000"
    assert body["job"]["language"] == "en"
    async with sessionmaker() as session:
        run = (await session.execute(select(LLMRun))).scalar_one()
        assert run.status == "completed" and run.output["summary"] == "Resumen sintético."
        assert "<think>" not in (run.raw_output or "")


async def test_invalid_output_retries_then_succeeds(
    api, sessionmaker, storage, settings, tmp_path, llm_configured, recording_queue
):
    await transcribe(api, sessionmaker, storage, settings, tmp_path, RecordingQueue())
    job = await only_brain_job(sessionmaker)
    queue = RecordingQueue()
    llm = ScriptedLLM([LLMInvalidOutput("LLM_INVALID_JSON"), good_output()])
    worker = brain_worker(sessionmaker, storage, settings, llm, queue)

    await worker.process(job.id)
    job = await only_brain_job(sessionmaker)
    assert (job.status, job.error, queue.published) == ("queued", "LLM_INVALID_JSON", [job.id])
    await worker.process(job.id)
    assert (await only_brain_job(sessionmaker)).status == "completed"
    async with sessionmaker() as session:
        statuses = sorted(r.status for r in (await session.execute(select(LLMRun))).scalars())
    assert statuses == ["completed", "failed"]


async def test_unavailable_llm_exhausts_retries_without_touching_the_transcript(
    api, sessionmaker, storage, settings, tmp_path, llm_configured, recording_queue
):
    meeting = await transcribe(api, sessionmaker, storage, settings, tmp_path, RecordingQueue())
    before = storage.transcript_path(meeting["id"]).read_bytes()
    job = await only_brain_job(sessionmaker)
    worker = brain_worker(
        sessionmaker, storage, settings, ScriptedLLM([LLMUnavailable("LLM_UNAVAILABLE")])
    )
    for _ in range(3):
        await worker.process(job.id)
    job = await only_brain_job(sessionmaker)
    assert (job.status, job.error, job.attempts) == ("failed", "LLM_UNAVAILABLE", 3)
    assert storage.transcript_path(meeting["id"]).read_bytes() == before
    assert api.get(f"/api/meetings/{meeting['id']}").json()["status"] == "ready"
    assert api.get(f"/api/meetings/{meeting['id']}/brain").json()["state"] == "failed"


async def test_changed_transcript_makes_the_job_stale(
    api, sessionmaker, storage, settings, tmp_path, llm_configured, recording_queue
):
    meeting = await transcribe(api, sessionmaker, storage, settings, tmp_path, RecordingQueue())
    job = await only_brain_job(sessionmaker)
    document = storage.read_transcript(meeting["id"])
    document["segments_sha256"] = "changed"
    storage.write_transcript(meeting["id"], document)
    llm = ScriptedLLM([good_output()])
    await brain_worker(sessionmaker, storage, settings, llm).process(job.id)
    job = await only_brain_job(sessionmaker)
    assert (job.status, job.error, llm.calls) == ("failed", "INPUT_CHANGED", 0)


async def test_regenerate_and_blocked_states(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    empty = create_meeting(api, "Sin transcript")
    assert api.get(f"/api/meetings/{empty['id']}/brain").json()["state"] == "blocked"
    assert api.post(f"/api/meetings/{empty['id']}/brain").status_code == 409

    meeting = await transcribe(api, sessionmaker, storage, settings, tmp_path, RecordingQueue())
    job = await only_brain_job(sessionmaker)
    await brain_worker(sessionmaker, storage, settings, ScriptedLLM([good_output()])).process(
        job.id
    )

    brain_queue = RecordingQueue()
    api.app.state.brain_queue = brain_queue
    response = api.post(f"/api/meetings/{meeting['id']}/brain")
    assert response.status_code == 202 and response.json()["state"] == "queued"
    assert brain_queue.published == [job.id]
    async with sessionmaker() as session:
        assert (await session.execute(select(BrainExtraction))).scalars().all() == []
    assert (
        api.post(f"/api/meetings/{meeting['id']}/brain").json()["detail"] == "BRAIN_ALREADY_RUNNING"
    )


async def test_deleting_the_meeting_removes_brain_data(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    meeting = await transcribe(api, sessionmaker, storage, settings, tmp_path, RecordingQueue())
    job = await only_brain_job(sessionmaker)
    await brain_worker(sessionmaker, storage, settings, ScriptedLLM([good_output()])).process(
        job.id
    )
    assert api.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    async with sessionmaker() as session:
        for model in (BrainJob, LLMRun, BrainExtraction):
            assert (await session.execute(select(model))).scalars().all() == []


async def test_a_lost_lease_never_leaves_the_llm_run_running(
    api, sessionmaker, storage, settings, tmp_path, llm_configured, recording_queue
):
    await transcribe(api, sessionmaker, storage, settings, tmp_path, RecordingQueue())
    job = await only_brain_job(sessionmaker)

    class StealingLLM(ScriptedLLM):
        async def complete_json(self, system, user, schema, *, context_tokens):
            # While the model "runs", another worker takes the job over.
            async with sessionmaker() as session:
                stored = await session.get(BrainJob, job.id)
                stored.lease_token = "someone-else"
                await session.commit()
            return await super().complete_json(system, user, schema, context_tokens=context_tokens)

    await brain_worker(sessionmaker, storage, settings, StealingLLM([good_output()])).process(
        job.id
    )
    async with sessionmaker() as session:
        run = (await session.execute(select(LLMRun))).scalar_one()
        extractions = (await session.execute(select(BrainExtraction))).scalars().all()
    assert (run.status, run.error) == ("failed", "LEASE_LOST")
    assert extractions == []  # the stale worker stored nothing
