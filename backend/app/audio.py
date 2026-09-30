"""Meeting audio WebSocket: browser microphone capture and lifecycle events (ADR 0004, 0008, 0010).

Protocol on `WS /ws/meetings/{meeting_id}/audio` (JSON text commands, binary PCM frames):

  client -> {"type": "start"}                                      new session
  client -> {"type": "start", "resume": true, "session_id": ..., "next_sequence": n}
  server -> {"type": "audio.ready", "session_id", "resumed", "next_sequence", "format", ...}
  client -> <binary pcm_s16le mono 16 kHz>                         microphone track
  server -> {"type": "audio.received", "sequence", "track", "track_sequence", "tracks"}
  client -> {"type": "stop"}
  server -> {"type": "audio.stopped", "tracks"} then {"type": "transcript.queued", "job_id"}
  server -> {"type": "audio.error", "code"}                        protocol errors

The WebSocket never waits for ASR: stop persists the tracks, commits a TranscriptionJob and
publishes its id (ADR 0008). A disconnect leaves the session recoverable. Audio and
transcripts are never logged.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.audio_sessions import AudioSession, AudioSessionError, AudioSessionManager
from app.config import get_settings
from app.media_import import imports_in_progress
from app.models import Meeting, utcnow
from app.transcription_jobs import active_job, publish, queue_meeting_transcription

logger = logging.getLogger("advera.audio")

router = APIRouter()

PCM_FORMAT = {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}


async def send_event(websocket: WebSocket, event: dict[str, Any]) -> bool:
    """Send one event; a send after close is an expected disconnect (close-safety record)."""
    try:
        await websocket.send_json(event)
        return True
    except (RuntimeError, WebSocketDisconnect):
        logger.info("audio event %s skipped: socket closed", event.get("type"))
        return False


class AudioConnection:
    def __init__(self, websocket: WebSocket, meeting_id: str) -> None:
        self.websocket = websocket
        self.meeting_id = meeting_id
        self.app = websocket.app
        self.manager: AudioSessionManager = self.app.state.audio_sessions
        self.session: AudioSession | None = None

    async def forward(self, event: dict[str, Any]) -> None:
        """Relay events from other sources of this session (the native agent, ADR 0010)."""
        await send_event(self.websocket, event)

    def attach(self, session: AudioSession) -> None:
        self.session = session
        session.listeners.add(self.forward)

    async def error(self, code: str) -> None:
        await send_event(self.websocket, {"type": "audio.error", "code": code})

    async def handle_start(self, command: dict[str, Any]) -> None:
        async with self.app.state.sessionmaker() as db:
            meeting = await db.get(Meeting, self.meeting_id)
            if meeting is None:
                await self.error("MEETING_NOT_FOUND")
                return
            if command.get("resume"):
                try:
                    session, missing = await self.manager.resume(
                        self.meeting_id,
                        str(command.get("session_id") or ""),
                        int(command.get("next_sequence") or 0),
                    )
                except (AudioSessionError, ValueError, TypeError) as error:
                    code = error.code if isinstance(error, AudioSessionError) else "INVALID_COMMAND"
                    await self.error(code)
                    return
                self.attach(session)
                if missing:
                    logger.warning(
                        "meeting %s resumed with %s missing frames", self.meeting_id, missing
                    )
                await self.ready(resumed=True, missing_frames=missing)
                return
            if (
                meeting.status in ("processing",)
                or self.meeting_id in imports_in_progress
                or self.manager.metrics_status(self.meeting_id) == "recording"
                or await active_job(db, self.meeting_id)
            ):
                # A recording in progress is resumed, never restarted: a new session would
                # truncate the audio captured so far (QA/Security review).
                await self.error("MEETING_BUSY")
                return
            if self.app.state.storage.non_empty_tracks(self.meeting_id):
                # The recorded audio is kept as it is; another recording is another meeting.
                await self.error("MEETING_ALREADY_RECORDED")
                return
            self.attach(await self.manager.start(self.meeting_id))
            meeting.status = "recording"
            meeting.started_at = utcnow()
            meeting.ended_at = None
            await db.commit()
        logger.info(
            "meeting %s capture session %s started", self.meeting_id, self.session.session_id
        )
        await self.ready(resumed=False, missing_frames=0)

    async def ready(self, resumed: bool, missing_frames: int) -> None:
        assert self.session is not None
        await send_event(
            self.websocket,
            {
                "type": "audio.ready",
                "session_id": self.session.session_id,
                "resumed": resumed,
                "next_sequence": self.session.sequence,
                "missing_frames": missing_frames,
                "format": PCM_FORMAT,
                "tracks": self.session.metrics()["tracks"],
            },
        )

    async def handle_frame(self, pcm: bytes) -> None:
        if self.session is None:
            await self.error("FRAME_BEFORE_START")
            return
        if self.session.capture_session_id:
            # The native agent owns the tracks of this session; never mix browser audio in.
            await self.error("AGENT_CAPTURE_ACTIVE")
            return
        try:
            cursor = self.manager.append(self.session, "microphone", pcm)
        except AudioSessionError as error:
            await self.error(error.code)
            return
        await send_event(
            self.websocket,
            {
                "type": "audio.received",
                "sequence": self.session.sequence,
                "track": "microphone",
                "track_sequence": cursor.frames,
                "bytes": cursor.bytes,
                "tracks": self.session.metrics()["tracks"],
            },
        )

    async def handle_stop(self) -> bool:
        if self.session is None:
            await self.error("NOT_RECORDING")
            return False
        if self.session.capture_session_id:
            await self.app.state.capture_agents.stop(self.session.capture_session_id)
        metrics = await self.manager.stop(self.session)
        await send_event(self.websocket, {"type": "audio.stopped", "tracks": metrics["tracks"]})
        storage = self.app.state.storage
        settings = get_settings()
        async with self.app.state.sessionmaker() as db:
            meeting: Meeting | None = await db.get(Meeting, self.meeting_id)
            if meeting is None:
                return True
            meeting.ended_at = utcnow()
            if not storage.non_empty_tracks(self.meeting_id):
                meeting.status = "scheduled"
                await db.commit()
                await send_event(self.websocket, {"type": "transcript.failed", "code": "NO_AUDIO"})
                return True
            job = await queue_meeting_transcription(db, storage, settings, meeting)
        if job.status == "queued":
            await publish(self.app.state.transcription_queue, job.id)
        logger.info("meeting %s capture stopped; transcription job %s", self.meeting_id, job.id)
        await send_event(
            self.websocket, {"type": "transcript.queued", "job_id": job.id, "status": job.status}
        )
        return True

    async def run(self) -> None:
        try:
            while True:
                message = await self.websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await self.handle_frame(message["bytes"])
                    continue
                try:
                    command = json.loads(message.get("text") or "")
                    kind = command.get("type") if isinstance(command, dict) else None
                except ValueError:
                    kind = None
                if kind == "start":
                    await self.handle_start(command)
                elif kind == "stop":
                    if await self.handle_stop():
                        self.session = None
                        await self.websocket.close()
                        return
                elif kind == "ping":
                    await send_event(self.websocket, {"type": "pong"})
                else:
                    await self.error("INVALID_COMMAND")
        except WebSocketDisconnect:
            pass
        finally:
            if self.session is not None:
                self.session.listeners.discard(self.forward)
            if self.session is not None and self.session.status == "recording":
                # Disconnect without stop: keep the session recoverable (never claim ready).
                self.manager.detach(self.session)
                logger.info("meeting %s capture detached; session recoverable", self.meeting_id)


@router.websocket("/ws/meetings/{meeting_id}/audio")
async def meeting_audio(websocket: WebSocket, meeting_id: str) -> None:
    await websocket.accept()
    await AudioConnection(websocket, meeting_id).run()
