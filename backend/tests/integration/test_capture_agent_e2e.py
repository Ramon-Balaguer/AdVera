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

agent_remote = pytest.importorskip("agent.remote")
agent_config = pytest.importorskip("agent.config")

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

        config = agent_config.AgentConfig(base, agent_id="agent-e2e", token="e2e-token")
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
