"""Agent protocol against an in-process fake backend (websockets server)."""

import asyncio
import json

import pytest
import websockets

from advera_agent.config import AgentConfig
from advera_agent.remote import RemoteAgent
from tests.fakes import FRAME, FakeCapture, available


class FakeBackend:
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self.control = None
        self.connected = asyncio.Event()
        self.events: asyncio.Queue = asyncio.Queue()
        self.frames: dict[str, list[bytes]] = {}
        self.hellos: list[dict] = []
        self.connections = 0
        self.close_pcm_after: int | None = None  # simulate a track channel that dies

    async def handler(self, websocket):
        auth = websocket.request.headers.get("Authorization")
        if self.token and auth != f"Bearer {self.token}":
            await websocket.close(code=4401)
            return
        path = websocket.request.path
        if path.endswith("/pcm"):
            track = path.split("/tracks/")[1].split("/")[0]
            hello = json.loads(await websocket.recv())
            assert hello["type"] == "track.hello" and hello["track"] == track
            assert hello["format"] == {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}
            await websocket.send(json.dumps({"type": "track.ready", "track": track}))
            async for message in websocket:
                self.frames.setdefault(track, []).append(message)
                if self.close_pcm_after and len(self.frames[track]) >= self.close_pcm_after:
                    await websocket.close(code=1011)
                    return
            return
        self.connections += 1
        hello = json.loads(await websocket.recv())
        self.hellos.append(hello)
        await websocket.send(json.dumps({"type": "agent.welcome", "pcm_transport": "per-track"}))
        self.control = websocket
        self.connected.set()
        async for message in websocket:
            await self.events.put(json.loads(message))

    async def command(self, **payload):
        await self.control.send(json.dumps(payload))

    async def next_event(self, kind: str, timeout: float = 5) -> dict:
        while True:
            event = await asyncio.wait_for(self.events.get(), timeout)
            if event["type"] == kind:
                return event


@pytest.fixture
async def backend():
    fake = FakeBackend(token="secret-token")
    server = await websockets.serve(fake.handler, "127.0.0.1", 0)
    fake.url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    yield fake
    server.close()
    await server.wait_closed()


def make_agent(backend, factory=None, notified=None, consent="always", confirm=None):
    cfg = AgentConfig(backend.url, agent_id="agent-1", token="secret-token", consent=consent)
    return RemoteAgent(
        cfg,
        confirm=confirm,
        capture_factory=factory or (lambda track: FakeCapture(track)),
        capabilities=available,
        notify=(notified.append if notified is not None else None),
    )


async def test_dual_track_capture_uses_independent_channels(backend):
    notified: list[str] = []
    agent = make_agent(backend, notified=notified)
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    hello = backend.hellos[0]
    assert hello["pcm_transports"] == ["per-track"]
    assert hello["capabilities"]["system"]["state"] == "available"

    await backend.command(
        type="capture.start", capture_session_id="c1", tracks=["microphone", "system"]
    )
    ready = await backend.next_event("capture.ready")
    assert ready == {
        "type": "capture.ready",
        "capture_session_id": "c1",
        "tracks": ["microphone", "system"],
    }
    assert notified == ["AdVera está grabando"]
    level = await backend.next_event("levels")
    assert level["capture_session_id"] == "c1" and level["track"] in ("microphone", "system")

    await asyncio.sleep(0.3)
    await backend.command(type="capture.stop", capture_session_id="c1")
    await backend.next_event("capture.stopped")
    assert backend.frames["microphone"] == [FRAME] * 5
    assert backend.frames["system"] == [FRAME] * 5
    snap = agent.diagnostics.snapshot()
    assert snap["tracks"]["microphone"]["frames"] == 5 and snap["session"] == "stopped"

    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_capture_failure_reports_error_and_releases_session(backend):
    agent = make_agent(backend, factory=lambda track: FakeCapture(track, fail=track == "system"))
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    await backend.command(
        type="capture.start", capture_session_id="c2", tracks=["microphone", "system"]
    )
    error = await backend.next_event("capture.error")
    assert error["capture_session_id"] == "c2" and error["code"] == "CAPTURE_FAILED"
    assert agent.active is None
    # A later session can start cleanly.
    agent.capture_factory = lambda track: FakeCapture(track, frames=1)
    await backend.command(type="capture.start", capture_session_id="c3", tracks=["microphone"])
    await backend.next_event("capture.ready")
    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_agent_reconnects_after_losing_the_control_channel(backend):
    agent = make_agent(backend)
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    backend.connected.clear()
    await backend.control.close()
    await asyncio.wait_for(backend.connected.wait(), 10)
    assert backend.connections == 2
    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_wrong_token_is_rejected(backend):
    cfg = AgentConfig(backend.url, agent_id="agent-1", token="wrong")
    agent = RemoteAgent(cfg, capabilities=available)
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(0.5)
    assert backend.connections == 0
    assert agent.diagnostics.connection in ("reconnecting", "connecting")
    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_remote_start_needs_local_consent(backend):
    asked: list[list[str]] = []

    async def deny(tracks):
        asked.append(tracks)
        return False

    agent = make_agent(backend, consent="ask", confirm=deny)
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    await backend.command(type="capture.start", capture_session_id="c1", tracks=["microphone"])
    error = await backend.next_event("capture.error")
    assert error["code"] == "CONSENT_DENIED" and asked == [["microphone"]]
    assert agent.active is None and not backend.frames

    async def allow(tracks):
        return True

    agent.confirm = allow
    await backend.command(type="capture.start", capture_session_id="c2", tracks=["microphone"])
    await backend.next_event("capture.ready")
    await backend.command(type="capture.stop", capture_session_id="c2")
    await backend.next_event("capture.stopped")
    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_headless_agent_refuses_remote_recording_unless_opted_in(backend):
    agent = make_agent(backend, consent="ask")  # no way to ask a person
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    await backend.command(type="capture.start", capture_session_id="c1", tracks=["system"])
    error = await backend.next_event("capture.error")
    assert error["code"] == "CONSENT_UNAVAILABLE" and agent.active is None
    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_consent_dialog_failure_is_a_refusal(backend):
    async def broken(tracks):
        raise RuntimeError("no display")

    agent = make_agent(backend, consent="ask", confirm=broken)
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    await backend.command(type="capture.start", capture_session_id="c1", tracks=["system"])
    assert (await backend.next_event("capture.error"))["code"] == "CONSENT_DENIED"
    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_a_dead_track_channel_is_reported_and_stops_the_capture(backend):
    backend.close_pcm_after = 2
    agent = make_agent(backend, factory=lambda track: FakeCapture(track, frames=400))
    task = asyncio.create_task(agent.run())
    await asyncio.wait_for(backend.connected.wait(), 5)
    await backend.command(type="capture.start", capture_session_id="c1", tracks=["microphone"])
    await backend.next_event("capture.ready")

    error = await backend.next_event("capture.error", timeout=10)
    assert error["code"] == "TRACK_SEND_FAILED" and error["capture_session_id"] == "c1"
    assert agent.active is None  # not left recording into a full queue

    agent.shutdown()
    await asyncio.wait_for(task, 5)


async def test_stop_never_hangs_on_a_full_queue():
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=3)
    for _ in range(3):
        queue.put_nowait(FRAME)  # a stuck sender: nobody consumes
    await asyncio.wait_for(RemoteAgent._close_queue(queue), 6)
    assert queue.full() and queue.get_nowait() is not None
    items = [queue.get_nowait(), queue.get_nowait()]
    assert items[-1] is None  # the end marker got in, older frames were dropped
