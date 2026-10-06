"""Summary concepts -> concept graph projection -> read-only API, against real PostgreSQL."""

import json

import pytest
from sqlalchemy import select

from app import brain_jobs, summary_jobs
from app.brain_worker import BrainIndexWorker
from app.llm import LLMResult
from app.models import (
    BrainConcept,
    BrainConceptAlias,
    BrainConceptMention,
    BrainConceptRelationship,
    BrainConceptRelationshipOccurrence,
    BrainIndexJob,
    SummaryJob,
)
from app.summary_worker import SummaryWorker
from tests.fakes import RecordingQueue
from tests.integration.test_brain_pipeline import BagOfWords
from tests.integration.test_summary_pipeline import (  # noqa: F401
    ScriptedLLM,
    llm_configured,
    transcribe,
)

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
    """One meeting through Summary (scripted) and its concept projection."""
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
        sessionmaker, storage, RecordingQueue(), settings, {"faster-whisper": FakeEngine()}
    )
    worker.summary_queue = RecordingQueue()
    await worker.process(job_id)

    async with sessionmaker() as session:
        summary = (
            await session.execute(select(SummaryJob).where(SummaryJob.meeting_id == meeting["id"]))
        ).scalar_one()
    index_queue = RecordingQueue()

    async def hook(job):
        await brain_jobs.schedule_concept_projection(sessionmaker, index_queue, settings, job)

    await SummaryWorker(
        sessionmaker,
        storage,
        RecordingQueue(),
        settings,
        provider_factory=lambda job, s: ScriptedLLM(
            output if isinstance(output, list) else [output]
        ),
        on_completed=hook,
    ).process(summary.id)
    return meeting, summary, index_queue


async def run_projection(sessionmaker, storage, settings, meeting_id):
    async with sessionmaker() as session:
        job = (
            await session.execute(
                select(BrainIndexJob).where(
                    BrainIndexJob.meeting_id == meeting_id, BrainIndexJob.kind == "concepts"
                )
            )
        ).scalar_one()
    await BrainIndexWorker(sessionmaker, storage, RecordingQueue(), settings, BagOfWords()).process(
        job.id
    )
    async with sessionmaker() as session:
        return await session.get(BrainIndexJob, job.id)


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


