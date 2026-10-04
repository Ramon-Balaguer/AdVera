"""Brain against real PostgreSQL + pgvector and Redis, with deterministic fake embeddings."""

import hashlib
import json
import re

import numpy as np
import pytest
from sqlalchemy import select

from app import runtime_settings
from app.asr import AsrSegment
from app.brain_worker import BrainIndexWorker, BrainQueryWorker
from app.embeddings import EmbeddingUnavailable
from app.llm import LLMResult, LLMUnavailable
from app.models import BrainChunk, BrainEvidence, BrainIndexJob, BrainQueryRun
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
    api,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    embeddings=None,
    title="Sincro",
    segments=None,
):
    meeting = create_meeting(api, title)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    brain_queue = RecordingQueue()
    worker = make_worker(
        sessionmaker,
        storage,
        RecordingQueue(),
        settings,
        {"whisperx": FakeEngine(results=[segments or SEGMENTS])},
    )
    worker.brain_queue = brain_queue
    await worker.process(job_id)
    assert len(brain_queue.published) == 1
    indexer = BrainIndexWorker(
        sessionmaker, storage, RecordingQueue(), settings, embeddings or BagOfWords()
    )
    await indexer.process(brain_queue.published[0])
    return meeting, brain_queue.published[0]


async def ask(api, sessionmaker, storage, settings, llm, query, embeddings=None, **filters):
    queue = RecordingQueue()
    api.app.state.brain_query_queue = queue
    response = api.post("/api/brain/query", json={"query": query, "filters": filters})
    assert response.status_code == 202, response.text
    run_id = response.json()["query_id"]
    worker = BrainQueryWorker(
        sessionmaker,
        storage,
        queue,
        settings,
        embeddings or BagOfWords(),
        llm_factory=lambda run, s: llm,
    )
    await worker.process(run_id)
    return api.get(f"/api/brain/query/{run_id}").json()


