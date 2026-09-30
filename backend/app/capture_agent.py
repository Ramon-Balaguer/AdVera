"""Native Capture Agent: outbound control channel, per-track PCM ingestion and frontend API.

ADR 0010: the backend owns native PCM ingestion. The agent connects outbound
(outbound-capture-agent-websocket.md) and never listens on a local port.

Control   WS /ws/capture-agents/{agent_id}
  agent   -> {"type": "agent.hello", "agent_version", "platform", "capabilities", "pcm_transports"}
  backend -> {"type": "agent.welcome", "pcm_transport": "per-track"}
  backend -> {"type": "capture.start", "capture_session_id", "tracks"}
  agent   -> {"type": "capture.ready", "capture_session_id", "tracks"}
          or {"type": "capture.error", "capture_session_id", "code"}
  backend -> {"type": "capture.stop", "capture_session_id"}
  agent   -> {"type": "capture.stopped", "capture_session_id"}
  agent   -> {"type": "levels", "capture_session_id", "track", "level"}
  agent   -> {"type": "capabilities", "capabilities"}

PCM       WS /ws/capture-agents/{agent_id}/sessions/{capture_session_id}/tracks/{track}/pcm
  agent   -> {"type": "track.hello", "format"}; backend -> {"type": "track.ready"}; then binary PCM.

Levels    WS /ws/capture-agent/{capture_session_id}/{track}/levels     (frontend, RMS only)

The session is reserved and associated with the meeting's active audio session before
`capture.start` is sent, so track handshakes can pass before `capture.ready`
(agent-pcm-e2e-delivery-fix.md). Bounded per-track queues drop the oldest frame on overflow
so audio never blocks the control channel. PCM and credentials are never logged.
"""

import asyncio
import contextlib
import hmac
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.audio_sessions import AudioSessionError, AudioSessionManager
from app.config import get_settings
from app.storage import TRACK_ORDER

logger = logging.getLogger("advera.capture_agent")

router = APIRouter()

PCM_FORMAT = {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}
TRACK_QUEUE_FRAMES = 256
START_TIMEOUT_SECONDS = 10
STOP_TIMEOUT_SECONDS = 5


@dataclass
class CaptureSession:
    capture_session_id: str
    meeting_id: str
    tracks: list[str]
    state: str = "starting"  # starting | recording | stopping | stopped | failed
    ready: asyncio.Future | None = None
    stopped: asyncio.Future | None = None
    dropped_frames: dict[str, int] = field(default_factory=dict)
    open_tracks: set[str] = field(default_factory=set)
    level_listeners: dict[str, set[WebSocket]] = field(default_factory=dict)


@dataclass
class AgentConnection:
    agent_id: str
    websocket: WebSocket
    agent_version: str = ""
    platform: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    session: CaptureSession | None = None

    async def send(self, event: dict[str, Any]) -> None:
        await self.websocket.send_json(event)


class CaptureAgentRegistry:
    """Process-local registry. One active agent is supported (single-user, ADR 0015)."""

    def __init__(self, audio_sessions: AudioSessionManager) -> None:
        self.audio_sessions = audio_sessions
        self.agents: dict[str, AgentConnection] = {}
        self.sessions: dict[str, CaptureSession] = {}

    def current_agent(self) -> AgentConnection | None:
        return next(iter(self.agents.values()), None)

    def current_session(self) -> CaptureSession | None:
        agent = self.current_agent()
        return agent.session if agent else None

    async def start(self, meeting_id: str, tracks: list[str]) -> CaptureSession:
        agent = self.current_agent()
        if agent is None:
            raise CaptureError("AGENT_UNAVAILABLE", 503)
        if agent.session and agent.session.state in ("starting", "recording", "stopping"):
            raise CaptureError("CAPTURE_ALREADY_ACTIVE", 409)
        unavailable = [
            track
            for track in tracks
            if agent.capabilities.get(track, {}).get("state") != "available"
        ]
        if unavailable:
            raise CaptureError("CAPTURE_ADAPTER_UNAVAILABLE", 503, {"tracks": unavailable})
        audio_session = self.audio_sessions.active(meeting_id)
        if audio_session is None:
            raise CaptureError("MEETING_NOT_RECORDING", 409)

        loop = asyncio.get_running_loop()
        session = CaptureSession(
            capture_session_id=str(uuid.uuid4()),
            meeting_id=meeting_id,
            tracks=tracks,
            ready=loop.create_future(),
            stopped=loop.create_future(),
        )
        # Reserve and associate before capture.start so track handshakes can pass.
        agent.session = session
        self.sessions[session.capture_session_id] = session
        self.audio_sessions.associate_capture(audio_session, session.capture_session_id)
        try:
            await agent.send(
                {
                    "type": "capture.start",
                    "capture_session_id": session.capture_session_id,
                    "tracks": tracks,
                    "format": PCM_FORMAT,
                }
            )
            code = await asyncio.wait_for(session.ready, START_TIMEOUT_SECONDS)
        except TimeoutError:
            code = "CAPTURE_START_TIMEOUT"
        except Exception:
            code = "AGENT_UNAVAILABLE"
        if code:
            self._clear(session, "failed")
            raise CaptureError(code, 502 if code != "CAPTURE_ADAPTER_UNAVAILABLE" else 503)
        session.state = "recording"
        logger.info("capture session %s recording tracks %s", session.capture_session_id, tracks)
        return session

    async def stop(self, capture_session_id: str) -> None:
        session = self.sessions.get(capture_session_id)
        agent = self.current_agent()
        if session is None or session.state in ("stopped", "failed"):
            return
        session.state = "stopping"
        if agent and agent.session is session:
            with contextlib.suppress(Exception):
                await agent.send({"type": "capture.stop", "capture_session_id": capture_session_id})
                await asyncio.wait_for(asyncio.shield(session.stopped), STOP_TIMEOUT_SECONDS)
        # Give open track channels a moment to deliver their final frames.
        for _ in range(STOP_TIMEOUT_SECONDS * 10):
            if not session.open_tracks:
                break
            await asyncio.sleep(0.1)
        self._clear(session, "stopped")

    def _clear(self, session: CaptureSession, state: str) -> None:
        session.state = state
        for future in (session.ready, session.stopped):
            if future and not future.done():
                future.set_result("CAPTURE_ABORTED" if future is session.ready else None)
        agent = self.current_agent()
        if agent and agent.session is session:
            agent.session = None
        self.sessions.pop(session.capture_session_id, None)

    def agent_lost(self, agent: AgentConnection) -> None:
        """A lost control channel fails the active capture; stored audio is kept."""
        if self.agents.get(agent.agent_id) is agent:
            del self.agents[agent.agent_id]
        if agent.session:
            logger.warning("capture session %s lost its agent", agent.session.capture_session_id)
            self._clear(agent.session, "failed")


