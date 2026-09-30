"""Memory against real PostgreSQL + pgvector and Redis, with deterministic fake embeddings."""

import hashlib
import json
import re

import numpy as np
import pytest
from sqlalchemy import select

from app import runtime_settings
from app.asr import AsrSegment
from app.embeddings import EmbeddingUnavailable
from app.llm import LLMResult, LLMUnavailable
from app.memory_worker import MemoryIndexWorker, MemoryQueryWorker
from app.models import MemoryChunk, MemoryEvidence, MemoryIndexJob, MemoryQueryRun
from tests.fakes import FakeEngine, RecordingQueue
from tests.integration.conftest import make_worker
from tests.integration.test_import_transcription import create_meeting, import_wav

pytestmark = pytest.mark.integration

SEGMENTS = [
    AsrSegment(0.0, 4.0, "Las copias de seguridad fallan cada noche.", "es", "SPEAKER_00"),
    AsrSegment(
        4.5, 9.0, "Ampliaremos el volumen de almacenamiento esta semana.", "es", "SPEAKER_01"
    ),
    AsrSegment(9.5, 13.0, "Publicarem la versió nova dilluns.", "ca", "SPEAKER_00"),
]


class BagOfWords:
    """Deterministic 1024-dim embeddings: shared words give cosine similarity."""

    name = "fake-embeddings"
    model = "bag-of-words"
    model_version = "1"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def encode(self, texts):
        if self.fail:
            raise EmbeddingUnavailable("EMBEDDING_MODEL_UNAVAILABLE")
        rows = np.zeros((len(texts), 1024), dtype=np.float32)
        for row, value in enumerate(texts):
            for word in re.findall(r"\w+", value.lower()):
                rows[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 1024] += 1
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        return rows / np.where(norms == 0, 1, norms)


class ScriptedLLM:
    name = "ollama"
    model = "scripted"

    def __init__(self, result):
        self.result = result
        self.calls = []

    async def complete_json(self, system, user, schema, *, context_tokens):
        self.calls.append(user)
        if isinstance(self.result, Exception):
            raise self.result
        return LLMResult(raw=json.dumps(self.result), parsed=self.result)


@pytest.fixture
def llm_configured(settings):
    runtime = runtime_settings.load(settings).model_copy(
        update={"llm_base_url": "http://llm.test", "llm_model": "scripted"}
    )
    runtime_settings.save(settings, runtime)


async def indexed_meeting(
    api, sessionmaker, storage, settings, tmp_path, embeddings=None, title="Sincro"
):
    meeting = create_meeting(api, title)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    memory_queue = RecordingQueue()
    worker = make_worker(
        sessionmaker,
        storage,
        RecordingQueue(),
        settings,
        {"whisperx": FakeEngine(results=[SEGMENTS])},
    )
    worker.memory_queue = memory_queue
    await worker.process(job_id)
    assert len(memory_queue.published) == 1
    indexer = MemoryIndexWorker(
        sessionmaker, storage, RecordingQueue(), settings, embeddings or BagOfWords()
    )
    await indexer.process(memory_queue.published[0])
    return meeting, memory_queue.published[0]


async def ask(api, sessionmaker, storage, settings, llm, query, embeddings=None, **filters):
    queue = RecordingQueue()
    api.app.state.memory_query_queue = queue
    response = api.post("/api/memory/query", json={"query": query, "filters": filters})
    assert response.status_code == 202, response.text
    run_id = response.json()["query_id"]
    worker = MemoryQueryWorker(
        sessionmaker,
        storage,
        queue,
        settings,
        embeddings or BagOfWords(),
        llm_factory=lambda run, s: llm,
    )
    await worker.process(run_id)
    return api.get(f"/api/memory/query/{run_id}").json()