async def test_transcript_is_indexed_with_embeddings_and_evidence(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting, job_id = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    async with sessionmaker() as session:
        job = await session.get(BrainIndexJob, job_id)
        chunks = (
            (await session.execute(select(BrainChunk).order_by(BrainChunk.start_time)))
            .scalars()
            .all()
        )
        evidence = (await session.execute(select(BrainEvidence))).scalars().all()
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
    overview = api.get("/api/brain/overview").json()
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
    assert body["result"]["reason"] == "NO_MATCH"  # nothing was found, so nothing was read


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
    assert body["result"]["reason"] == "UNCITED"  # it answered, but cited nothing valid
    assert body["result"]["retrieved"]  # the evidence found is still reported
    # ...with what the page needs to show it like a source: the text and a segment to link to.
    fragment = body["result"]["retrieved"][0]
    assert fragment["content"] and fragment["segment_id"].startswith("system-")
    assert fragment["language"] and fragment["speaker"] is not None


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
    settings.brain_max_attempts = 1  # the only attempt is the last one
    _, job_id = await indexed_meeting(
        api, sessionmaker, storage, settings, tmp_path, embeddings=BagOfWords(fail=True)
    )
    async with sessionmaker() as session:
        job = await session.get(BrainIndexJob, job_id)
        chunks = (await session.execute(select(BrainChunk))).scalars().all()
    assert (job.status, job.error) == ("completed", "EMBEDDING_MODEL_UNAVAILABLE")
    assert chunks and all(c.embedding is None for c in chunks)
    assert api.get("/api/brain/overview").json()["state"] == "partial"
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
    with api.websocket_connect(f"/ws/brain/query/{body['query_id']}") as ws:
        event = ws.receive_json()
    assert (event["type"], event["status"]) == ("query.state", "completed")
    assert event["result"]["sources"][0]["segment_id"] == "system-00000"


async def test_redis_down_fails_the_query_explicitly(
    api, recording_queue, settings, llm_configured
):
    api.app.state.brain_query_queue = RecordingQueue(fail=True)
    body = api.post("/api/brain/query", json={"query": "copias"}).json()
    assert (body["status"], body["error"]) == ("failed", "QUEUE_UNAVAILABLE")


async def test_query_requires_a_configured_llm(api, recording_queue):
    assert (
        api.post("/api/brain/query", json={"query": "copias"}).json()["detail"]
        == "LLM_NOT_CONFIGURED"
    )


async def test_deleting_the_meeting_removes_its_brain(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    meeting, _ = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    other, _ = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path, title="Altra")
    llm = ScriptedLLM({"sufficient": True, "answer": "Fallan.", "citations": ["S1"]})
    cited = await ask(
        api,
        sessionmaker,
        storage,
        settings,
        llm,
        "copias de seguridad",
        meeting_ids=[meeting["id"]],
    )
    kept = await ask(
        api, sessionmaker, storage, settings, llm, "copias de seguridad", meeting_ids=[other["id"]]
    )
    assert cited["result"]["sources"] and kept["result"]["sources"]  # real runs hold segment text

    assert api.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    async with sessionmaker() as session:
        for model in (BrainIndexJob, BrainChunk, BrainEvidence):
            rows = (await session.execute(select(model))).scalars().all()
            assert all(getattr(row, "meeting_id", other["id"]) == other["id"] for row in rows)
        runs = (await session.execute(select(BrainQueryRun))).scalars().all()
    # The answer that quoted the deleted meeting is gone; the other meeting's answer stays.
    assert [run.id for run in runs] == [kept["query_id"]]
    assert api.get(f"/api/brain/query/{cited['query_id']}").status_code == 404


async def test_chunks_that_resolve_to_no_segment_do_not_reach_the_llm(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    meeting, _ = await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    storage.transcript_path(meeting["id"]).unlink()  # chunks remain, their segments do not
    llm = ScriptedLLM({"sufficient": True, "answer": "Inventado.", "citations": ["S1"]})
    body = await ask(api, sessionmaker, storage, settings, llm, "copias de seguridad")
    assert body["status"] == "empty" and body["result"]["sources"] == []
    assert body["result"]["reason"] == "NO_SEGMENTS"
    assert body["result"]["retrieved"]  # the chunks were found…
    assert llm.calls == []  # …but there was no evidence to show the model


async def test_the_same_words_from_two_speakers_are_two_pieces_of_evidence(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    same_words = [
        AsrSegment(0.0, 2.0, "Sí, ho tinc.", "ca", "SPEAKER_00"),
        AsrSegment(3.0, 5.0, "Sí, ho tinc.", "ca", "SPEAKER_01"),
        AsrSegment(6.0, 9.0, "El pressupost queda pendent.", "ca", "SPEAKER_00"),
    ]
    await indexed_meeting(
        api, sessionmaker, storage, settings, tmp_path, title="Reunió", segments=same_words
    )
    llm = ScriptedLLM({"sufficient": True, "answer": "Tots dos.", "citations": ["S1", "S2"]})
    body = await ask(api, sessionmaker, storage, settings, llm, "sí ho tinc")
    speakers = sorted(r["speaker"] for r in body["result"]["retrieved"] if r["start"] < 5)
    assert speakers == ["SPEAKER_00", "SPEAKER_01"]  # neither attribution was collapsed away


async def test_a_query_whose_lease_is_taken_over_writes_no_answer(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    from sqlalchemy import update

    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)

    class StealingLLM(ScriptedLLM):
        async def complete_json(self, system, user, schema, *, context_tokens):
            # While the model "runs", another worker takes the query over.
            async with sessionmaker() as session:
                await session.execute(update(BrainQueryRun).values(lease_token="someone-else"))
                await session.commit()
            return await super().complete_json(system, user, schema, context_tokens=context_tokens)

    llm = StealingLLM({"sufficient": True, "answer": "Fallan cada noche.", "citations": ["S1"]})
    queue = RecordingQueue()
    api.app.state.brain_query_queue = queue
    run_id = api.post("/api/brain/query", json={"query": "copias de seguridad"}).json()["query_id"]
    worker = BrainQueryWorker(
        sessionmaker,
        storage,
        queue,
        settings,
        BagOfWords(),
        llm_factory=lambda run, s: llm,
    )
    await worker.process(run_id)

    async with sessionmaker() as session:
        run = await session.get(BrainQueryRun, run_id)
    # The stale worker's answer was fenced out: the new owner will produce the result.
    assert run.status != "completed" and (run.result or {}).get("answer") is None


async def test_a_model_that_says_the_excerpts_do_not_answer_is_reported_as_insufficient(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    await indexed_meeting(api, sessionmaker, storage, settings, tmp_path)
    llm = ScriptedLLM({"sufficient": False, "answer": "No consta.", "citations": []})
    body = await ask(api, sessionmaker, storage, settings, llm, "copias de seguridad")
    assert (body["status"], body["result"]["reason"]) == ("empty", "MODEL_INSUFFICIENT")
    assert body["result"]["retrieved"]  # the reader can still judge the fragments

    # A completed answer has no reason.
    good = ScriptedLLM({"sufficient": True, "answer": "Fallan.", "citations": ["S1"]})
    answered = await ask(api, sessionmaker, storage, settings, good, "copias de seguridad")
    assert answered["status"] == "completed" and "reason" not in answered["result"]


async def test_a_tag_filter_limits_the_search_to_tagged_meetings_before_ranking(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, llm_configured
):
    tagged, _ = await indexed_meeting(
        api, sessionmaker, storage, settings, tmp_path, title="Con etiqueta"
    )
    other, _ = await indexed_meeting(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        title="Sin etiqueta",
        segments=[
            AsrSegment(0.0, 4.0, "Las copias de seguridad se hacen los lunes.", "es", "SPEAKER_03")
        ],
    )
    api.post(f"/api/meetings/{tagged['id']}/tags", json={"label": "Arquitectura"})
    llm = ScriptedLLM({"sufficient": True, "answer": "Fallan.", "citations": ["S1"]})

    everything = await ask(api, sessionmaker, storage, settings, llm, "copias de seguridad")
    assert {r["meeting_id"] for r in everything["result"]["retrieved"]} == {
        tagged["id"],
        other["id"],
    }

    # The tag is matched by its normalized name (case and accents do not matter).
    only = await ask(
        api, sessionmaker, storage, settings, llm, "copias de seguridad", tag="ARQUITECTURA"
    )
    assert {r["meeting_id"] for r in only["result"]["retrieved"]} == {tagged["id"]}
    assert only["result"]["sources"] and only["result"]["sources"][0]["meeting_id"] == tagged["id"]

    nothing = await ask(
        api, sessionmaker, storage, settings, llm, "copias de seguridad", tag="otra etiqueta"
    )
    assert nothing["status"] == "empty" and nothing["result"]["reason"] == "NO_MATCH"

    # Several tags: meetings carrying any of them.
    api.post(f"/api/meetings/{other['id']}/tags", json={"label": "Trèvol"})
    either = await ask(
        api,
        sessionmaker,
        storage,
        settings,
        llm,
        "copias de seguridad",
        tags=["arquitectura", "trevol"],
    )
    assert {r["meeting_id"] for r in either["result"]["retrieved"]} == {tagged["id"], other["id"]}
    one = await ask(
        api, sessionmaker, storage, settings, llm, "copias de seguridad", tags=["Trèvol", "nada"]
    )
    assert {r["meeting_id"] for r in one["result"]["retrieved"]} == {other["id"]}
