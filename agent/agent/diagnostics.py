"""Process-local traffic diagnostics (tray-send-statistics.md).

Only operational counters, timestamps, technical session ids and sanitized error codes.
Never PCM, levels, transcripts or meeting content; nothing is persisted or sent anywhere.
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class TrackStats:
    frames: int = 0
    bytes: int = 0
    dropped: int = 0
    last_activity: float | None = None


@dataclass
class Diagnostics:
    connection: str = "disconnected"  # disconnected|connecting|connected|reconnecting
    session: str = "idle"  # idle|starting|recording|stopped
    capture_session_id: str | None = None
    last_error: str | None = None
    tracks: dict[str, TrackStats] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set(self, **values) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self, key, value)

    def reset_session(self, capture_session_id: str, tracks: list[str]) -> None:
        with self._lock:
            self.capture_session_id = capture_session_id
            self.session = "starting"
            self.tracks = {track: TrackStats() for track in tracks}

    def sent(self, track: str, size: int) -> None:
        with self._lock:
            stats = self.tracks.setdefault(track, TrackStats())
            stats.frames += 1
            stats.bytes += size
            stats.last_activity = time.time()

    def dropped(self, track: str) -> None:
        with self._lock:
            self.tracks.setdefault(track, TrackStats()).dropped += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connection": self.connection,
                "session": self.session,
                "capture_session_id": self.capture_session_id,
                "last_error": self.last_error,
                "tracks": {
                    name: {
                        "frames": stats.frames,
                        "bytes": stats.bytes,
                        "dropped": stats.dropped,
                        "last_activity": stats.last_activity,
                    }
                    for name, stats in self.tracks.items()
                },
            }
