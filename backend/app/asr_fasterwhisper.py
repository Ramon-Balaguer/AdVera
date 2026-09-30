"""faster-whisper provider with per-chunk language detection (ADR 0014, ADR 0018).

WhisperX decides one language per track and then decodes everything in it, which drops or
silently translates the other languages of a multilingual meeting. Here each voice chunk
found by VAD gets its own language, and is decoded in that language, so nothing is
translated. Chunks under MIN_DETECT_SECONDS inherit the language of the nearest reliable
neighbor, because detection on very short audio is unstable. No language is ever passed in
from outside: this is autodetection per segment, not an override.

faster-whisper and torch are optional (`.[asr]`) and imported lazily. torch must be
imported first: it loads the CUDA libraries that CTranslate2 needs.
"""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from app.asr import AsrSegment, ProviderConfigurationError, ProviderError

SAMPLE_RATE = 16_000
MIN_DETECT_SECONDS = 1.2
MAX_CHUNK_SECONDS = 30.0
MIN_SILENCE_MS = 400
# A language must cover this share of the detected speech to count as a language of the
# meeting. Detection on short or noisy chunks otherwise invents languages (observed on a real
# 46 min recording: 22 languages, most of them a few seconds long).
MIN_LANGUAGE_SHARE = 0.05
BEAM_SIZE = 5

Chunk = tuple[float, float]  # start, end in seconds


def assign_languages(chunks: list[Chunk], detected: list[str | None]) -> list[str | None]:
    """Fill chunks whose language could not be detected reliably from the nearest reliable one."""
    reliable = [index for index, language in enumerate(detected) if language]
    if not reliable:
        return list(detected)
    result = list(detected)
    for index, language in enumerate(detected):
        if language:
            continue
        nearest = min(reliable, key=lambda other: (abs(other - index), other))
        result[index] = detected[nearest]
    return result


def dominant_languages(
    chunks: list[Chunk], probabilities: list[dict[str, float] | None]
) -> set[str]:
    """Languages covering at least MIN_LANGUAGE_SHARE of the detected speech (never empty)."""
    weight: dict[str, float] = {}
    for (start, end), probs in zip(chunks, probabilities, strict=True):
        if probs:
            top = max(probs, key=probs.__getitem__)
            weight[top] = weight.get(top, 0.0) + (end - start)
    if not weight:
        return set()
    total = sum(weight.values())
    kept = {name for name, seconds in weight.items() if seconds / total >= MIN_LANGUAGE_SHARE}
    return kept or {max(weight, key=weight.__getitem__)}


def restrict(probs: dict[str, float] | None, allowed: set[str]) -> str | None:
    if not probs or not allowed:
        return None
    return max(allowed, key=lambda language: probs.get(language, 0.0))


class FasterWhisperProvider:
    name = "faster-whisper"

    def __init__(
        self,
        model: str,
        device: str,
        compute_type: str,
        *,
        model_loader: Callable[[], Any] | None = None,
        vad: Callable[[np.ndarray], list[Chunk]] | None = None,
    ) -> None:
        if device == "cuda" and compute_type == "int8":
            raise ProviderConfigurationError("CUDA_INT8_UNSUPPORTED")
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self._loader = model_loader
        self._vad = vad
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is None:
            if self._loader is not None:
                self._model = self._loader()
            else:
                try:
                    import torch  # noqa: F401  (must precede CTranslate2 for the CUDA libs)
                    from faster_whisper import WhisperModel
                except ImportError as error:
                    raise ProviderConfigurationError("FASTER_WHISPER_NOT_INSTALLED") from error
                if self.device == "cuda" and not torch.cuda.is_available():
                    raise ProviderConfigurationError("CUDA_UNAVAILABLE")
                self._model = WhisperModel(
                    self.model, device=self.device, compute_type=self.compute_type
                )
        return self._model

    def _chunks(self, audio: np.ndarray) -> list[Chunk]:
        if self._vad is not None:
            return self._vad(audio)
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        options = VadOptions(
            min_silence_duration_ms=MIN_SILENCE_MS, max_speech_duration_s=MAX_CHUNK_SECONDS
        )
        return [
            (found["start"] / SAMPLE_RATE, found["end"] / SAMPLE_RATE)
            for found in get_speech_timestamps(audio, options)
        ]

    def transcribe(self, pcm_path: Path) -> list[AsrSegment]:
        audio = np.fromfile(pcm_path, dtype="<i2").astype(np.float32) / 32768.0
        with self._lock:
            model = self._load()
            try:
                chunks = self._chunks(audio)
                probabilities: list[dict[str, float] | None] = []
                for start, end in chunks:
                    piece = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
                    if end - start < MIN_DETECT_SECONDS:
                        probabilities.append(None)
                    else:
                        _language, _prob, all_probs = model.detect_language(piece)
                        probabilities.append(dict(all_probs))
                allowed = dominant_languages(chunks, probabilities)
                detected = [restrict(probs, allowed) for probs in probabilities]
                languages = assign_languages(chunks, detected)
                segments: list[AsrSegment] = []
                for (start, end), language in zip(chunks, languages, strict=True):
                    piece = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
                    found, _info = model.transcribe(
                        piece,
                        language=language,
                        beam_size=BEAM_SIZE,
                        condition_on_previous_text=False,
                        word_timestamps=True,
                    )
                    for item in found:
                        text = item.text.strip()
                        if not text:
                            continue
                        # Whisper's segment bounds can include silence; word times are tight,
                        # which keeps diarization windows on actual speech.
                        words = getattr(item, "words", None) or []
                        first = float(words[0].start) if words else float(item.start)
                        last = float(words[-1].end) if words else float(item.end)
                        segments.append(
                            AsrSegment(
                                start=start + first,
                                end=start + max(last, first),
                                text=text,
                                language=language,
                            )
                        )
            except ProviderError:
                raise
            except Exception as error:
                raise ProviderError("FASTER_WHISPER_FAILED") from error
        return segments
