"""Meeting bot end to end against real PostgreSQL and Redis (ADR 0026, ADR 0027).

Vexa is the fake in tests/fake_vexa.py; everything on AdVera's side is real: the API, the
lifecycle, the webhook, the lease-fenced ingestion with ffmpeg, the durable transcription job,
the worker and the analysis input. One test per platform (Google Meet and Teams).
"""

import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app import analysis_input, runtime_settings
from app.asr import AsrSegment
from app.meeting_bot import poll
from app.models import Meeting, MeetingBotSession
from app.runtime_settings import RuntimeSettings
from tests.fake_vexa import FakeVexa, fixture
from tests.fakes import FakeEngine, write_sine_wav
from tests.integration.conftest import make_worker

pytestmark = pytest.mark.integration

SECRET = "webhook-secret-for-tests"
MEET_URL = "https://meet.google.com/abc-defg-hij"
TEAMS_URL = "https://teams.microsoft.com/meet/3812345678901?p=Ab12Cd"


@pytest.fixture
def vexa(api, settings, recording_queue, tmp_path):
    runtime_settings.save(
        settings,
        RuntimeSettings(
            llm_base_url="http://localhost:11434",
            llm_output_language="es",
            vexa_base_url="http://vexa:8056",
            vexa_api_key="test-vexa-key",
            vexa_webhook_secret=SECRET,
        ),
    )
    wav = write_sine_wav(tmp_path / "call.wav", seconds=4.0)
    fake = FakeVexa(recording=wav.read_bytes())
    context = api.app.state.meeting_bot
    context.client_factory = fake.factory
    context.queue = recording_queue
    return fake


def create_meeting(api, title="Llamada sintética") -> str:
    response = api.post("/api/meetings", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


def send_bot(api, meeting_id: str, url: str = MEET_URL):
    return api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": url})


def send_webhook(api, envelope: dict, secret: str = SECRET):
    body = json.dumps(envelope).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return api.post(
        "/api/integrations/vexa/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-webhook-timestamp": timestamp,
            "x-webhook-signature": f"sha256={signature.hexdigest()}",
        },
    )


def call_engine() -> FakeEngine:
    """AdVera's own transcript of the call: two diarized voices on the system track."""
    return FakeEngine(
        results=[
            [
                AsrSegment(0.0, 1.0, "Bon dia a tothom", language="ca", speaker="SPEAKER_00"),
                AsrSegment(2.0, 3.4, "Hola, ¿empezamos?", language="es", speaker="SPEAKER_01"),
            ]
        ]
    )