async def test_transcript_is_indexed_with_embeddings_and_evidence(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting, job_id = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    async with sessionmaker() as session:
        job = await session.get(MemoryIndexJob, job_id)
        chunks = (
            (await session.execute(select(MemoryChunk).order_by(MemoryChunk.start_time)))
            .scalars()
            .all()
        )
        evidence = (await session.execute(select(MemoryEvidence))).scalars().all()
    assert (job.status, job.error) == ("completed", None)
    assert [c.source_segment_ids for c in chunks] == [
        ["system-00000"],
        ["system-00001"],
        ["system-00002"],
    ]
    assert all(len(c.embedding) == 1024 and c.embedding_dimension == 1024 for c in chunks)
    transcript = storage.read_transcript(meeting["id"])
    assert {c.transcript_sha256 for c in chunks} == {transcript["segments_sha256"]}
    assert sorted(e.segment_id for e in evidence) == [
        "system-00000",
        "system-00001",
        "system-00002",
    ]
    overview = api.get("/api/memory/overview").json()
    assert (overview["state"], overview["chunks"], overview["embedded_chunks"]) == ("ready", 3, 3)


async def test_cited_answer_links_back_to_meeting_segment_and_time(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    meeting, _ = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM(
        {
            "sufficient": True,
            "answer": "Fallan las copias por falta de espacio.",
            "citations": ["S1", "S7"],
        }
    )
    body = await ask(api, sessionmaker, storage, settings, llm, "copias de seguridad")

    assert body["status"] == "completed"
    assert body["result"]["answer"] == "Fallan las copias por falta de espacio."
    source = body["result"]["sources"][0]
    assert (source["meeting_id"], source["segment_id"], source["start"]) == (
        meeting["id"],
        "system-00000",
        0.0,
    )
    assert source["text"] == "Las copias de seguridad fallan cada noche."
    assert body["result"]["retrieval"] == "hybrid"
    assert "[S1] Sincro" in llm.calls[0]


async def test_vector_search_finds_what_full_text_misses(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM(
        {"sufficient": True, "answer": "Se ampliará el volumen.", "citations": ["S1"]}
    )
    # "ampliar" and "volúmenes" are not the stored word forms, so full-text alone finds nothing.
    body = await ask(api, sessionmaker, storage, settings, llm, "ampliar almacenamiento volúmenes")
    first = body["result"]["retrieved"][0]
    assert first["matched"] == ["vector"]
    assert body["result"]["sources"][0]["segment_id"] == "system-00001"


async def test_identical_chunks_from_several_meetings_fill_one_slot(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    first, _ = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path, title="A")
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path, title="B")
    llm = ScriptedLLM({"sufficient": True, "answer": "Cada noche.", "citations": ["S1"]})
    body = await ask(api, sessionmaker, storage, settings, llm, "copias volumen versió")
    retrieved = body["result"]["retrieved"]
    # Six chunks, three distinct contents: the best-ranked copy of each is kept.
    assert len(retrieved) == 3
    assert sorted(r["start"] for r in retrieved) == [0.0, 4.5, 9.5]


async def test_no_evidence_is_empty_without_calling_the_llm(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM({"sufficient": True, "answer": "x", "citations": []})
    body = await ask(
        api,
        sessionmaker,
        storage,
        settings,
        llm,
        "presupuesto marketing",
        embeddings=BagOfWords(fail=True),
    )
    assert (body["status"], body["result"]["answer"], llm.calls) == ("empty", None, [])


async def test_uncited_or_insufficient_answers_are_not_presented_as_fact(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM({"sufficient": True, "answer": "Algo inventado", "citations": ["S99"]})
    body = await ask(api, sessionmaker, storage, settings, llm, "copias de seguridad")
    assert (body["status"], body["result"]["answer"], body["result"]["sources"]) == (
        "empty",
        None,
        [],
    )
    assert body["result"]["retrieved"]  # the evidence found is still reported


async def test_llm_unavailable_fails_but_keeps_the_retrieved_evidence(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    body = await ask(
        api,
        sessionmaker,
        storage,
        settings,
        ScriptedLLM(LLMUnavailable("LLM_UNAVAILABLE")),
        "copias de seguridad",
    )
    assert (body["status"], body["error"]) == ("failed", "LLM_UNAVAILABLE")
    assert body["result"]["answer"] is None and body["result"]["retrieved"]


async def test_filters_are_applied_before_ranking(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM({"sufficient": True, "answer": "Dilluns.", "citations": ["S1"]})
    body = await ask(
        api, sessionmaker, storage, settings, llm, "versió nova dilluns copias", language="ca"
    )
    assert {r["chunk_id"] for r in body["result"]["retrieved"]} and all(
        s["language"] == "ca" for s in body["result"]["sources"]
    )
    other = create_meeting(api, "Otra")
    body = await ask(
        api, sessionmaker, storage, settings, llm, "copias de seguridad", meeting_ids=[other["id"]]
    )
    assert body["status"] == "empty"


async def test_embeddings_unavailable_keeps_full_text_and_reports_partial(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    settings.memory_max_attempts = 1  # the only attempt is the last one
    _, job_id = await indexed_meeting(
        api, sessionmaker, storage, settings, tmp_path, embeddings=BagOfWords(fail=True)
    )
    async with sessionmaker() as session:
        job = await session.get(MemoryIndexJob, job_id)
        chunks = (await session.execute(select(MemoryChunk))).scalars().all()
    assert (job.status, job.error) == ("completed", "EMBEDDING_MODEL_UNAVAILABLE")
    assert chunks and all(c.embedding is None for c in chunks)
    assert api.get("/api/memory/overview").json()["state"] == "partial"
    llm = ScriptedLLM({"sufficient": True, "answer": "Fallan.", "citations": ["S1"]})
    body = await ask(
        api,
        sessionmaker,
        storage,
        settings,
        llm,
        "copias de seguridad",
        embeddings=BagOfWords(fail=True),
    )
    assert body["status"] == "completed" and body["result"]["retrieval"] == "text"


async def test_query_websocket_streams_states_until_terminal(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM({"sufficient": True, "answer": "Fallan.", "citations": ["S1"]})
    body = await ask(api, sessionmaker, storage, settings, llm, "copias de seguridad")
    with api.websocket_connect(f"/ws/query/{body['query_id']}") as ws:
        event = ws.receive_json()
    assert (event["type"], event["status"]) == ("query.state", "completed")
    assert event["result"]["sources"][0]["segment_id"] == "system-00000"


async def test_redis_down_fails_the_query_explicitly(
    api, recording_queue, settings, llm_configured
):
    api.app.state.memory_query_queue = RecordingQueue(fail=True)
    body = api.post("/api/memory/query", json={"query": "copias"}).json()
    assert (body["status"], body["error"]) == ("failed", "QUEUE_UNAVAILABLE")


async def test_query_requires_a_configured_llm(api, recording_queue):
    assert (
        api.post("/api/memory/query", json={"query": "copias"}).json()["detail"]
        == "LLM_NOT_CONFIGURED"
    )


async def test_deleting_the_meeting_removes_its_memory(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting, _ = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    assert api.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    async with sessionmaker() as session:
        for model in (MemoryIndexJob, MemoryChunk, MemoryEvidence):
            assert (await session.execute(select(model))).scalars().all() == []
        assert (await session.execute(select(MemoryQueryRun))).scalars().all() == []
