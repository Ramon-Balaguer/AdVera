"""Local filesystem storage with a flat per-meeting layout (spec §5).

<AUDIO_STORAGE_PATH>/<meeting-id>/original.pcm      microphone track
<AUDIO_STORAGE_PATH>/<meeting-id>/system.pcm        system track / imported media
<AUDIO_STORAGE_PATH>/<meeting-id>/transcript.json   definitive transcript

Tracks are PCM16 mono 16 kHz at rest (ADR 0004); WAV is only synthesized to serve HTTP.
"""

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

Track = Literal["microphone", "system"]
TRACK_FILES: dict[Track, str] = {"microphone": "original.pcm", "system": "system.pcm"}
TRACK_ORDER: tuple[Track, ...] = ("microphone", "system")

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
TRANSCRIPT_FILE = "transcript.json"


class MeetingStorage:
    """StorageProvider for the local filesystem."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def meeting_dir(self, meeting_id: str) -> Path:
        # Cleanup and writes are scoped to the UUID-derived directory only.
        return self.root / str(uuid.UUID(meeting_id))

    def track_path(self, meeting_id: str, track: Track) -> Path:
        return self.meeting_dir(meeting_id) / TRACK_FILES[track]

    def transcript_path(self, meeting_id: str) -> Path:
        return self.meeting_dir(meeting_id) / TRANSCRIPT_FILE

    def non_empty_tracks(self, meeting_id: str) -> list[Track]:
        tracks: list[Track] = []
        for track in TRACK_ORDER:
            path = self.track_path(meeting_id, track)
            if path.is_file() and path.stat().st_size >= SAMPLE_WIDTH:
                tracks.append(track)
        return tracks

    def track_duration(self, meeting_id: str, track: Track) -> float:
        size = self.track_path(meeting_id, track).stat().st_size
        return size / (SAMPLE_RATE * SAMPLE_WIDTH)

    def tracks_sha256(self, meeting_id: str, tracks: list[Track]) -> str:
        """Hash of the selected source tracks; identifies the job input."""
        digest = hashlib.sha256()
        for track in tracks:
            digest.update(f"{track}:".encode())
            with self.track_path(meeting_id, track).open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b";")
        return digest.hexdigest()

    def write_transcript(self, meeting_id: str, document: dict[str, Any]) -> None:
        """Atomically replace transcript.json (write to a temp file, then os.replace)."""
        directory = self.meeting_dir(meeting_id)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=directory, prefix=".transcript-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.transcript_path(meeting_id))
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def read_transcript(self, meeting_id: str) -> dict[str, Any] | None:
        path = self.transcript_path(meeting_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_meeting(self, meeting_id: str) -> None:
        directory = self.meeting_dir(meeting_id)
        if directory.exists():
            shutil.rmtree(directory)