async def test_a_google_meet_call_reaches_ready_with_names_and_chat(
    api, vexa, recording_queue, sessionmaker, storage, settings
):
    meeting_id = create_meeting(api)
    assert api.get("/api/meeting-bot/capabilities").json() == {
        "configured": True,
        "available": True,
        "bot_name": "AdVera Notekeeper",
        "platforms": ["google_meet", "teams"],
    }

    sent = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": MEET_URL})
    assert sent.status_code == 201, sent.text
    bot = sent.json()
    assert (bot["platform"], bot["status"], bot["active"]) == ("google_meet", "requested", True)
    assert bot["meet_url"] == MEET_URL
    assert api.get(f"/api/meetings/{meeting_id}").json()["status"] == "recording"
    assert vexa.bodies[0]["transcribe_enabled"] is False

    # One source per meeting while the bot owns it.
    again = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": MEET_URL})
    assert (again.status_code, again.json()["detail"]) == (409, "BOT_ALREADY_ACTIVE")
    imported = api.post(
        f"/api/meetings/{meeting_id}/imports",
        files={"file": ("x.wav", (storage.root / "x").as_posix().encode(), "audio/wav")},
    )
    assert (imported.status_code, imported.json()["detail"]) == (409, "MEETING_BUSY")
    assert api.delete(f"/api/meetings/{meeting_id}").status_code == 409
    with api.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as socket:
        socket.send_json({"type": "start"})
        assert socket.receive_json() == {"type": "audio.error", "code": "MEETING_BUSY"}

    # Admitted: the status follows Vexa, and the recording notice is tried in the chat.
    vexa.set_status("active")
    async with sessionmaker() as session:  # make the page's next read ask Vexa
        row = (await session.execute(select(MeetingBotSession))).scalar_one()
        row.checked_at = None
        await session.commit()
    live = api.get(f"/api/meetings/{meeting_id}/bot").json()
    assert live["status"] == "active"
    assert live["joined_at"] is not None
    assert live["consent_notice"] == "unsupported"  # Vexa 0.12 cannot write in the chat
    assert any(path.endswith("/chat") for path in vexa.paths("POST"))

    left = api.delete(f"/api/meetings/{meeting_id}/bot")
    assert (left.status_code, left.json()["status"]) == (200, "stopping")
    assert any(path.startswith("/bots/google_meet/") for path in vexa.paths("DELETE"))

    # The bot left: the signed webhook makes AdVera ask Vexa and ingest the call.
    vexa.set_status("completed")
    hook = send_webhook(api, fixture("webhook_meeting_completed.json"))
    assert (hook.status_code, hook.json()) == (202, {"status": "accepted"})

    done = api.get(f"/api/meetings/{meeting_id}/bot").json()
    assert (done["status"], done["active"], done["error"]) == ("completed", False, None)
    meeting = api.get(f"/api/meetings/{meeting_id}").json()
    assert meeting["status"] == "processing"
    assert meeting["tracks"] == ["system"]
    assert meeting["started_at"].startswith("2026-10-16T10:00:00")
    assert meeting["duration"] == pytest.approx(4.0, abs=0.05)
    assert len(recording_queue.published) == 1
    assert not list(storage.meeting_dir(meeting_id).glob(".bot-recording-*"))  # audio only

    chat = api.get(f"/api/meetings/{meeting_id}/chat").json()
    assert [(m["id"], m["sender"], m["text"], m["offset_s"]) for m in chat] == [
        ("chat-001", "Marta Prueba", "Os paso el enlace del presupuesto", 1.5),
        ("chat-002", "Ramón Prueba", "Gràcies!", 3.8),
    ]

    # AdVera's transcription; the bot's names go to the diarized labels by overlap.
    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"faster-whisper": call_engine()}
    )
    await worker.process(recording_queue.published[0])
    assert api.get(f"/api/meetings/{meeting_id}").json()["status"] == "ready"
    speakers = api.get(f"/api/meetings/{meeting_id}/speakers").json()["speakers"]
    assert {(s["speaker"], s["person"]) for s in speakers} == {
        ("SPEAKER_00", "Ramón Prueba"),
        ("SPEAKER_01", "Marta Prueba"),
    }
    transcript = api.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert [s["person"] for s in transcript["segments"]] == ["Ramón Prueba", "Marta Prueba"]

    # The chat is part of what Summary and Brain read, citable by its block ids.
    async with sessionmaker() as session:
        analysis = await analysis_input.load(session, storage, meeting_id)
    assert [block.id for block in analysis.chat] == ["chat-001", "chat-002"]
    assert analysis.chat[0].track == "chat"
    assert analysis.brain_sha256 != analysis.transcript.segments_sha256

    # A webhook for the finished call changes nothing; a bad signature is refused.
    assert send_webhook(api, fixture("webhook_meeting_completed.json")).json() == {
        "status": "ignored"
    }
    forged = send_webhook(api, fixture("webhook_meeting_completed.json"), secret="other")
    assert (forged.status_code, forged.json()["detail"]) == (401, "INVALID_SIGNATURE")

    # Audio is stored now: no second bot, ever.
    later = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": MEET_URL})
    assert (later.status_code, later.json()["detail"]) == (409, "MEETING_ALREADY_RECORDED")


async def test_a_teams_call_with_passcode_is_ingested_by_the_worker_poll(
    api, vexa, recording_queue, sessionmaker, storage, settings
):
    """No webhook at all: the transcription worker's poll follows the bot to the end."""
    meeting_id = create_meeting(api, "Teams sintético")
    sent = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": TEAMS_URL})
    assert sent.status_code == 201, sent.text
    bot = sent.json()
    assert bot["platform"] == "teams"
    assert bot["meet_url"] == "https://teams.microsoft.com/meet/3812345678901"
    assert vexa.bodies[0]["passcode"] == "Ab12Cd"
    async with sessionmaker() as session:
        row = (await session.execute(select(MeetingBotSession))).scalar_one()
        assert "Ab12Cd" not in json.dumps(
            {c.name: str(getattr(row, c.name)) for c in row.__table__.columns}
        )

    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"faster-whisper": call_engine()}
    )
    worker.meeting_bot.client_factory = vexa.factory
    vexa.set_status("active")
    await poll(worker.meeting_bot)
    assert api.get(f"/api/meetings/{meeting_id}/bot").json()["status"] == "active"

    # Vexa still finalizing the recording: the session waits and is retried.
    vexa.set_status("completed")
    vexa.recording_status = "in_progress"
    await poll(worker.meeting_bot)
    waiting = api.get(f"/api/meetings/{meeting_id}/bot").json()
    assert (waiting["status"], waiting["error"]) == ("ended", "RECORDING_NOT_READY")
    assert recording_queue.published == []

    vexa.recording_status = "completed"
    await poll(worker.meeting_bot)
    assert api.get(f"/api/meetings/{meeting_id}/bot").json()["status"] == "completed"
    assert len(recording_queue.published) == 1
    await worker.process(recording_queue.published[0])
    names = {
        s["person"] for s in api.get(f"/api/meetings/{meeting_id}/speakers").json()["speakers"]
    }
    assert names == {"Ramón Prueba", "Marta Prueba"}


