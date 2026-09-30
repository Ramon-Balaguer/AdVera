"""Real Capture Agent against a real backend server (agent-pcm-e2e-delivery-fix.md).

A uvicorn server runs the actual app; the actual `RemoteAgent` connects outbound with
synthetic captures. PCM must reach `original.pcm` and `system.pcm` directly (ADR 0010),
with the meeting WebSocket only receiving lifecycle events and metrics.
"""

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
import websockets

from app.config import get_settings

agent_remote = pytest.importorskip("advera_agent.remote")
agent_config = pytest.importorskip("advera_agent.config")

pytestmark = pytest.mark.integration

FRAME = b"\x10\x00" * 4096
FRAMES = 5


class SyntheticCapture:
    def __init__(self, track: str) -> None:
        self.track = track
        self.stopped = threading.Event()

    def start(self, sink) -> None:
        def run() -> None:
            for _ in range(FRAMES):
                if self.stopped.is_set():
                    return
                sink(FRAME)
                time.sleep(0.02)

        threading.Thread(target=run, daemon=True).start()

    def stop(self) -> None:
        self.stopped.set()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def server(database, settings, monkeypatch):
    for name, value in {
        "DATABASE_URL": settings.database_url,
        "REDIS_URL": settings.redis_url,
        "AUDIO_STORAGE_PATH": settings.audio_storage_path,
        "TRANSCRIPTION_QUEUE_NAME": settings.transcription_queue_name,
        "CAPTURE_AGENT_TOKEN": "e2e-token",
        "ASR_DEFINITIVE_PROVIDER": settings.asr_definitive_provider,
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    from app.main import app

    port = free_port()
    instance = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    while not instance.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    instance.should_exit = True
    thread.join(timeout=10)
    get_settings.cache_clear()


async def next_event(ws, kind: str, timeout: float = 10) -> dict:
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if event["type"] == kind:
            return event


async def test_agent_tracks_reach_the_meeting_session_directly(server, storage):
    base = server
    async with httpx.AsyncClient(base_url=base) as http:
        meeting = (await http.post("/api/meetings", json={"title": "Agent E2E"})).json()

        config = agent_config.AgentConfig(
            base, agent_id="agent-e2e", token="e2e-token", consent="always"
        )
        agent = agent_remote.RemoteAgent(
            config,
            capture_factory=SyntheticCapture,
            capabilities=lambda: {
                "microphone": {"state": "available"},
                "system": {"state": "available"},
            },
        )
        agent_task = asyncio.create_task(agent.run())
        for _ in range(100):
            capabilities = (await http.get("/api/capture-agent/capabilities")).json()
            if capabilities["available"]:
                break
            await asyncio.sleep(0.05)
        assert capabilities["tracks"] == {
            "microphone": {"state": "available"},
            "system": {"state": "available"},
        }

        ws_url = base.replace("http", "ws") + f"/ws/meetings/{meeting['id']}/audio"
        async with websockets.connect(ws_url) as meeting_ws:
            await meeting_ws.send(json.dumps({"type": "start", "source": "agent"}))
            await next_event(meeting_ws, "audio.ready")

            response = await http.post(
                "/api/capture-agent/sessions",
                json={"meeting_id": meeting["id"], "tracks": ["microphone", "system"]},
            )
            assert response.status_code == 201, response.text
            capture = response.json()
            assert capture["state"] == "recording"
            current = (await http.get("/api/capture-agent/sessions/current")).json()
            assert current["capture_session_id"] == capture["capture_session_id"]

            # Per-track metrics are relayed to the meeting socket; wait for every frame.
            seen = {"microphone": 0, "system": 0}
            while min(seen.values()) < FRAMES:
                event = await next_event(meeting_ws, "audio.received")
                for track, metrics in event["tracks"].items():
                    seen[track] = metrics["frames"]

            await meeting_ws.send(json.dumps({"type": "stop"}))
            stopped = await next_event(meeting_ws, "audio.stopped")
            queued = await next_event(meeting_ws, "transcript.queued")

        assert stopped["tracks"]["microphone"]["frames"] == FRAMES
        assert stopped["tracks"]["system"]["frames"] == FRAMES
        assert queued["job_id"]
        mic = storage.track_path(meeting["id"], "microphone")
        system = storage.track_path(meeting["id"], "system")
        assert mic.stat().st_size == FRAMES * len(FRAME)
        assert system.stat().st_size == FRAMES * len(FRAME)
        assert (await http.get("/api/capture-agent/sessions/current")).status_code == 404
        detail = (await http.get(f"/api/meetings/{meeting['id']}")).json()
        assert detail["tracks"] == ["microphone", "system"]
        assert detail["status"] == "processing"

        agent.shutdown()
        await asyncio.wait_for(agent_task, 10)


async def test_agent_without_the_token_is_rejected(server):
    config = agent_config.AgentConfig(server, agent_id="intruder", token="wrong")
    agent = agent_remote.RemoteAgent(config, capabilities=lambda: {})
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(1)
    async with httpx.AsyncClient(base_url=server) as http:
        assert (await http.get("/api/capture-agent/capabilities")).json()["available"] is False
    agent.shutdown()
    await asyncio.wait_for(task, 10)


async def test_capture_start_requires_a_recording_meeting_and_an_agent(server):
    async with httpx.AsyncClient(base_url=server) as http:
        meeting = (await http.post("/api/meetings", json={"title": "No agent"})).json()
        response = await http.post(
            "/api/capture-agent/sessions", json={"meeting_id": meeting["id"]}
        )
        assert (response.status_code, response.json()["detail"]) == (503, "AGENT_UNAVAILABLE")


class LongCapture(SyntheticCapture):
    """Keeps producing frames for ~10 s, so the test can pull the plug mid-recording."""

    def start(self, sink) -> None:
        def run() -> None:
            for _ in range(500):
                if self.stopped.is_set():
                    return
                sink(FRAME)
                time.sleep(0.02)

        threading.Thread(target=run, daemon=True).start()


async def start_agent_recording(base, http, title, capture_class, tracks=("microphone",)):
    meeting = (await http.post("/api/meetings", json={"title": title})).json()
    config = agent_config.AgentConfig(
        base, agent_id="agent-e2e", token="e2e-token", consent="always"
    )
    agent = agent_remote.RemoteAgent(
        config,
        capture_factory=capture_class,
        capabilities=lambda: {
            "microphone": {"state": "available"},
            "system": {"state": "available"},
        },
    )
    task = asyncio.create_task(agent.run())
    for _ in range(100):
        if (await http.get("/api/capture-agent/capabilities")).json()["available"]:
            break
        await asyncio.sleep(0.05)
    meeting_ws = await websockets.connect(
        base.replace("http", "ws") + f"/ws/meetings/{meeting['id']}/audio"
    )
    await meeting_ws.send(json.dumps({"type": "start", "source": "agent"}))
    await next_event(meeting_ws, "audio.ready")
    response = await http.post(
        "/api/capture-agent/sessions", json={"meeting_id": meeting["id"], "tracks": list(tracks)}
    )
    assert response.status_code == 201, response.text
    return meeting, agent, task, meeting_ws, response.json()


async def test_losing_the_agent_mid_recording_is_reported_and_the_audio_is_kept(server, storage):
    async with httpx.AsyncClient(base_url=server) as http:
        meeting, agent, task, meeting_ws, _capture = await start_agent_recording(
            server, http, "Reunió de seguiment: pressupost i llançament", LongCapture
        )
        await next_event(meeting_ws, "audio.received")

        agent.shutdown()  # the agent process goes away while recording
        await asyncio.wait_for(task, 10)
        lost = await next_event(meeting_ws, "capture.error")
        assert lost["code"] == "AGENT_DISCONNECTED"
        assert (await http.get("/api/capture-agent/sessions/current")).status_code == 404

        # The recording is still finalizable, with the audio captured so far.
        await meeting_ws.send(json.dumps({"type": "stop"}))
        stopped = await next_event(meeting_ws, "audio.stopped")
        assert stopped["tracks"]["microphone"]["frames"] > 0
        assert (await next_event(meeting_ws, "transcript.queued"))["job_id"]
        assert storage.track_path(meeting["id"], "microphone").stat().st_size > 0
        await meeting_ws.close()


async def test_a_second_writer_is_rejected_on_the_track_channel(server):
    async with httpx.AsyncClient(base_url=server) as http:
        _meeting, agent, task, meeting_ws, capture = await start_agent_recording(
            server, http, "Reunión de prueba con dos escritores", LongCapture
        )
        ws_base = server.replace("http", "ws")
        url = (
            f"{ws_base}/ws/capture-agents/agent-e2e/sessions/"
            f"{capture['capture_session_id']}/tracks/microphone/pcm"
        )
        headers = {"Authorization": "Bearer e2e-token"}
        # The agent already writes this track: a second connection cannot interleave audio.
        with pytest.raises(websockets.exceptions.InvalidStatus):
            async with websockets.connect(url, additional_headers=headers):
                pass

        agent.shutdown()
        await asyncio.wait_for(task, 10)
        await meeting_ws.close()


async def test_oversized_pcm_frame_and_malformed_events_do_not_break_the_channels(server):
    async with httpx.AsyncClient(base_url=server) as http:
        meeting = (await http.post("/api/meetings", json={"title": "Frame massa gran"})).json()
        ws_base = server.replace("http", "ws")
        headers = {"Authorization": "Bearer e2e-token"}
        async with websockets.connect(
            f"{ws_base}/ws/capture-agents/fake-agent", additional_headers=headers
        ) as control:
            await control.send(
                json.dumps(
                    {
                        "type": "agent.hello",
                        "pcm_transports": ["per-track"],
                        "capabilities": {"microphone": {"state": "available"}},
                    }
                )
            )
            assert json.loads(await control.recv())["type"] == "agent.welcome"
            async with websockets.connect(
                f"{ws_base}/ws/meetings/{meeting['id']}/audio"
            ) as meeting_ws:
                await meeting_ws.send(json.dumps({"type": "start", "source": "agent"}))
                await next_event(meeting_ws, "audio.ready")
                request = asyncio.create_task(
                    http.post(
                        "/api/capture-agent/sessions",
                        json={"meeting_id": meeting["id"], "tracks": ["microphone"]},
                    )
                )
                start = json.loads(await control.recv())
                assert start["type"] == "capture.start"
                pcm_url = (
                    f"{ws_base}/ws/capture-agents/fake-agent/sessions/"
                    f"{start['capture_session_id']}/tracks/microphone/pcm"
                )
                async with websockets.connect(pcm_url, additional_headers=headers) as pcm:
                    hello = {
                        "type": "track.hello",
                        "track": "microphone",
                        "format": {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1},
                    }
                    await pcm.send(json.dumps(hello))
                    assert json.loads(await pcm.recv())["type"] == "track.ready"
                    ready = {
                        "type": "capture.ready",
                        "capture_session_id": start["capture_session_id"],
                        "tracks": ["microphone"],
                    }
                    await control.send(json.dumps(ready))
                    assert (await request).status_code == 201
                    await control.send("[1, 2, 3]")  # not an object: ignored, no crash
                    levels = {
                        "type": "levels",
                        "capture_session_id": start["capture_session_id"],
                        "track": "microphone",
                        "level": [1],
                    }
                    await control.send(json.dumps(levels))  # not a number: treated as silence
                    await pcm.send(b"\x00\x00" * (300 * 1024 // 2))  # over the 256 KiB limit
                    with pytest.raises(websockets.exceptions.ConnectionClosed) as closed:
                        await asyncio.wait_for(pcm.recv(), 10)
                    assert closed.value.rcvd.code == 1009
                # The control channel survived the malformed events.
                await control.send(json.dumps({"type": "capabilities", "capabilities": {}}))
                await asyncio.sleep(0.2)
                assert (await http.get("/api/capture-agent/capabilities")).status_code == 200
