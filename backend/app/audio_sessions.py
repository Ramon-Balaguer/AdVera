"""Backend-owned audio sessions (ADR 0004, 0005, 0010; audio-session-reconnection.md).

One active capture session per meeting. PCM from any source (browser microphone over the
meeting WebSocket, or the native Capture Agent per-track sockets) is appended to that
meeting's track files through this module, so persistence has a single owner. Each track
keeps its own frame counter and byte cursor; a global sequence orders events.

The durable manifest `audio_session.json` holds identifiers, counters and status only,
never audio. It is replaced atomically.
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.storage import SAMPLE_RATE, SAMPLE_WIDTH, TRACK_FILES, TRACK_ORDER, MeetingStorage, Track

MANIFEST_FILE = "audio_session.json"
MAX_FRAME_BYTES = 256 * 1024
MANIFEST_INTERVAL_SECONDS = 1.0

SessionStatus = Literal["recording", "stopped"]


class AudioSessionError(Exception):
    """A protocol error with a stable, client-safe code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class TrackCursor:
    frames: int = 0
    bytes: int = 0

    @property
    def duration(self) -> float:
        return self.bytes / (SAMPLE_RATE * SAMPLE_WIDTH)

    def as_dict(self) -> dict[str, Any]:
        return {"frames": self.frames, "bytes": self.bytes, "duration": round(self.duration, 3)}


@dataclass
class AudioSession:
    meeting_id: str
    session_id: str
    status: SessionStatus = "recording"
    sequence: int = 0
    started_at: float = field(default_factory=time.time)
    tracks: dict[Track, TrackCursor] = field(default_factory=dict)
    capture_session_id: str | None = None
    # Meeting WebSocket connections receiving lifecycle and metric events (ADR 0010).
    listeners: set[Callable[[dict[str, Any]], Awaitable[None]]] = field(
        default_factory=set, repr=False
    )
    _files: dict[Track, Any] = field(default_factory=dict, repr=False)
    _last_manifest: float = 0.0

    def cursor(self, track: Track) -> TrackCursor:
        return self.tracks.setdefault(track, TrackCursor())

    def metrics(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "sequence": self.sequence,
            "next_sequence": self.sequence,
            "capture_session_id": self.capture_session_id,
            "tracks": {
                track: self.tracks[track].as_dict() for track in TRACK_ORDER if track in self.tracks
            },
        }