async def test_a_name_the_user_gave_is_never_replaced_by_the_bot(
    api, vexa, recording_queue, sessionmaker, storage, settings
):
    meeting_id = create_meeting(api)
    assert send_bot(api, meeting_id).status_code == 201
    vexa.set_status("completed")
    send_webhook(api, fixture("webhook_meeting_completed.json"))
    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"faster-whisper": call_engine()}
    )
    await worker.process(recording_queue.published[0])
    renamed = api.put(
        f"/api/meetings/{meeting_id}/speakers",
        json={"assignments": [{"track": "system", "speaker": "SPEAKER_00", "person": "Pere"}]},
    )
    assert renamed.status_code == 200
    from app.meeting_bot import name_speakers
    from app.transcripts import parse_definitive

    document = parse_definitive(storage.read_transcript(meeting_id))
    async with sessionmaker() as session:
        added = await name_speakers(session, meeting_id, document)
        await session.commit()
    assert added  # it proposes both, but only the unnamed one is stored
    people = {
        s["speaker"]: s["person"]
        for s in api.get(f"/api/meetings/{meeting_id}/speakers").json()["speakers"]
    }
    assert people == {"SPEAKER_00": "Pere", "SPEAKER_01": "Marta Prueba"}


async def test_a_bot_that_fails_gives_the_meeting_back(api, vexa, sessionmaker):
    meeting_id = create_meeting(api)
    assert send_bot(api, meeting_id).status_code == 201
    vexa.set_status("failed")
    hook = send_webhook(api, fixture("webhook_meeting_completed.json"))
    assert hook.json() == {"status": "accepted"}
    failed = api.get(f"/api/meetings/{meeting_id}/bot").json()
    assert (failed["status"], failed["error"], failed["active"]) == ("failed", "BOT_FAILED", False)
    async with sessionmaker() as session:
        meeting = await session.get(Meeting, meeting_id)
        assert (meeting.status, meeting.started_at) == ("scheduled", None)
    # Another bot (or the microphone) may record it now.
    vexa.set_status("requested")
    assert send_bot(api, meeting_id).status_code == 201


async def test_errors_use_the_documented_codes(api, vexa, settings):
    meeting_id = create_meeting(api)
    bad = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": "https://x.example/a"})
    assert (bad.status_code, bad.json()["detail"]) == (400, "INVALID_MEET_URL")
    missing = api.post(
        "/api/meetings/00000000-0000-4000-8000-000000000000/bot", json={"meet_url": MEET_URL}
    )
    assert (missing.status_code, missing.json()["detail"]) == (404, "MEETING_NOT_FOUND")
    assert api.get(f"/api/meetings/{meeting_id}/bot").status_code == 404
    assert api.delete(f"/api/meetings/{meeting_id}/bot").json()["detail"] == "BOT_NOT_ACTIVE"

    vexa.fail_start = 503
    down = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": MEET_URL})
    assert (down.status_code, down.json()["detail"]) == (502, "BOT_PROVIDER_UNAVAILABLE")
    assert api.get(f"/api/meetings/{meeting_id}").json()["status"] == "scheduled"

    runtime = runtime_settings.load(settings)
    runtime_settings.save(settings, runtime.model_copy(update={"vexa_api_key": ""}))
    unset = api.post(f"/api/meetings/{meeting_id}/bot", json={"meet_url": MEET_URL})
    assert (unset.status_code, unset.json()["detail"]) == (503, "BOT_PROVIDER_NOT_CONFIGURED")
