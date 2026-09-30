"""Outbound connection to the AdVera backend (ADR 0010, outbound-capture-agent-websocket.md).

The agent never listens on a local port. It keeps one control WebSocket open, reconnecting
with bounded backoff. On `capture.start` it starts the requested native tracks, opens one
PCM WebSocket per track with a JSON handshake (per-track-pcm-websockets.md), and only then
answers `capture.ready`. Each track has a bounded queue that drops the oldest frame, so a
slow network never blocks capture or the control channel.
"""

import asyncio
import contextlib
import json
import logging
import platform
import time
from collections.abc import Callable

import websockets

from agent import __version__
from agent.capture import TrackCapture, create_capture, probe, rms
from agent.config import AgentConfig
from agent.diagnostics import Diagnostics

logger = logging.getLogger("advera.agent.remote")

PCM_FORMAT = {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}
TRACK_QUEUE_FRAMES = 128
LEVEL_INTERVAL_SECONDS = 0.1
MAX_BACKOFF_SECONDS = 30

CaptureFactory = Callable[[str], TrackCapture]
Notifier = Callable[[str], None]


class CaptureStartError(Exception):
    """A capture start failure with a controlled, client-safe code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ActiveCapture:
    def __init__(self, capture_session_id: str, tracks: list[str]) -> None:
        self.capture_session_id = capture_session_id
        self.tracks = tracks
        self.captures: dict[str, TrackCapture] = {}
        self.queues: dict[str, asyncio.Queue[bytes | None]] = {}
        self.senders: list[asyncio.Task] = []
        self.sockets: list = []
        self.last_level: dict[str, float] = {}


class RemoteAgent:
    def __init__(
        self,
        config: AgentConfig,
        *,
        capture_factory: CaptureFactory = create_capture,
        capabilities: Callable[[], dict] = probe,
        diagnostics: Diagnostics | None = None,
        notify: Notifier | None = None,
    ) -> None:
        self.config = config
        self.capture_factory = capture_factory
        self.capabilities = capabilities
        self.diagnostics = diagnostics or Diagnostics()
        self.notify = notify or (lambda message: None)
        self.active: ActiveCapture | None = None
        self._control = None
        self._stop = asyncio.Event()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.token}"} if self.config.token else {}

    @property
    def control_url(self) -> str:
        return f"{self.config.websocket_base()}/ws/capture-agents/{self.config.agent_id}"

    def track_url(self, capture_session_id: str, track: str) -> str:
        return f"{self.control_url}/sessions/{capture_session_id}/tracks/{track}/pcm"

    async def run(self) -> None:
        """Connect and serve until `shutdown()`; reconnect with bounded backoff."""
        backoff = 1.0
        while not self._stop.is_set():
            self.diagnostics.set(connection="connecting")
            try:
                async with websockets.connect(
                    self.control_url, additional_headers=self._headers(), max_size=2**20
                ) as control:
                    self._control = control
                    await self._handshake(control)
                    backoff = 1.0
                    self.diagnostics.set(connection="connected", last_error=None)
                    logger.info("connected to backend as agent %s", self.config.agent_id)
                    await self._serve(control)
            except (TimeoutError, OSError, websockets.WebSocketException) as error:
                self.diagnostics.set(connection="reconnecting", last_error=type(error).__name__)
                logger.warning("backend connection lost: %s", type(error).__name__)
            finally:
                self._control = None
                await self._abort_capture()
            if self._stop.is_set():
                break
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            backoff = min(MAX_BACKOFF_SECONDS, backoff * 2)
        self.diagnostics.set(connection="disconnected")

    def shutdown(self) -> None:
        self._stop.set()
        if self._control is not None:
            asyncio.ensure_future(self._control.close())

    async def _handshake(self, control) -> None:
        await control.send(
            json.dumps(
                {
                    "type": "agent.hello",
                    "agent_version": __version__,
                    "platform": platform.system().lower(),
                    "capabilities": self.capabilities(),
                    "pcm_transports": ["per-track"],
                }
            )
        )
        welcome = json.loads(await asyncio.wait_for(control.recv(), timeout=10))
        if welcome.get("type") != "agent.welcome" or welcome.get("pcm_transport") != "per-track":
            raise websockets.WebSocketException("unsupported backend protocol")

    async def _serve(self, control) -> None:
        async for raw in control:
            if self._stop.is_set():
                break
            try:
                command = json.loads(raw)
            except (TypeError, ValueError):
                continue
            kind = command.get("type")
            if kind == "capture.start":
                await self._start(control, command)
            elif kind == "capture.stop":
                await self._finish(control, command.get("capture_session_id"))

    async def _start(self, control, command: dict) -> None:
        capture_session_id = str(command.get("capture_session_id") or "")
        tracks = [track for track in command.get("tracks", []) if track in ("microphone", "system")]
        if self.active is not None or not tracks:
            await self._send_error(control, capture_session_id, "CAPTURE_ALREADY_ACTIVE")
            return
        self.diagnostics.reset_session(capture_session_id, tracks)
        active = ActiveCapture(capture_session_id, tracks)
        self.active = active
        loop = asyncio.get_running_loop()
        try:
            for track in tracks:
                queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=TRACK_QUEUE_FRAMES)
                active.queues[track] = queue
                socket = await websockets.connect(
                    self.track_url(capture_session_id, track),
                    additional_headers=self._headers(),
                    max_size=2**20,
                )
                active.sockets.append(socket)
                await socket.send(
                    json.dumps({"type": "track.hello", "track": track, "format": PCM_FORMAT})
                )
                ready = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                if ready.get("type") != "track.ready":
                    raise CaptureStartError("TRACK_HANDSHAKE_FAILED")
                active.senders.append(asyncio.create_task(self._send_track(track, queue, socket)))
            for track in tracks:
                capture = self.capture_factory(track)
                capture.start(self._sink(loop, active, track, control))
                active.captures[track] = capture
        except Exception as error:
            code = error.code if isinstance(error, CaptureStartError) else "CAPTURE_FAILED"
            logger.warning("capture start failed: %s", type(error).__name__)
            await self._abort_capture()
            await self._send_error(control, capture_session_id, code)
            return
        await control.send(
            json.dumps(
                {
                    "type": "capture.ready",
                    "capture_session_id": capture_session_id,
                    "tracks": tracks,
                }
            )
        )
        self.diagnostics.set(session="recording")
        with contextlib.suppress(Exception):
            self.notify(
                "AdVera está grabando"
            )  # generic; no ids or content (agent-recording-notification)

    def _sink(self, loop, active: ActiveCapture, track: str, control) -> Callable[[bytes], None]:
        """Thread-safe frame sink: enqueue on the event loop, dropping the oldest on overflow."""

        def enqueue(pcm: bytes) -> None:
            queue = active.queues[track]
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                self.diagnostics.dropped(track)
            queue.put_nowait(pcm)
            now = time.monotonic()
            if now - active.last_level.get(track, 0) >= LEVEL_INTERVAL_SECONDS:
                active.last_level[track] = now
                asyncio.ensure_future(self._send_level(control, active, track, rms(pcm)))

        def sink(pcm: bytes) -> None:
            if pcm:
                loop.call_soon_threadsafe(enqueue, bytes(pcm))

        return sink

    async def _send_level(self, control, active: ActiveCapture, track: str, level: float) -> None:
        with contextlib.suppress(Exception):
            await control.send(
                json.dumps(
                    {
                        "type": "levels",
                        "capture_session_id": active.capture_session_id,
                        "track": track,
                        "level": round(level, 4),
                    }
                )
            )

    async def _send_track(self, track: str, queue: asyncio.Queue, socket) -> None:
        while True:
            pcm = await queue.get()
            if pcm is None:
                break
            await socket.send(pcm)
            self.diagnostics.sent(track, len(pcm))

    async def _finish(self, control, capture_session_id) -> None:
        active = self.active
        if active is None or active.capture_session_id != capture_session_id:
            return
        for capture in active.captures.values():
            with contextlib.suppress(Exception):
                capture.stop()
        # Drain what was captured, then close each track channel.
        for queue in active.queues.values():
            await queue.put(None)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.gather(*active.senders), timeout=10)
        for socket in active.sockets:
            with contextlib.suppress(Exception):
                await socket.close()
        self.active = None
        self.diagnostics.set(session="stopped")
        with contextlib.suppress(Exception):
            await control.send(
                json.dumps({"type": "capture.stopped", "capture_session_id": capture_session_id})
            )

    async def _abort_capture(self) -> None:
        active, self.active = self.active, None
        if active is None:
            return
        for capture in active.captures.values():
            with contextlib.suppress(Exception):
                capture.stop()
        for task in active.senders:
            task.cancel()
        for socket in active.sockets:
            with contextlib.suppress(Exception):
                await socket.close()
        self.diagnostics.set(session="idle")

    async def _send_error(self, control, capture_session_id: str, code: str) -> None:
        self.diagnostics.set(last_error=code, session="idle")
        with contextlib.suppress(Exception):
            await control.send(
                json.dumps(
                    {
                        "type": "capture.error",
                        "capture_session_id": capture_session_id,
                        "code": code,
                    }
                )
            )