async def test_summary_completion_schedules_one_projection_job_per_extraction(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, summary, index_queue = await project(
        api, sessionmaker, storage, settings, tmp_path, extraction(concepts=[concept("Kafka")])
    )
    async with sessionmaker() as session:
        jobs = (
            (await session.execute(select(BrainIndexJob).where(BrainIndexJob.kind == "concepts")))
            .scalars()
            .all()
        )
    assert [(j.meeting_id, j.source_summary_job_id, j.status) for j in jobs] == [
        (meeting["id"], summary.id, "queued")
    ]
    assert index_queue.published == [jobs[0].id]  # the id only, like every stream message
    # Scheduling again for the same extraction reuses the job.
    await brain_jobs.schedule_concept_projection(sessionmaker, RecordingQueue(), settings, summary)
    async with sessionmaker() as session:
        assert (
            len(
                (
                    await session.execute(
                        select(BrainIndexJob).where(BrainIndexJob.kind == "concepts")
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
        concepts = (await session.execute(select(BrainConcept))).scalars().all()
        aliases = (await session.execute(select(BrainConceptAlias))).scalars().all()
    names = sorted(c.canonical_name for c in concepts)
    # Kafka (by alias) and Pressupost (by normalized name, in Catalan) are merged; Kafka Streams
    # is kept apart: nothing is merged by similarity.
    assert names == ["Kafka", "Kafka Streams", "Mensajería", "Pressupost"]
    assert [a.normalized_alias for a in aliases] == ["apache kafka"]

    graph = api.get("/api/brain/concept-graph").json()
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
            n["label"] for n in api.get("/api/brain/concept-graph", params=params).json()["nodes"]
        )

    assert labels(type="topic") == ["Mensajería", "Pressupost"]
    assert labels(q="KAFKA") == ["Kafka", "Kafka Streams"]  # case and accents do not matter
    assert labels(q="apache") == ["Kafka"]  # through the alias
    assert labels(meeting_id=second["id"]) == ["Kafka", "Kafka Streams", "Pressupost"]
    assert labels(q="%") == []  # LIKE wildcards are literal

    bounded = api.get("/api/brain/concept-graph", params={"limit": 2}).json()
    assert len(bounded["nodes"]) == 2 and bounded["truncated"] and bounded["total_nodes"] == 4
    # The most shared concepts come first, and no edge points outside the returned nodes.
    assert {n["label"] for n in bounded["nodes"]} == {"Kafka", "Pressupost"}
    assert bounded["edges"] == []

    # A relationship seen only in another meeting is not drawn when filtering by this one.
    only_first = api.get("/api/brain/concept-graph", params={"meeting_id": first["id"]}).json()
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

    graph = api.get("/api/brain/concept-graph").json()
    tags = {n["label"]: n for n in graph["nodes"] if n["is_tag"]}
    assert set(tags) == {"Arquitectura", "kafka"}
    assert tags["Arquitectura"]["mentions"] == 0  # a tag is metadata, never transcript evidence
    # The exact-name tag is related to the concept of the same name, marked as manual.
    manual = [e for e in graph["edges"] if e["source_type"] == "manual_user"]
    assert [(e["source"], e["type"]) for e in manual] == [(tags["kafka"]["id"], "related_to")]

    only = lambda **p: sorted(  # noqa: E731
        n["label"]
        for n in api.get("/api/brain/concept-graph", params=p).json()["nodes"]
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
    graph = api.get("/api/brain/concept-graph").json()
    kafka = next(n for n in graph["nodes"] if n["label"] == "Kafka" and not n["is_tag"])

    detail = api.get(f"/api/brain/concepts/{kafka['id']}").json()
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
    assert api.get("/api/brain/concepts/does-not-exist").status_code == 404

    tag = next(n for n in graph["nodes"] if n["is_tag"])
    tag_detail = api.get(f"/api/brain/concepts/{tag['id']}").json()
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
    meeting, summary, _ = await project(
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
            await session.execute(select(BrainIndexJob).where(BrainIndexJob.kind == "concepts"))
        ).scalar_one()
        await brain_jobs.create_or_reuse_concept_job(
            session, summary_job=summary, settings=settings, force=True
        )
        await session.commit()
    await BrainIndexWorker(sessionmaker, storage, RecordingQueue(), settings, BagOfWords()).process(
        job.id
    )

    async with sessionmaker() as session:
        assert len((await session.execute(select(BrainConceptMention))).scalars().all()) == 2
        assert len((await session.execute(select(BrainConceptRelationship))).scalars().all()) == 1
        assert (
            len((await session.execute(select(BrainConceptRelationshipOccurrence))).scalars().all())
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
    meeting, summary, _ = await project(
        api, sessionmaker, storage, settings, tmp_path, extraction(concepts=[concept("Kafka")])
    )
    async with sessionmaker() as session:
        runtime = __import__("app.runtime_settings", fromlist=["load"]).load(settings)
        await summary_jobs.create_or_reuse(
            session,
            meeting_id=meeting["id"],
            input_sha256=summary.input_sha256,
            runtime=runtime,
            settings=settings,
            force=True,
        )  # regenerating removes the old extraction
        await session.commit()
    job = await run_projection(sessionmaker, storage, settings, meeting["id"])
    assert (job.status, job.error) == ("failed", "STALE_EXTRACTION")
    async with sessionmaker() as session:
        assert (await session.execute(select(BrainConceptMention))).scalars().all() == []


async def test_deleting_a_meeting_keeps_shared_concepts_and_deletes_its_own_concepts(
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
        mentions = (await session.execute(select(BrainConceptMention))).scalars().all()
        concepts = (await session.execute(select(BrainConcept))).scalars().all()
    assert {m.meeting_id for m in mentions} == {second["id"]}
    # Shared concepts stay; "Mensajería" was only in the deleted meeting, so it is gone, with
    # its relationship to Kafka.
    assert sorted(c.canonical_name for c in concepts) == ["Kafka", "Kafka Streams", "Pressupost"]
    async with sessionmaker() as session:
        kinds = (await session.execute(select(BrainConceptRelationship))).scalars().all()
    assert [r.relationship_type for r in kinds] == ["depends_on"]
    labels = {n["label"] for n in api.get("/api/brain/concept-graph").json()["nodes"]}
    assert labels == {"Kafka", "Kafka Streams", "Pressupost"}


def test_an_empty_graph_says_so(api):
    graph = api.get("/api/brain/concept-graph").json()
    assert graph == {
        "state": "empty",
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "truncated": False,
        "hidden_isolated": 0,
    }


async def test_one_name_is_one_node_shown_with_the_type_used_most(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meetings = []
    for index, kind in enumerate(("topic", "project", "project")):
        meeting, *_ = await project(
            api,
            sessionmaker,
            storage,
            settings,
            tmp_path,
            extraction(concepts=[concept("Documentación" if index else "documentacion", kind)]),
            title=f"Reunión {index}",
            name=f"{index}.wav",
        )
        meetings.append(meeting)
        assert (
            await run_projection(sessionmaker, storage, settings, meeting["id"])
        ).status == "completed"

    nodes = api.get("/api/brain/concept-graph").json()["nodes"]
    assert [(n["label"], n["type"], n["meetings"]) for n in nodes] == [
        ("documentacion", "project", 3)
    ]
    # A tag with the same name stays a tag (ADR 0013), related to the concept.
    api.post(f"/api/meetings/{meetings[0]['id']}/tags", json={"label": "Documentación"})
    graph = api.get("/api/brain/concept-graph").json()
    assert sorted((n["type"], n["is_tag"]) for n in graph["nodes"]) == [
        ("project", False),
        ("tag", True),
    ]
    assert [e["type"] for e in graph["edges"]] == ["related_to"]


async def test_loose_concepts_can_be_left_out_and_are_counted(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, second = await two_meetings(api, sessionmaker, storage, settings, tmp_path)

    def graph(**params):
        return api.get("/api/brain/concept-graph", params=params).json()

    everything = graph()
    assert len(everything["nodes"]) == 4 and everything["hidden_isolated"] == 0
    connected = graph(include_isolated="false")
    # Pressupost has no relationship; Kafka, Mensajería and Kafka Streams do.
    assert sorted(n["label"] for n in connected["nodes"]) == [
        "Kafka",
        "Kafka Streams",
        "Mensajería",
    ]
    assert connected["hidden_isolated"] == 1 and connected["total_nodes"] == 3
    assert connected["state"] == "ready"
    # Under a meeting filter, only relationships seen in that meeting connect a concept.
    only_first = graph(include_isolated="false", meeting_id=first["id"])
    assert sorted(n["label"] for n in only_first["nodes"]) == ["Kafka", "Mensajería"]
    assert only_first["hidden_isolated"] == 1


async def projected(api, sessionmaker, storage, settings, tmp_path, output, title):
    meeting, *_ = await project(
        api, sessionmaker, storage, settings, tmp_path, output, title=title, name=f"{title}.wav"
    )
    assert (
        await run_projection(sessionmaker, storage, settings, meeting["id"])
    ).status == "completed"
    return meeting


async def test_filters_never_count_or_draw_relations_from_outside_their_scope(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(
            concepts=[concept("Kafka"), concept("Pressupost", type="topic")],
            relationships=[relation("Kafka", "Pressupost", "constrains")],
        ),
        "Primera",
    )
    second = await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(concepts=[concept("Kafka"), concept("Pressupost", type="topic")]),
        "Segunda",
    )
    api.post(f"/api/meetings/{second['id']}/tags", json={"label": "Cliente"})

    def graph(**params):
        return api.get("/api/brain/concept-graph", params=params).json()

    assert [e["type"] for e in graph()["edges"]] == ["constrains"]
    # The relation was said only in the untagged meeting: not drawn, and nothing it connects
    # counts as connected under the tag filter.
    tagged = graph(tag="Cliente")
    assert sorted(n["label"] for n in tagged["nodes"]) == ["Cliente", "Kafka", "Pressupost"]
    assert tagged["edges"] == []
    assert graph(tag="Cliente", include_isolated="false")["hidden_isolated"] == 3
    # A concept whose only partner is filtered out by type is not connected either.
    by_type = graph(type="topic", include_isolated="false")
    assert by_type["nodes"] == [] and by_type["hidden_isolated"] == 1


async def test_a_tag_left_without_meetings_does_not_keep_its_concept_connected(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting = await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(concepts=[concept("Atlas", type="project")]),
        "Atlas",
    )
    tag = api.post(f"/api/meetings/{meeting['id']}/tags", json={"label": "atlas"}).json()
    connected = api.get("/api/brain/concept-graph", params={"include_isolated": "false"}).json()
    assert sorted(n["is_tag"] for n in connected["nodes"]) == [False, True]

    api.delete(f"/api/meetings/{meeting['id']}/tags/{tag['assignment_id']}")
    alone = api.get("/api/brain/concept-graph", params={"include_isolated": "false"}).json()
    assert alone["nodes"] == [] and alone["hidden_isolated"] == 1


async def test_two_names_of_one_output_that_resolve_to_one_concept_make_one_mention(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(concepts=[concept("Kafka", aliases=["Apache Kafka"])]),
        "Primera",
    )
    second = await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(
            concepts=[
                concept("Kafka", evidence=("system-00000",)),
                concept("Apache Kafka", evidence=("system-00000", "system-00001")),
            ]
        ),
        "Segunda",
    )
    async with sessionmaker() as session:
        mentions = (
            (
                await session.execute(
                    select(BrainConceptMention).where(
                        BrainConceptMention.meeting_id == second["id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(mentions) == 1
    assert [e["segment_id"] for e in mentions[0].evidence] == ["system-00000", "system-00001"]


async def test_deleting_meetings_updates_types_forgets_their_aliases_and_hides_orphans(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meetings = []
    for index, kind in enumerate(("project", "project", "topic")):
        aliases = ["Manual"] if index < 2 else []
        meetings.append(
            await projected(
                api,
                sessionmaker,
                storage,
                settings,
                tmp_path,
                extraction(concepts=[concept("Documentación", kind, aliases=aliases)]),
                f"Reunión {index}",
            )
        )
    (node,) = api.get("/api/brain/concept-graph").json()["nodes"]
    assert node["type"] == "project"
    assert api.get(f"/api/brain/concepts/{node['id']}").json()["aliases"] == ["Manual"]

    for meeting in meetings[:2]:
        assert api.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    (node,) = api.get("/api/brain/concept-graph").json()["nodes"]
    assert node["type"] == "topic"

    assert api.delete(f"/api/meetings/{meetings[2]['id']}").status_code == 204
    response = api.get(f"/api/brain/concepts/{node['id']}")
    assert response.status_code == 404 and response.json()["detail"] == "CONCEPT_NOT_FOUND"
    # An alias is kept while a meeting with the transcript it came from remains (these test
    # meetings share one transcript), and forgotten with the last one.
    async with sessionmaker() as session:
        assert (await session.execute(select(BrainConceptAlias))).scalars().all() == []


async def test_reproject_queues_the_latest_extraction_again_without_the_model(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    from app.brain_backfill import _reproject

    meeting = await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        extraction(concepts=[concept("Kafka")]),
        "Primera",
    )
    async with sessionmaker() as session:
        job = await _reproject(session, meeting["id"], settings)
        await session.commit()
    assert job is not None and job.status == "queued" and job.kind == "concepts"
    assert (await run_projection(sessionmaker, storage, settings, meeting["id"])).status == (
        "completed"
    )
    async with sessionmaker() as session:
        mentions = (await session.execute(select(BrainConceptMention))).scalars().all()
    assert len(mentions) == 1


async def test_a_concept_timeline_reads_its_meetings_in_order_with_related_facts(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    def with_facts(decision, action, unrelated):
        output = extraction(concepts=[concept("Pressupost", type="topic")])
        output.parsed["decisions"] = [
            {"text": decision, "evidence_ids": ["system-00000"], "state": "decided"}
        ]
        output.parsed["actions"] = [
            {"text": action, "evidence_ids": ["system-00001"], "owner": "Marta"},
            {"text": unrelated, "evidence_ids": ["system-00001"]},
        ]
        return LLMResult(raw=json.dumps(output.parsed), parsed=output.parsed)

    first = await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        with_facts("Aprovar el pressupost inicial", "Revisar el pressupost", "Comprar cadires"),
        "Gener",
    )
    second = await projected(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        with_facts("Ampliar el pressupost un 10 %", "Enviar el pressupost nou", "Reservar sala"),
        "Febrer",
    )
    api.post(f"/api/meetings/{second['id']}/tags", json={"label": "Projecte X"})
    (node,) = [
        n for n in api.get("/api/brain/concept-graph").json()["nodes"] if n["label"] == "Pressupost"
    ]
    timeline = api.get(f"/api/brain/concepts/{node['id']}/timeline").json()
    assert [e["title"] for e in timeline["entries"]] == ["Febrer", "Gener"]  # newest first
    january = timeline["entries"][1]
    assert january["mentioned"] and not january["tagged"]
    # Facts naming the concept or citing where it is mentioned; "Comprar cadires" is unrelated.
    assert [(f["kind"], f["text"]) for f in january["facts"]] == [
        ("decision", "Aprovar el pressupost inicial"),
        ("action", "Revisar el pressupost"),
    ]
    assert january["facts"][1]["owner"] == "Marta"
    assert january["quotes"][0]["segment_id"] == "system-00000"
    assert january["facts"][0]["evidence"][0]["text"]  # the cited words

    # A tag's timeline: the meetings carrying it, with their main facts and summary.
    tags = {t["label"]: t["concept_id"] for t in api.get("/api/meetings/tags").json()}
    tag_line = api.get(f"/api/brain/concepts/{tags['Projecte X']}/timeline").json()
    assert tag_line["is_tag"] and [e["title"] for e in tag_line["entries"]] == ["Febrer"]
    assert tag_line["entries"][0]["tagged"] and tag_line["entries"][0]["summary"]
    assert {f["text"] for f in tag_line["entries"][0]["facts"]} >= {"Reservar sala"}
    assert first["id"] != second["id"]
    assert api.get("/api/brain/concepts/nope/timeline").status_code == 404


async def test_the_second_pass_adds_relationships_and_a_failing_one_keeps_the_first(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    from app.llm import LLMUnavailable
    from app.models import LLMRun, SummaryExtraction

    first = extraction(concepts=[concept("Kafka"), concept("Zookeeper"), concept("Pressupost")])
    second = LLMResult(
        raw="{}",
        parsed={"relationships": [relation("Kafka", "Zookeeper", "depends_on")]},
    )

    async def project_two(title, results):
        meeting, _summary, _queue = await project(
            api,
            sessionmaker,
            storage,
            settings,
            tmp_path,
            results,
            title=title,
            name=f"{title}.wav",
        )
        return meeting

    good = await project_two("Con segunda pasada", [first, second])
    # One failed attempt of the second pass is retried (a proxy may cut the first, slow one).
    retried = await project_two(
        "Segunda pasada reintentada", [first, LLMUnavailable("LLM_UNAVAILABLE"), second]
    )
    bad = await project_two(
        "Segunda pasada caida",
        [first, LLMUnavailable("LLM_UNAVAILABLE"), LLMUnavailable("LLM_UNAVAILABLE")],
    )

    async with sessionmaker() as session:
        results = {
            e.meeting_id: e.result
            for e in (await session.execute(select(SummaryExtraction))).scalars()
        }
        runs = (await session.execute(select(LLMRun))).scalars().all()
    assert [r["type"] for r in results[good["id"]]["relationships"]] == ["depends_on"]
    assert results[good["id"]]["relations_pass"] == {"status": "completed", "added": 1}
    assert results[retried["id"]]["relations_pass"] == {"status": "completed", "added": 1}
    # The extraction of the failing one is complete: only the second pass failed, and says so.
    assert results[bad["id"]]["relationships"] == []
    assert results[bad["id"]]["relations_pass"]["status"] == "failed"
    by_version = sorted((r.prompt_version.endswith(":relations"), r.status) for r in runs)
    assert by_version == [
        (False, "completed"),
        (False, "completed"),
        (False, "completed"),
        (True, "completed"),
        (True, "completed"),
        (True, "failed"),
    ]
