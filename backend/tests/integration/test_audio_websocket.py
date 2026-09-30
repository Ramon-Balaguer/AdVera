"""Meeting audio WebSocket: browser microphone capture into original.pcm (ADR 0004, 0008)."""

import pytest

from app.audio_sessions import AudioSessionManager
from tests.fakes import FakeEngine
from tests.integration.conftest import make_worker
from tests.integration.test_import_transcription import create_meeting, get_job, import_wav

pytestmark = pytest.mark.integration

FRAME = b"\x10\x00" * 4096  # 4096 synthetic samples, 256 ms


def receive_type(ws, expected: str) -> dict:
    event = ws.receive_json()
    assert event["type"] == expected, event
    return event


def start(ws, **extra) -> dict:
    ws.send_json({"type": "start", **extra})
    return ws.receive_json()


def test_capture_persists_microphone_track_and_queues_definitive_job(api, recording_queue, storage):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        ready = start(ws)
        assert ready["type"] == "audio.ready" and ready["resumed"] is False
        assert ready["next_sequence"] == 0
        assert ready["format"] == {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}
        assert api.get(f"/api/meetings/{meeting['id']}").json()["status"] == "recording"

        for expected in (1, 2):
            ws.send_bytes(FRAME)
            received = receive_type(ws, "audio.received")
            assert (received["sequence"], received["track_sequence"]) == (expected, expected)
        assert received["tracks"]["microphone"]["bytes"] == 2 * len(FRAME)

        ws.send_json({"type": "stop"})
        stopped = receive_type(ws, "audio.stopped")
        assert stopped["tracks"]["microphone"]["frames"] == 2
        queued = receive_type(ws, "transcript.queued")

    assert storage.track_path(meeting["id"], "microphone").stat().st_size == 2 * len(FRAME)
    assert recording_queue.published == [queued["job_id"]]
    detail = api.get(f"/api/meetings/{meeting['id']}").json()
    assert detail["status"] == "processing" and detail["tracks"] == ["microphone"]
    assert detail["ended_at"] is not None
    metrics = api.get(f"/api/meetings/{meeting['id']}/audio-metrics").json()
    assert metrics["status"] == "stopped" and metrics["tracks"]["microphone"]["frames"] == 2


async def test_captured_microphone_reaches_the_definitive_transcript(
    api, recording_queue, sessionmaker, storage, settings
):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        start(ws)
        ws.send_bytes(FRAME)
        receive_type(ws, "audio.received")
        ws.send_json({"type": "stop"})
        receive_type(ws, "audio.stopped")
        job_id = receive_type(ws, "transcript.queued")["job_id"]

    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(job_id)
    assert (await get_job(sessionmaker, job_id)).status == "completed"
    transcript = api.get(f"/api/meetings/{meeting['id']}/transcript").json()
    assert {s["track"] for s in transcript["segments"]} == {"microphone"}
    assert transcript["primary_language"] == ["ca"]


def test_frames_before_start_and_invalid_frames_are_rejected(api, recording_queue, storage):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        ws.send_bytes(FRAME)
        assert receive_type(ws, "audio.error")["code"] == "FRAME_BEFORE_START"
        start(ws)
        ws.send_bytes(b"\x01\x02\x03")  # not aligned to 16-bit samples
        assert receive_type(ws, "audio.error")["code"] == "INVALID_FRAME"
        ws.send_text("not json")
        assert receive_type(ws, "audio.error")["code"] == "INVALID_COMMAND"
    path = storage.track_path(meeting["id"], "microphone")
    assert not path.exists() or path.stat().st_size == 0


def test_disconnect_keeps_session_recoverable_and_resume_appends(api, recording_queue, storage):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        session_id = start(ws)["session_id"]
        for _ in range(2):
            ws.send_bytes(FRAME)
            receive_type(ws, "audio.received")
    # Disconnected without stop: still recording, audio kept.
    assert api.get(f"/api/meetings/{meeting['id']}").json()["status"] == "recording"
    assert api.get(f"/api/meetings/{meeting['id']}/audio-metrics").json()["next_sequence"] == 2

    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        stale = start(ws, resume=True, session_id=session_id, next_sequence=1)
        assert (stale["type"], stale["code"]) == ("audio.error", "STALE_CURSOR")
        unknown = start(ws, resume=True, session_id="another", next_sequence=2)
        assert unknown["code"] == "SESSION_NOT_RECOVERABLE"

        ready = start(ws, resume=True, session_id=session_id, next_sequence=2)
        assert (ready["type"], ready["resumed"], ready["next_sequence"]) == ("audio.ready", True, 2)
        ws.send_bytes(FRAME)
        assert receive_type(ws, "audio.received")["sequence"] == 3
        ws.send_json({"type": "stop"})
        receive_type(ws, "audio.stopped")
        receive_type(ws, "transcript.queued")

    # Resume never truncates: all three frames are stored.
    assert storage.track_path(meeting["id"], "microphone").stat().st_size == 3 * len(FRAME)


