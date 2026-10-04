"""Notes with @references and speakers named as people, through Summary, Brain and the graph
(ADR 0020, ADR 0021), against real PostgreSQL."""

import pytest
from sqlalchemy import select

from app import runtime_settings, summary_jobs
from app.asr import AsrSegment
from app.brain_worker import BrainIndexWorker
from app.llm import LLMResult
from app.models import BrainChunk, BrainConcept, BrainIndexJob, SummaryExtraction, SummaryJob
from app.summary_worker import SummaryWorker
from tests.fakes import RecordingQueue
from tests.integration.test_brain_pipeline import BagOfWords, ScriptedLLM, ask, indexed_meeting
from tests.integration.test_summary_pipeline import llm_configured  # noqa: F401

pytestmark = pytest.mark.integration

GUILLEM = [
    AsrSegment(0.0, 4.0, "El proveïdor del núvol puja els preus al gener.", "ca", "SPEAKER_00"),
    AsrSegment(4.5, 8.0, "Caldrà renegociar el contracte.", "ca", "SPEAKER_01"),
]
ARA = [
    AsrSegment(0.0, 4.0, "Hoy revisamos el plan de copias.", "es", "SPEAKER_00"),
    AsrSegment(4.5, 8.0, "Yo me encargo del inventario.", "es", "SPEAKER_01"),
]


class CapturingLLM:
    name = "ollama"
    model = "scripted"

    def __init__(self, parsed):
        self.parsed = parsed
        self.prompts: list[str] = []

    async def complete_json(self, system, user, schema, *, context_tokens):
        self.prompts.append(user)
        import json

        return LLMResult(raw=json.dumps(self.parsed), parsed=self.parsed)


def extraction(evidence):
    return {
        "summary": "Se revisa el plan.",
        "summary_evidence_ids": evidence,
        "topics": [{"text": "Copias", "evidence_ids": evidence}],
        "decisions": [],
        "actions": [],
        "open_questions": [],
        "risks": [],
        "concepts": [],
        "relationships": [],
    }


@pytest.fixture
def queues(api):
    summary, index = RecordingQueue(), RecordingQueue()
    api.app.state.summary_queue = summary
    api.app.state.brain_index_queue = index
    return summary, index


async def two_meetings(api, sessionmaker, storage, settings, tmp_path):
    guillem, _ = await indexed_meeting(
        api, sessionmaker, storage, settings, tmp_path, title="Meet de Guillem", segments=GUILLEM
    )
    ara, _ = await indexed_meeting(
        api, sessionmaker, storage, settings, tmp_path, title="Seguiment", segments=ARA
    )
    return guillem, ara


def segment_id(api, meeting_id, index):
    return api.get(f"/api/meetings/{meeting_id}/transcript").json()["segments"][index]["id"]


async def test_notes_saved_while_recording_wait_and_without_an_llm_say_so(api, queues):
    meeting = api.post("/api/meetings", json={"title": "En directe"}).json()
    saved = api.put(f"/api/meetings/{meeting['id']}/notes", json={"content": "# Idea\nProvar"})
    assert saved.status_code == 200 and saved.json()["analysis"] == "waiting_transcript"
    assert api.get(f"/api/meetings/{meeting['id']}/notes").json()["content"] == "# Idea\nProvar"
    too_long = api.put(f"/api/meetings/{meeting['id']}/notes", json={"content": "x" * 50_001})
    assert too_long.status_code == 422
    assert queues[0].published == [] and queues[1].published == []


