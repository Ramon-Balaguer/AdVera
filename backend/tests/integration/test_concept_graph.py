"""Brain concepts -> concept graph projection -> read-only API, against real PostgreSQL."""

import json

import pytest
from sqlalchemy import select

from app import brain_jobs, memory_jobs
from app.brain_worker import BrainWorker
from app.llm import LLMResult
from app.memory_worker import MemoryIndexWorker
from app.models import (
    BrainJob,
    MemoryConcept,
    MemoryConceptAlias,
    MemoryConceptMention,
    MemoryConceptRelationship,
    MemoryConceptRelationshipOccurrence,
    MemoryIndexJob,
)
from tests.fakes import RecordingQueue
from tests.integration.test_brain_pipeline import (  # noqa: F401
    ScriptedLLM,
    llm_configured,
    transcribe,
)
from tests.integration.test_memory_pipeline import BagOfWords

pytestmark = pytest.mark.integration


def extraction(concepts=(), relationships=()):
    parsed = {
        "summary": "Resumen sintético.",
        "summary_evidence_ids": ["system-00000"],
        "topics": [],
        "decisions": [],
        "actions": [],
        "open_questions": [],
        "risks": [],
        "concepts": list(concepts),
        "relationships": list(relationships),
    }
    return LLMResult(raw=json.dumps(parsed), parsed=parsed)


def concept(name, type="technology", evidence=("system-00000",), aliases=()):
    return {"name": name, "type": type, "aliases": list(aliases), "evidence_ids": list(evidence)}


def relation(source, target, type="part_of", evidence=("system-00000",)):
    return {"source": source, "target": target, "type": type, "evidence_ids": list(evidence)}


async def project(
    api, sessionmaker, storage, settings, tmp_path, output, title="Reunión", name="sample.wav"
):
    """One meeting through Brain (scripted) and its concept projection."""
    # Each meeting needs different audio: the same file would reuse the finished job.
    import struct

    from tests.integration.test_import_transcription import create_meeting, write_sine_wav

    meeting = create_meeting(api, title)
    source = write_sine_wav(tmp_path / name, seconds=1.0 + 0.01 * len(title))
    with source.open("rb") as handle:
        job_id = api.post(
            f"/api/meetings/{meeting['id']}/imports", files={"file": (name, handle, "audio/wav")}
        ).json()["transcription"]["job_id"]
    del struct
    from tests.fakes import FakeEngine
    from tests.integration.conftest import make_worker

    worker = make_worker(
        sessionmaker, storage, RecordingQueue(), settings, {"whisperx": FakeEngine()}
    )
    worker.brain_queue = RecordingQueue()
    await worker.process(job_id)

    async with sessionmaker() as session:
        brain = (
            await session.execute(select(BrainJob).where(BrainJob.meeting_id == meeting["id"]))
        ).scalar_one()
    index_queue = RecordingQueue()

    async def hook(job):
        await memory_jobs.schedule_concept_projection(sessionmaker, index_queue, settings, job)

    await BrainWorker(
        sessionmaker,
        storage,
        RecordingQueue(),
        settings,
        provider_factory=lambda job, s: ScriptedLLM([output]),
        on_completed=hook,
    ).process(brain.id)
    return meeting, brain, index_queue


async def run_projection(sessionmaker, storage, settings, meeting_id):
    async with sessionmaker() as session:
        job = (
            await session.execute(
                select(MemoryIndexJob).where(
                    MemoryIndexJob.meeting_id == meeting_id, MemoryIndexJob.kind == "concepts"
                )
            )
        ).scalar_one()
    await MemoryIndexWorker(
        sessionmaker, storage, RecordingQueue(), settings, BagOfWords()
    ).process(job.id)
    async with sessionmaker() as session:
        return await session.get(MemoryIndexJob, job.id)


async def two_meetings(api, sessionmaker, storage, settings, tmp_path):
    first, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(
            concepts=[
                concept("Kafka"),
                concept("Mensajería", type="topic"),
                concept("Pressupost", type="topic", evidence=("system-00001",)),
            ],
            relationships=[relation("Kafka", "Mensajería")],
        ),
        title="Primera",
        name="a.wav",
    )
    second, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(
            concepts=[
                concept("Apache Kafka", aliases=["Kafka"]),  # known through its alias
                concept("Kafka Streams"),  # similar, but a different concept
                concept("pressupost ", type="topic"),
            ],
            relationships=[relation("Kafka Streams", "Apache Kafka", "depends_on")],
        ),
        title="Segunda",
        name="b.wav",
    )
    for meeting in (first, second):
        assert (
            await run_projection(sessionmaker, storage, settings, meeting["id"])
        ).status == "completed"
    return first, second


