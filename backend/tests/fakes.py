"""Deterministic test doubles. No models are downloaded and no real meeting content is used."""

import math
import struct
import wave
from collections.abc import Callable
from pathlib import Path

from app.asr import AsrSegment, ProviderError

SYNTHETIC_TEXT = "synthetic segment"


class FakeEngine:
    """A TranscriptionEngine returning scripted results per call."""

    def __init__(
        self,
        name: str = "fake",
        model: str = "fake-model",
        results: list[list[AsrSegment] | Exception] | None = None,
        on_call: Callable[[Path], None] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.results = list(results) if results is not None else None
        self.on_call = on_call
        self.calls: list[Path] = []

    def transcribe(self, pcm_path: Path) -> list[AsrSegment]:
        self.calls.append(pcm_path)
        if self.on_call:
            self.on_call(pcm_path)
        if self.results is None:
            return [
                AsrSegment(0.0, 0.5, f"{SYNTHETIC_TEXT} one", language="ca", speaker="SPEAKER_00"),
                AsrSegment(0.5, 1.0, f"{SYNTHETIC_TEXT} two", language="ca", speaker="SPEAKER_00"),
            ]
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


def failing(code: str = "FAKE_FAILED") -> ProviderError:
    return ProviderError(code)


class RecordingQueue:
    def __init__(self, fail: bool = False) -> None:
        self.published: list[str] = []
        self.fail = fail

    async def publish(self, job_id: str) -> None:
        if self.fail:
            raise ConnectionError("redis unavailable")
        self.published.append(job_id)


def write_sine_wav(path: Path, seconds: float = 1.0, rate: int = 16_000) -> Path:
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(int(seconds * rate))
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return path


def write_pcm(path: Path, seconds: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x01\x00" * int(16_000 * seconds))
    return path


class FakeDiarizer:
    """Assigns labels from a script (a list per call); `status` simulates degraded modes."""

    name = "fake-diarizer"

    def __init__(self, scripts: list[list[int | None]] | None = None, status: str = "completed"):
        self.scripts = list(scripts or [])
        self.status = status

    def diarize(self, pcm_path, spans):
        from app.diarization import DiarizationResult

        if self.status != "completed":
            return DiarizationResult([None] * len(spans), self.status, "local", "fake")
        labels = self.scripts.pop(0) if self.scripts else [0] * len(spans)
        return DiarizationResult(labels, "completed", "local", "fake", {"threshold": 0.5})