def test_resume_after_process_restart_uses_the_manifest(api, recording_queue, storage):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        session_id = start(ws)["session_id"]
        ws.send_bytes(FRAME)
        receive_type(ws, "audio.received")
    api.app.state.audio_sessions = AudioSessionManager(storage)  # in-memory state lost

    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        ready = start(ws, resume=True, session_id=session_id, next_sequence=1)
        assert (ready["type"], ready["next_sequence"]) == ("audio.ready", 1)
        assert ready["tracks"]["microphone"]["bytes"] == len(FRAME)


def test_stop_without_audio_does_not_queue_a_job(api, recording_queue, sessionmaker):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        start(ws)
        ws.send_json({"type": "stop"})
        receive_type(ws, "audio.stopped")
        assert receive_type(ws, "transcript.failed")["code"] == "NO_AUDIO"
    assert recording_queue.published == []
    assert api.get(f"/api/meetings/{meeting['id']}").json()["status"] == "scheduled"


def test_start_is_rejected_while_a_transcription_job_is_active(api, recording_queue, tmp_path):
    meeting = create_meeting(api)
    assert import_wav(api, meeting["id"], tmp_path).status_code == 202
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        assert start(ws)["code"] == "MEETING_BUSY"


async def test_recording_over_recorded_audio_is_refused_and_keeps_it(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(job_id)
    assert api.get(f"/api/meetings/{meeting['id']}").json()["status"] == "ready"

    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        assert start(ws)["code"] == "MEETING_ALREADY_RECORDED"
    # Nothing was truncated: the audio and its transcript are untouched.
    assert storage.track_path(meeting["id"], "system").stat().st_size > 0
    assert storage.transcript_path(meeting["id"]).exists()


def test_a_second_start_never_truncates_a_recording_in_progress(api, recording_queue, storage):
    meeting = create_meeting(api)
    url = f"/ws/meetings/{meeting['id']}/audio"
    with api.websocket_connect(url) as first:
        session_id = start(first)["session_id"]
        first.send_bytes(FRAME)
        receive_type(first, "audio.received")
        with api.websocket_connect(url) as second:  # another tab, a double click…
            assert start(second)["code"] == "MEETING_BUSY"
        first.send_bytes(FRAME)
        assert receive_type(first, "audio.received")["tracks"]["microphone"]["bytes"] == 2 * len(
            FRAME
        )
        # Detached (tab lost) sessions are protected the same way.
    with api.websocket_connect(url) as third:
        assert start(third)["code"] == "MEETING_BUSY"
        ready = start(third, resume=True, session_id=session_id, next_sequence=2)
        assert ready["type"] == "audio.ready" and ready["tracks"]["microphone"]["bytes"] == 2 * len(
            FRAME
        )
        third.send_json({"type": "stop"})
        receive_type(third, "audio.stopped")
    assert storage.track_path(meeting["id"], "microphone").stat().st_size == 2 * len(FRAME)


def test_start_is_refused_while_an_import_is_running(api, recording_queue):
    from app.media_import import imports_in_progress

    meeting = create_meeting(api)
    imports_in_progress.add(meeting["id"])
    try:
        with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
            assert start(ws)["code"] == "MEETING_BUSY"
    finally:
        imports_in_progress.discard(meeting["id"])


def test_a_malformed_resume_cursor_is_an_invalid_command_not_a_crash(api, recording_queue):
    meeting = create_meeting(api)
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        session_id = start(ws)["session_id"]
        for bad in ([1], {"a": 1}):
            reply = start(ws, resume=True, session_id=session_id, next_sequence=bad)
            assert (reply["type"], reply["code"]) == ("audio.error", "INVALID_COMMAND")
        ws.send_json({"type": "ping"})
        assert receive_type(ws, "pong")