async def test_notes_with_a_reference_reach_summary_and_brain(
    api,
    queues,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    summary_queue, index_queue = queues
    guillem, ara = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    target = segment_id(api, guillem["id"], 0)
    notes = (
        "# Pla de còpies\n"
        "Cal parlar-ho amb proveïdors, com es va dir a "
        f"[@Meet de Guillem · 0:00](/meetings/{guillem['id']}?segment={target}).\n\n"
        "Recordar [@inexistent](/meetings/00000000-0000-4000-8000-000000000000)."
    )
    # A Summary job made for the transcript alone, before the notes (as after transcription).
    async with sessionmaker() as session:
        old_summary = await summary_jobs.create_or_reuse(
            session,
            meeting_id=ara["id"],
            input_sha256=api.get(f"/api/meetings/{ara['id']}/transcript").json()["segments_sha256"],
            runtime=runtime_settings.load(settings),
            settings=settings,
        )
        await session.commit()

    saved = api.put(f"/api/meetings/{ara['id']}/notes", json={"content": notes}).json()
    assert saved["analysis"] == "queued"
    assert len(summary_queue.published) == 1 and len(index_queue.published) == 1
    # Saving the same text again queues nothing.
    again = api.put(f"/api/meetings/{ara['id']}/notes", json={"content": notes}).json()
    assert again["analysis"] == "unchanged" and len(summary_queue.published) == 1
    # The reference to a meeting that does not exist is skipped; the other shows as a backlink.
    assert api.get(f"/api/meetings/{guillem['id']}/references").json() == [
        {
            "meeting_id": ara["id"],
            "title": "Seguiment",
            "segment_id": target,
            "note_block_id": "note-001",
        }
    ]

    # Summary reads the notes with the referenced words and may cite the note.
    llm = CapturingLLM(extraction(["note-001", segment_id(api, ara["id"], 0)]))
    worker = SummaryWorker(
        sessionmaker, storage, RecordingQueue(), settings, provider_factory=lambda j, s: llm
    )
    await worker.process(summary_queue.published[0])
    prompt = llm.prompts[0]
    assert "[note-001] # Pla de còpies" in prompt
    # What the note refers to is given apart, as another meeting's context.
    notes_part, context = prompt.split("Context from other meetings", 1)
    assert "puja els preus al gener" not in notes_part
    assert "[note-001] → «Meet de Guillem», 0:00:00" in context
    assert "puja els preus al gener" in context
    async with sessionmaker() as session:
        result = (
            await session.execute(
                select(SummaryExtraction.result).where(SummaryExtraction.meeting_id == ara["id"])
            )
        ).scalar_one()
    assert result["summary"]["evidence"][0] == {
        "segment_id": "note-001",
        "start": None,
        "end": None,
        "speaker": None,
        "track": "notes",
        "text": result["summary"]["evidence"][0]["text"],
    }
    assert result["summary"]["evidence"][0]["text"].startswith("# Pla de còpies")

    # A Summary job made before the notes is stale now.
    await worker.process(old_summary.id)
    async with sessionmaker() as session:
        stale = await session.get(SummaryJob, old_summary.id)
    assert stale.status == "failed" and stale.error == "INPUT_CHANGED"

    # Brain indexes the note with what it references, so the referenced words find it.
    await BrainIndexWorker(sessionmaker, storage, RecordingQueue(), settings, BagOfWords()).process(
        index_queue.published[0]
    )
    async with sessionmaker() as session:
        note_chunks = (
            (
                await session.execute(
                    select(BrainChunk).where(
                        BrainChunk.meeting_id == ara["id"], BrainChunk.track == "notes"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [c.segment_id for c in note_chunks] == ["note-001", "note-002"]
    assert "puja els preus al gener" in note_chunks[0].content
    answer = ScriptedLLM({"sufficient": True, "answer": "Al gener.", "citations": ["S1"]})
    found = await ask(
        api,
        sessionmaker,
        storage,
        settings,
        answer,
        "proveïdors preus gener",
        meeting_ids=[ara["id"]],
    )
    assert any(r["track"] == "notes" for r in found["result"]["retrieved"])
    assert found["status"] == "completed"


async def test_speakers_are_named_as_people_shared_across_meetings(
    api,
    queues,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    summary_queue, _ = queues
    guillem, ara = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    speakers = api.get(f"/api/meetings/{ara['id']}/speakers").json()["speakers"]
    assert [(s["speaker"], s["segments"], s["person"]) for s in speakers] == [
        ("SPEAKER_00", 1, None),
        ("SPEAKER_01", 1, None),
    ]
    track = speakers[0]["track"]

    named = api.put(
        f"/api/meetings/{ara['id']}/speakers",
        json={
            "assignments": [
                {"track": track, "speaker": "SPEAKER_00", "person": "Ramón"},
                {"track": track, "speaker": "SPEAKER_01", "person": "Núria"},
            ]
        },
    ).json()
    assert named["analysis"] == "queued" and len(summary_queue.published) == 1
    assert [s["person"] for s in named["speakers"]] == ["Ramón", "Núria"]
    segments = api.get(f"/api/meetings/{ara['id']}/transcript").json()["segments"]
    assert [s["person"] for s in segments] == ["Ramón", "Núria"]

    # The same person in another meeting is the same node, found as a suggestion.
    api.put(
        f"/api/meetings/{guillem['id']}/speakers",
        json={"assignments": [{"track": track, "speaker": "SPEAKER_00", "person": "ramon"}]},
    )
    assert api.get("/api/people", params={"q": "RAM"}).json()[0]["name"] == "Ramón"
    assert api.get("/api/people", params={"q": "RAM"}).json()[0]["meetings"] == 2
    nodes = {n["label"]: n for n in api.get("/api/brain/concept-graph").json()["nodes"]}
    assert nodes["Ramón"]["type"] == "person" and nodes["Ramón"]["meetings"] == 2
    detail = api.get(f"/api/brain/concepts/{nodes['Ramón']['id']}").json()
    assert all(m["spoke"] for m in detail["meetings"])

    # The prompt names the speakers.
    llm = CapturingLLM(extraction([segment_id(api, ara["id"], 0)]))
    await SummaryWorker(
        sessionmaker, storage, RecordingQueue(), settings, provider_factory=lambda j, s: llm
    ).process(summary_queue.published[0])
    assert "Ramón (SPEAKER_00)" in llm.prompts[0] and "Núria (SPEAKER_01)" in llm.prompts[0]

    bad = api.put(
        f"/api/meetings/{ara['id']}/speakers",
        json={"assignments": [{"track": track, "speaker": "SPEAKER_09", "person": "X"}]},
    )
    assert bad.status_code == 422 and bad.json()["detail"] == "UNKNOWN_SPEAKER"

    # Unnaming and deleting leave no orphan person behind.
    api.put(f"/api/meetings/{ara['id']}/speakers", json={"assignments": []})
    assert api.delete(f"/api/meetings/{guillem['id']}").status_code == 204
    async with sessionmaker() as session:
        names = (await session.execute(select(BrainConcept.canonical_name))).scalars().all()
    assert "Ramón" not in names and "Núria" not in names
    async with sessionmaker() as session:
        assert (await session.execute(select(BrainIndexJob))).scalars().all() is not None


async def test_going_back_to_earlier_notes_analyses_them_again(
    api,
    queues,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    # Found in review: A -> B -> A answered "unchanged" and left B's analysis in place.
    summary_queue, index_queue = queues
    _guillem, ara = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    url = f"/api/meetings/{ara['id']}/notes"
    worker = SummaryWorker(
        sessionmaker,
        storage,
        RecordingQueue(),
        settings,
        provider_factory=lambda j, s: CapturingLLM(extraction(["note-001"])),
    )
    indexer = BrainIndexWorker(sessionmaker, storage, RecordingQueue(), settings, BagOfWords())

    async def save_and_run(content):
        assert api.put(url, json={"content": content}).json()["analysis"] == "queued"
        await worker.process(summary_queue.published[-1])
        await indexer.process(index_queue.published[-1])

    await save_and_run("Versió A del pla.")
    first_summary, first_index = summary_queue.published[-1], index_queue.published[-1]
    await save_and_run("Versió B del pla.")
    await save_and_run("Versió A del pla.")
    assert summary_queue.published[-1] == first_summary and index_queue.published[-1] == first_index
    async with sessionmaker() as session:
        latest = (
            await session.execute(
                select(SummaryExtraction.result)
                .where(SummaryExtraction.meeting_id == ara["id"])
                .order_by(SummaryExtraction.generated_at.desc())
                .limit(1)
            )
        ).scalar_one()
        chunks = (
            (
                await session.execute(
                    select(BrainChunk.content).where(
                        BrainChunk.meeting_id == ara["id"], BrainChunk.track == "notes"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert latest["summary"]["evidence"][0]["text"] == "Versió A del pla."
    assert chunks == ["Versió A del pla."]


async def test_the_same_note_line_in_two_meetings_is_found_in_both(
    api,
    queues,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    _summary_queue, index_queue = queues
    guillem, ara = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    indexer = BrainIndexWorker(sessionmaker, storage, RecordingQueue(), settings, BagOfWords())
    for meeting in (guillem, ara):
        api.put(f"/api/meetings/{meeting['id']}/notes", json={"content": "- Revisar pressupost"})
        await indexer.process(index_queue.published[-1])
    answer = ScriptedLLM({"sufficient": True, "answer": "Sí.", "citations": ["S1"]})
    found = await ask(api, sessionmaker, storage, settings, answer, "revisar pressupost")
    notes = {r["meeting_id"] for r in found["result"]["retrieved"] if r["track"] == "notes"}
    assert notes == {guillem["id"], ara["id"]}


async def test_a_name_given_to_a_label_the_transcript_no_longer_has_is_ignored(
    api, queues, sessionmaker, storage, settings, tmp_path
):
    from app import analysis_input
    from app.models import MeetingSpeaker

    _guillem, ara = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    track = api.get(f"/api/meetings/{ara['id']}/speakers").json()["speakers"][0]["track"]
    api.put(
        f"/api/meetings/{ara['id']}/speakers",
        json={"assignments": [{"track": track, "speaker": "SPEAKER_00", "person": "Joan"}]},
    )
    async with sessionmaker() as session:
        row = (await session.execute(select(MeetingSpeaker))).scalar_one()
        row.speaker_label = "SPEAKER_07"  # as after a re-transcription that renumbered voices
        await session.commit()
        loaded = await analysis_input.load(session, storage, ara["id"], expand=False)
    assert loaded.people == {}
    transcript = loaded.transcript
    assert loaded.summary_sha256 == transcript.segments_sha256  # nothing named, nothing changes
