"""ASR provider boundary (spec §3.5, §5; ADR 0003).

Downstream consumers see one normalized contract regardless of provider. Providers never
receive a language code: they autodetect and report language metadata (ADR 0014).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from app.config import Settings

AsrRole = Literal["live", "definitive"]


@dataclass(frozen=True)
class AsrSegment:
    start: float
    end: float
    text: str
    language: str | None = None
    speaker: str | None = None


class ProviderError(Exception):
    """A provider failure. `code` is safe to persist; the message is never logged."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProviderConfigurationError(ProviderError):
    """The provider cannot run with the current configuration. Not retryable."""


class TranscriptionEngine(Protocol):
    name: str
    model: str

    def transcribe(self, pcm_path: Path) -> list[AsrSegment]:
        """Transcribe one PCM16 mono 16 kHz track. Blocking; call from a worker thread."""
        ...


def build_engine(provider: str, role: AsrRole, settings: Settings) -> TranscriptionEngine:
    if provider == "whisperx":
        from app.asr_whisperx import WhisperXProvider

        model = settings.asr_live_model if role == "live" else settings.asr_definitive_model
        return WhisperXProvider(
            model=model, device=settings.asr_device, compute_type=settings.asr_compute_type
        )
    if provider == "faster-whisper":
        from app.asr_fasterwhisper import FasterWhisperProvider

        model = settings.asr_live_model if role == "live" else settings.asr_definitive_model
        return FasterWhisperProvider(
            model=model, device=settings.asr_device, compute_type=settings.asr_compute_type
        )
    if provider == "moss":
        # MOSS is opt-in and arrives with its own increment (ADR 0007).
        raise ProviderConfigurationError("MOSS_NOT_AVAILABLE")
    raise ProviderConfigurationError("UNKNOWN_PROVIDER")


def definitive_model_name(provider: str, settings: Settings) -> str:
    if provider in ("whisperx", "faster-whisper"):
        return settings.asr_definitive_model
    return provider