class CaptureError(Exception):
    def __init__(self, code: str, status_code: int, extra: dict | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.extra = extra or {}


def _authorized(websocket: WebSocket) -> bool:
    settings = get_settings()
    if settings.api_token:
        return True  # AccessTokenMiddleware already verified this handshake (ADR 0019)
    expected = settings.capture_agent_token
    if not expected:
        return True
    header = websocket.headers.get("authorization", "")
    return hmac.compare_digest(header, f"Bearer {expected}")


def registry(app) -> CaptureAgentRegistry:
    return app.state.capture_agents


# ----- agent control channel -------------------------------------------------------------
@router.websocket("/ws/capture-agents/{agent_id}")
async def agent_control(websocket: WebSocket, agent_id: str) -> None:
    if not _authorized(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    agents = registry(websocket.app)
    agent = AgentConnection(agent_id=agent_id, websocket=websocket)
    try:
        hello = await websocket.receive_json()
        if hello.get("type") != "agent.hello" or "per-track" not in hello.get("pcm_transports", []):
            await websocket.close(code=4400)
            return
        agent.agent_version = str(hello.get("agent_version", ""))[:50]
        agent.platform = str(hello.get("platform", ""))[:50]
        agent.capabilities = hello.get("capabilities") or {}
        previous = agents.agents.get(agent_id)
        if previous:
            agents.agent_lost(previous)
        agents.agents[agent_id] = agent
        await agent.send({"type": "agent.welcome", "pcm_transport": "per-track"})
        logger.info("capture agent %s connected (%s)", agent_id, agent.platform)
        while True:
            event = await websocket.receive_json()
            await _handle_agent_event(agents, agent, event)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        agents.agent_lost(agent)
        logger.info("capture agent %s disconnected", agent_id)


async def _handle_agent_event(
    agents: CaptureAgentRegistry, agent: AgentConnection, event: dict[str, Any]
) -> None:
    kind = event.get("type")
    session = agent.session
    matches = session is not None and event.get("capture_session_id") == session.capture_session_id
    if kind == "capabilities":
        agent.capabilities = event.get("capabilities") or {}
    elif kind == "capture.ready" and matches and not session.ready.done():
        session.ready.set_result(None)
    elif kind == "capture.error" and matches and not session.ready.done():
        session.ready.set_result(str(event.get("code") or "CAPTURE_FAILED")[:50])
    elif kind == "capture.error" and matches:
        logger.warning("capture session %s agent error", session.capture_session_id)
        audio_session = agents.audio_sessions.session_for_capture(session.capture_session_id)
        if audio_session is not None:
            await agents.audio_sessions.notify(
                audio_session, {"type": "capture.error", "code": str(event.get("code"))[:50]}
            )
    elif kind == "capture.stopped" and matches and not session.stopped.done():
        session.stopped.set_result(None)
    elif kind == "levels" and matches:
        track = event.get("track")
        level = float(event.get("level") or 0.0)
        for listener in list(session.level_listeners.get(track, ())):
            with contextlib.suppress(Exception):
                await listener.send_json({"type": "levels", "track": track, "level": level})


# ----- per-track PCM channel -------------------------------------------------------------
@router.websocket("/ws/capture-agents/{agent_id}/sessions/{capture_session_id}/tracks/{track}/pcm")
async def agent_track_pcm(
    websocket: WebSocket, agent_id: str, capture_session_id: str, track: str
) -> None:
    if not _authorized(websocket):
        await websocket.close(code=4401)
        return
    agents = registry(websocket.app)
    agent = agents.agents.get(agent_id)
    session = agents.sessions.get(capture_session_id)
    audio_session = agents.audio_sessions.session_for_capture(capture_session_id)
    valid = (
        agent is not None
        and session is not None
        and agent.session is session
        and track in TRACK_ORDER
        and track in session.tracks
        and audio_session is not None
    )
    if not valid:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    try:
        hello = await websocket.receive_json()
        if hello.get("type") != "track.hello" or hello.get("format") != PCM_FORMAT:
            await websocket.close(code=4400)
            return
        await websocket.send_json({"type": "track.ready", "track": track})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        return

    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=TRACK_QUEUE_FRAMES)
    session.open_tracks.add(track)
    writer = asyncio.create_task(_write_track(agents.audio_sessions, audio_session, track, queue))
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            pcm = message.get("bytes")
            if pcm is None:
                continue
            if queue.full():  # bounded: drop the oldest frame, never block (ADR 0010)
                queue.get_nowait()
                session.dropped_frames[track] = session.dropped_frames.get(track, 0) + 1
            queue.put_nowait(pcm)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await queue.join()
        writer.cancel()
        session.open_tracks.discard(track)


async def _write_track(manager: AudioSessionManager, audio_session, track, queue) -> None:
    while True:
        pcm = await queue.get()
        try:
            cursor = manager.append(audio_session, track, pcm)
            await manager.notify(
                audio_session,
                {
                    "type": "audio.received",
                    "sequence": audio_session.sequence,
                    "track": track,
                    "track_sequence": cursor.frames,
                    "bytes": cursor.bytes,
                    "tracks": audio_session.metrics()["tracks"],
                },
            )
        except AudioSessionError:
            pass  # session stopped or invalid frame: never corrupt stored audio
        finally:
            queue.task_done()


# ----- frontend API (spec §20) -------------------------------------------------------------
class CaptureSessionRequest(BaseModel):
    meeting_id: str
    tracks: list[str] = ["microphone", "system"]


def _session_payload(session: CaptureSession) -> dict[str, Any]:
    return {
        "capture_session_id": session.capture_session_id,
        "meeting_id": session.meeting_id,
        "tracks": session.tracks,
        "state": session.state,
        "dropped_frames": session.dropped_frames,
    }


@router.get("/api/capture-agent/capabilities", tags=["capture-agent"])
async def capabilities(request: Request) -> dict[str, Any]:
    agent = registry(request.app).current_agent()
    if agent is None:
        return {"available": False, "agent_id": None, "tracks": {}}
    tracks = {
        track: {"state": (agent.capabilities.get(track) or {}).get("state", "unsupported")}
        for track in TRACK_ORDER
    }
    return {
        "available": True,
        "agent_id": agent.agent_id,
        "agent_version": agent.agent_version,
        "platform": agent.platform,
        "tracks": tracks,
    }


@router.post("/api/capture-agent/sessions", status_code=201, tags=["capture-agent"])
async def start_session(body: CaptureSessionRequest, request: Request) -> dict[str, Any]:
    tracks = [track for track in TRACK_ORDER if track in body.tracks]
    if not tracks:
        raise HTTPException(status_code=422, detail="NO_TRACKS")
    try:
        session = await registry(request.app).start(body.meeting_id, tracks)
    except CaptureError as error:
        raise HTTPException(status_code=error.status_code, detail=error.code) from None
    return _session_payload(session)


@router.get("/api/capture-agent/sessions/current", tags=["capture-agent"])
async def current_session(request: Request) -> dict[str, Any]:
    session = registry(request.app).current_session()
    if session is None:
        raise HTTPException(status_code=404, detail="NO_CAPTURE_SESSION")
    return _session_payload(session)


@router.delete("/api/capture-agent/sessions/current", status_code=204, tags=["capture-agent"])
async def stop_current_session(request: Request) -> None:
    session = registry(request.app).current_session()
    if session is None:
        raise HTTPException(status_code=404, detail="NO_CAPTURE_SESSION")
    await registry(request.app).stop(session.capture_session_id)


@router.websocket("/ws/capture-agent/{capture_session_id}/{track}/levels")
async def track_levels(websocket: WebSocket, capture_session_id: str, track: str) -> None:
    session = registry(websocket.app).sessions.get(capture_session_id)
    if session is None or track not in session.tracks:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    listeners = session.level_listeners.setdefault(track, set())
    listeners.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; the client only listens
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        listeners.discard(websocket)