class AudioSessionManager:
    def __init__(self, storage: MeetingStorage, max_track_bytes: int | None = None) -> None:
        self.storage = storage
        # A live track never grows past this (ADR 0015 size and duration limits).
        self.max_track_bytes = max_track_bytes
        self._sessions: dict[str, AudioSession] = {}
        self._capture_index: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ----- manifest -------------------------------------------------------------------
    def manifest_path(self, meeting_id: str) -> Path:
        return self.storage.meeting_dir(meeting_id) / MANIFEST_FILE

    def read_manifest(self, meeting_id: str) -> dict[str, Any] | None:
        path = self.manifest_path(meeting_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_manifest(self, session: AudioSession) -> None:
        directory = self.storage.meeting_dir(session.meeting_id)
        directory.mkdir(parents=True, exist_ok=True)
        payload = session.metrics() | {
            "meeting_id": session.meeting_id,
            "started_at": session.started_at,
        }
        descriptor, temp_name = tempfile.mkstemp(
            dir=directory, prefix=".audio-session-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            os.replace(temp_name, self.manifest_path(session.meeting_id))
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
        session._last_manifest = time.monotonic()

    # ----- lifecycle ------------------------------------------------------------------
    def active(self, meeting_id: str) -> AudioSession | None:
        session = self._sessions.get(meeting_id)
        return session if session and session.status == "recording" else None

    def metrics_status(self, meeting_id: str) -> str | None:
        """`recording`/`stopped` from memory or the durable manifest; None when never recorded."""
        session = self._sessions.get(meeting_id)
        if session:
            return session.status
        manifest = self.read_manifest(meeting_id)
        return manifest.get("status") if manifest else None

    def has_recorded_audio(self, meeting_id: str) -> bool:
        """True when a capture (not an import) stored audio: its session shows non-empty tracks.
        An empty manifest (a stop with no audio) or none at all means nothing was recorded."""
        session = self._sessions.get(meeting_id)
        tracks = (session.metrics() if session else self.read_manifest(meeting_id) or {}).get(
            "tracks", {}
        )
        return any(track.get("bytes", 0) > 0 for track in tracks.values())

    def metrics(self, meeting_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(meeting_id)
        if session:
            return session.metrics()
        return self.read_manifest(meeting_id)

    async def start(self, meeting_id: str) -> AudioSession:
        """Start a fresh session. The checks and the start share one lock, so two `start`
        commands (two tabs, a double click) cannot both pass: a recording in progress is
        resumed, never replaced, and audio already stored is never truncated."""
        async with self._lock:
            if self.metrics_status(meeting_id) == "recording":
                raise AudioSessionError("MEETING_BUSY")
            if self.storage.non_empty_tracks(meeting_id):
                raise AudioSessionError("MEETING_ALREADY_RECORDED")
            previous = self._sessions.pop(meeting_id, None)
            if previous:
                self._close_files(previous)
                self._unindex(previous)
            directory = self.storage.meeting_dir(meeting_id)
            directory.mkdir(parents=True, exist_ok=True)
            for name in TRACK_FILES.values():
                (directory / name).unlink(missing_ok=True)
            session = AudioSession(meeting_id=meeting_id, session_id=str(uuid.uuid4()))
            self._sessions[meeting_id] = session
            self._write_manifest(session)
            return session

    async def resume(
        self, meeting_id: str, session_id: str, client_next_sequence: int
    ) -> tuple[AudioSession, int]:
        """Resume without truncating. Returns the session and the number of missing frames."""
        async with self._lock:
            session = self._sessions.get(meeting_id)
            if session is None:
                manifest = self.read_manifest(meeting_id)
                if not manifest or manifest.get("status") != "recording":
                    raise AudioSessionError("SESSION_NOT_RECOVERABLE")
                session = AudioSession(
                    meeting_id=meeting_id,
                    session_id=manifest["session_id"],
                    sequence=int(manifest.get("sequence", 0)),
                    started_at=float(manifest.get("started_at", time.time())),
                    capture_session_id=manifest.get("capture_session_id"),
                )
                for track in TRACK_ORDER:
                    path = self.storage.track_path(meeting_id, track)
                    saved = manifest.get("tracks", {}).get(track)
                    if saved or path.exists():
                        size = path.stat().st_size if path.exists() else 0
                        session.tracks[track] = TrackCursor(
                            int((saved or {}).get("frames", 0)), size
                        )
                self._sessions[meeting_id] = session
            if session.session_id != session_id or session.status != "recording":
                raise AudioSessionError("SESSION_NOT_RECOVERABLE")
            if session.capture_session_id:
                # The native agent is the frame source; the frontend only listens (ADR 0010).
                return session, 0
            if client_next_sequence < session.sequence:
                # A lower client cursor would duplicate frames already stored.
                raise AudioSessionError("STALE_CURSOR")
            return session, client_next_sequence - session.sequence

    def append(self, session: AudioSession, track: Track, pcm: bytes) -> TrackCursor:
        if session.status != "recording":
            raise AudioSessionError("SESSION_NOT_ACTIVE")
        if not pcm or len(pcm) % SAMPLE_WIDTH or len(pcm) > MAX_FRAME_BYTES:
            raise AudioSessionError("INVALID_FRAME")
        if (
            self.max_track_bytes is not None
            and session.cursor(track).bytes + len(pcm) > self.max_track_bytes
        ):
            raise AudioSessionError("CAPTURE_LIMIT_REACHED")
        handle = session._files.get(track)
        if handle is None:
            handle = self.storage.track_path(session.meeting_id, track).open("ab")
            session._files[track] = handle
        handle.write(pcm)
        handle.flush()
        cursor = session.cursor(track)
        cursor.frames += 1
        cursor.bytes += len(pcm)
        session.sequence += 1
        if time.monotonic() - session._last_manifest >= MANIFEST_INTERVAL_SECONDS:
            self._write_manifest(session)
        return cursor

    def detach(self, session: AudioSession) -> None:
        """Connection lost: flush and keep the session recoverable."""
        self._close_files(session)
        if session.status == "recording":
            self._write_manifest(session)

    async def stop(self, session: AudioSession) -> dict[str, Any]:
        async with self._lock:
            self._close_files(session)
            session.status = "stopped"
            self._write_manifest(session)
            self._unindex(session)
            return session.metrics()

    def forget(self, meeting_id: str) -> None:
        session = self._sessions.pop(meeting_id, None)
        if session:
            self._close_files(session)
            self._unindex(session)

    async def notify(self, session: AudioSession, event: dict[str, Any]) -> None:
        for listener in list(session.listeners):
            try:
                await listener(event)
            except Exception:
                session.listeners.discard(listener)

    # ----- native capture association (ADR 0010) --------------------------------------
    def associate_capture(self, session: AudioSession, capture_session_id: str) -> None:
        session.capture_session_id = capture_session_id
        self._capture_index[capture_session_id] = session.meeting_id
        self._write_manifest(session)

    def dissociate_capture(self, session: AudioSession) -> None:
        """Release the native agent's claim (a capture that never started)."""
        self._unindex(session)
        session.capture_session_id = None
        self._write_manifest(session)

    def session_for_capture(self, capture_session_id: str) -> AudioSession | None:
        meeting_id = self._capture_index.get(capture_session_id)
        return self.active(meeting_id) if meeting_id else None

    def _unindex(self, session: AudioSession) -> None:
        if session.capture_session_id:
            self._capture_index.pop(session.capture_session_id, None)

    @staticmethod
    def _close_files(session: AudioSession) -> None:
        for handle in session._files.values():
            handle.close()
        session._files.clear()