async def test_brain_completion_schedules_one_projection_job_per_extraction(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, brain, index_queue = await project(
        api, sessionmaker, storage, settings, tmp_path, extraction(concepts=[concept("Kafka")])
    )
    async with sessionmaker() as session:
        jobs = (
            (await session.execute(select(MemoryIndexJob).where(MemoryIndexJob.kind == "concepts")))
            .scalars()
            .all()
        )
    assert [(j.meeting_id, j.source_brain_job_id, j.status) for j in jobs] == [
        (meeting["id"], brain.id, "queued")
    ]
    assert index_queue.published == [jobs[0].id]  # the id only, like every stream message
    # Scheduling again for the same extraction reuses the job.
    await memory_jobs.schedule_concept_projection(sessionmaker, RecordingQueue(), settings, brain)
    async with sessionmaker() as session:
        assert (
            len(
                (
                    await session.execute(
                        select(MemoryIndexJob).where(MemoryIndexJob.kind == "concepts")
                    )
                )
                .scalars()
                .all()
            )
            == 1
        )


async def test_the_same_concept_in_two_meetings_is_one_node_and_similar_ones_stay_apart(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)

    async with sessionmaker() as session:
        concepts = (await session.execute(select(MemoryConcept))).scalars().all()
        aliases = (await session.execute(select(MemoryConceptAlias))).scalars().all()
    names = sorted(c.canonical_name for c in concepts)
    # Kafka (by alias) and Pressupost (by normalized name, in Catalan) are merged; Kafka Streams
    # is kept apart: nothing is merged by similarity.
    assert names == ["Kafka", "Kafka Streams", "Mensajería", "Pressupost"]
    assert [a.normalized_alias for a in aliases] == ["apache kafka"]

    graph = api.get("/api/memory/concept-graph").json()
    by_label = {n["label"]: n for n in graph["nodes"]}
    assert by_label["Kafka"]["meetings"] == 2 and by_label["Kafka"]["mentions"] == 2
    assert by_label["Pressupost"]["meetings"] == 2
    assert by_label["Kafka Streams"]["meetings"] == 1
    edges = {(e["source"], e["target"], e["type"]) for e in graph["edges"]}
    assert (by_label["Kafka"]["id"], by_label["Mensajería"]["id"], "part_of") in edges
    assert (by_label["Kafka Streams"]["id"], by_label["Kafka"]["id"], "depends_on") in edges
    assert graph["state"] == "ready" and not graph["truncated"]


async def test_the_graph_filters_and_bounds_its_size(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)

    def labels(**params):
        return sorted(
            n["label"] for n in api.get("/api/memory/concept-graph", params=params).json()["nodes"]
        )

    assert labels(type="topic") == ["Mensajería", "Pressupost"]
    assert labels(q="KAFKA") == ["Kafka", "Kafka Streams"]  # case and accents do not matter
    assert labels(q="apache") == ["Kafka"]  # through the alias
    assert labels(meeting_id=second["id"]) == ["Kafka", "Kafka Streams", "Pressupost"]
    assert labels(q="%") == []  # LIKE wildcards are literal

    bounded = api.get("/api/memory/concept-graph", params={"limit": 2}).json()
    assert len(bounded["nodes"]) == 2 and bounded["truncated"] and bounded["total_nodes"] == 4
    # The most shared concepts come first, and no edge points outside the returned nodes.
    assert {n["label"] for n in bounded["nodes"]} == {"Kafka", "Pressupost"}
    assert bounded["edges"] == []

    # A relationship seen only in another meeting is not drawn when filtering by this one.
    only_first = api.get("/api/memory/concept-graph", params={"meeting_id": first["id"]}).json()
    assert {(e["type"]) for e in only_first["edges"]} == {"part_of"}


async def test_tags_join_the_graph_and_filter_it(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    api.post(f"/api/meetings/{first['id']}/tags", json={"label": "Arquitectura"})
    api.post(f"/api/meetings/{second['id']}/tags", json={"label": "kafka"})  # named like a concept

    graph = api.get("/api/memory/concept-graph").json()
    tags = {n["label"]: n for n in graph["nodes"] if n["is_tag"]}
    assert set(tags) == {"Arquitectura", "kafka"}
    assert tags["Arquitectura"]["mentions"] == 0  # a tag is metadata, never transcript evidence
    # The exact-name tag is related to the concept of the same name, marked as manual.
    manual = [e for e in graph["edges"] if e["source_type"] == "manual_user"]
    assert [(e["source"], e["type"]) for e in manual] == [(tags["kafka"]["id"], "related_to")]

    only = lambda **p: sorted(  # noqa: E731
        n["label"]
        for n in api.get("/api/memory/concept-graph", params=p).json()["nodes"]
        if not n["is_tag"]
    )
    assert only(tag="arquitectura") == ["Kafka", "Mensajería", "Pressupost"]  # first meeting only
    assert only(tag="Kafka") == ["Kafka", "Kafka Streams", "Pressupost"]  # second meeting only
    assert only(tag="no existe") == []


async def test_the_inspector_shows_meetings_quotes_tags_and_relations(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    api.post(f"/api/meetings/{first['id']}/tags", json={"label": "Kafka"})
    graph = api.get("/api/memory/concept-graph").json()
    kafka = next(n for n in graph["nodes"] if n["label"] == "Kafka" and not n["is_tag"])

    detail = api.get(f"/api/memory/concepts/{kafka['id']}").json()
    assert (detail["label"], detail["type"], detail["aliases"]) == (
        "Kafka",
        "technology",
        ["Apache Kafka"],
    )
    by_title = {m["title"]: m for m in detail["meetings"]}
    assert set(by_title) == {"Primera", "Segunda"}
    quote = by_title["Primera"]["evidence"][0]
    assert quote["segment_id"] == "system-00000" and quote["text"]  # the segment's own text
    assert {(r["direction"], r["type"], r["other_label"]) for r in detail["relations"]} == {
        ("outgoing", "part_of", "Mensajería"),
        ("incoming", "depends_on", "Kafka Streams"),
        ("incoming", "related_to", "Kafka"),  # the manual tag named like this concept
    }
    assert api.get("/api/memory/concepts/does-not-exist").status_code == 404

    tag = next(n for n in graph["nodes"] if n["is_tag"])
    tag_detail = api.get(f"/api/memory/concepts/{tag['id']}").json()
    assert tag_detail["is_tag"] and tag_detail["meetings"][0]["tagged"]
    assert tag_detail["meetings"][0]["evidence"] == []  # no transcript evidence for a tag


async def test_reprojecting_replaces_a_meetings_mentions_without_duplicates(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, brain, _ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(
            concepts=[concept("Kafka"), concept("Mensajería", type="topic")],
            relationships=[relation("Kafka", "Mensajería")],
        ),
    )
    await run_projection(sessionmaker, storage, settings, meeting["id"])
    async with sessionmaker() as session:
        job = (
            await session.execute(select(MemoryIndexJob).where(MemoryIndexJob.kind == "concepts"))
        ).scalar_one()
        await memory_jobs.create_or_reuse_concept_job(
            session, brain_job=brain, settings=settings, force=True
        )
        await session.commit()
    await MemoryIndexWorker(
        sessionmaker, storage, RecordingQueue(), settings, BagOfWords()
    ).process(job.id)

    async with sessionmaker() as session:
        assert len((await session.execute(select(MemoryConceptMention))).scalars().all()) == 2
        assert len((await session.execute(select(MemoryConceptRelationship))).scalars().all()) == 1
        assert (
            len(
                (await session.execute(select(MemoryConceptRelationshipOccurrence))).scalars().all()
            )
            == 1
        )


async def test_an_extraction_that_is_gone_is_stale_and_never_projected(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, brain, _ = await project(
        api, sessionmaker, storage, settings, tmp_path, extraction(concepts=[concept("Kafka")])
    )
    async with sessionmaker() as session:
        runtime = __import__("app.runtime_settings", fromlist=["load"]).load(settings)
        await brain_jobs.create_or_reuse(
            session,
            meeting_id=meeting["id"],
            input_sha256=brain.input_sha256,
            runtime=runtime,
            settings=settings,
            force=True,
        )  # regenerating removes the old extraction
        await session.commit()
    job = await run_projection(sessionmaker, storage, settings, meeting["id"])
    assert (job.status, job.error) == ("failed", "STALE_EXTRACTION")
    async with sessionmaker() as session:
        assert (await session.execute(select(MemoryConceptMention))).scalars().all() == []


async def test_deleting_a_meeting_removes_its_mentions_but_keeps_shared_concepts(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    assert api.delete(f"/api/meetings/{first['id']}").status_code == 204

    async with sessionmaker() as session:
        mentions = (await session.execute(select(MemoryConceptMention))).scalars().all()
        concepts = (await session.execute(select(MemoryConcept))).scalars().all()
    assert {m.meeting_id for m in mentions} == {second["id"]}
    assert len(concepts) == 4  # the global concepts stay
    labels = {n["label"] for n in api.get("/api/memory/concept-graph").json()["nodes"]}
    assert labels == {"Kafka", "Kafka Streams", "Pressupost"}  # "Mensajería" is nobody's now


def test_an_empty_graph_says_so(api):
    graph = api.get("/api/memory/concept-graph").json()
    assert graph == {
        "state": "empty",
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "truncated": False,
    }
