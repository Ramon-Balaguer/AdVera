"""Notes with @references and speakers named as people, through Brain, Memory and the graph
(ADR 0020, ADR 0021), against real PostgreSQL."""

import pytest
from sqlalchemy import select

from app import brain_jobs, runtime_settings
from app.asr import AsrSegment
from app.brain_worker import BrainWorker
from app.llm import LLMResult
from app.memory_worker import MemoryIndexWorker
from app.models import BrainExtraction, BrainJob, MemoryChunk, MemoryConcept, MemoryIndexJob
from tests.fakes import RecordingQueue
from tests.integration.test_brain_pipeline import llm_configured  # noqa: F401
from tests.integration.test_memory_pipeline import BagOfWords, ScriptedLLM, ask, indexed_meeting

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
    brain, index = RecordingQueue(), RecordingQueue()
    api.app.state.brain_queue = brain
    api.app.state.memory_index_queue = index
    return brain, index


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


async def test_notes_with_a_reference_reach_brain_and_memory(
    api,
    queues,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    brain_queue, index_queue = queues
    guillem, ara = await two_meetings(api, sessionmaker, storage, settings, tmp_path)
    target = segment_id(api, guillem["id"], 0)
    notes = (
        "# Pla de còpies\n"
        "Cal parlar-ho amb proveïdors, com es va dir a "
        f"[@Meet de Guillem · 0:00](/meetings/{guillem['id']}?segment={target}).\n\n"
        "Recordar [@inexistent](/meetings/00000000-0000-4000-8000-000000000000)."
    )
    # A Brain job made for the transcript alone, before the notes (as after transcription).
    async with sessionmaker() as session:
        old_brain = await brain_jobs.create_or_reuse(
            session,
            meeting_id=ara["id"],
            input_sha256=api.get(f"/api/meetings/{ara['id']}/transcript").json()["segments_sha256"],
            runtime=runtime_settings.load(settings),
            settings=settings,
        )
        await session.commit()

    saved = api.put(f"/api/meetings/{ara['id']}/notes", json={"content": notes}).json()
    assert saved["analysis"] == "queued"
    assert len(brain_queue.published) == 1 and len(index_queue.published) == 1
    # Saving the same text again queues nothing.
    again = api.put(f"/api/meetings/{ara['id']}/notes", json={"content": notes}).json()
    assert again["analysis"] == "unchanged" and len(brain_queue.published) == 1
    # The reference to a meeting that does not exist is skipped; the other shows as a backlink.
    assert api.get(f"/api/meetings/{guillem['id']}/references").json() == [
        {
            "meeting_id": ara["id"],
            "title": "Seguiment",
            "segment_id": target,
            "note_block_id": "note-001",
        }
    ]

    # Brain reads the notes with the referenced words and may cite the note.
    llm = CapturingLLM(extraction(["note-001", segment_id(api, ara["id"], 0)]))
    worker = BrainWorker(
        sessionmaker, storage, RecordingQueue(), settings, provider_factory=lambda j, s: llm
    )
    await worker.process(brain_queue.published[0])
    prompt = llm.prompts[0]
    assert "[note-001] # Pla de còpies" in prompt
    assert "→ «Meet de Guillem», 0:00:00" in prompt and "puja els preus al gener" in prompt
    async with sessionmaker() as session:
        result = (
            await session.execute(
                select(BrainExtraction.result).where(BrainExtraction.meeting_id == ara["id"])
            )
        ).scalar_one()
    assert result["summary"]["evidence"][0] == {
        "segment_id": "note-001",
        "start": None,
        "end": None,
        "speaker": None,
        "track": "notes",
    }

    # A Brain job made before the notes is stale now.
    await worker.process(old_brain.id)
    async with sessionmaker() as session:
        stale = await session.get(BrainJob, old_brain.id)
    assert stale.status == "failed" and stale.error == "INPUT_CHANGED"

    # Memory indexes the note with what it references, so the referenced words find it.
    await MemoryIndexWorker(
        sessionmaker, storage, RecordingQueue(), settings, BagOfWords()
    ).process(index_queue.published[0])
    async with sessionmaker() as session:
        note_chunks = (
            (
                await session.execute(
                    select(MemoryChunk).where(
                        MemoryChunk.meeting_id == ara["id"], MemoryChunk.track == "notes"
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
    brain_queue, _ = queues
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
    assert named["analysis"] == "queued" and len(brain_queue.published) == 1
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
    nodes = {n["label"]: n for n in api.get("/api/memory/concept-graph").json()["nodes"]}
    assert nodes["Ramón"]["type"] == "person" and nodes["Ramón"]["meetings"] == 2
    detail = api.get(f"/api/memory/concepts/{nodes['Ramón']['id']}").json()
    assert all(m["spoke"] for m in detail["meetings"])

    # The prompt names the speakers.
    llm = CapturingLLM(extraction([segment_id(api, ara["id"], 0)]))
    await BrainWorker(
        sessionmaker, storage, RecordingQueue(), settings, provider_factory=lambda j, s: llm
    ).process(brain_queue.published[0])
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
        names = (await session.execute(select(MemoryConcept.canonical_name))).scalars().all()
    assert "Ramón" not in names and "Núria" not in names
    async with sessionmaker() as session:
        assert (await session.execute(select(MemoryIndexJob))).scalars().all() is not None
