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

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from app.asr import AsrSegment, ProgressCallback, ProviderConfigurationError, ProviderError

logger = logging.getLogger("advera.asr.faster_whisper")

SAMPLE_RATE = 16_000
MIN_DETECT_SECONDS = 1.2
MAX_CHUNK_SECONDS = 30.0
MIN_SILENCE_MS = 400
# A language must cover this share of the detected speech to count as a language of the
# meeting. Detection on short or noisy chunks otherwise invents languages (observed on a real
# 46 min recording: 22 languages, most of them a few seconds long).
MIN_LANGUAGE_SHARE = 0.05
# A language below MIN_LANGUAGE_SHARE still counts when the detector is sure about it (ADR 0018),
# calibrated on a real 46 min Catalan/Spanish recording, where 488 voice chunks produced 46
# chunks in languages that were not spoken. Only 8 of them reached probability 0.7, all shorter
# than 2.7 s and none above 0.96 for more than 1.8 s, so probability alone cannot tell a real
# short turn from noise; duration has to help:
#   (a) one chunk of at least SURE_CHUNK_SECONDS with probability >= SURE_LANGUAGE_PROBABILITY, or
#   (b) at least ACCUMULATED_SECONDS of chunks with probability >= CONFIDENT_LANGUAGE_PROBABILITY.
CONFIDENT_LANGUAGE_PROBABILITY = 0.7
SURE_LANGUAGE_PROBABILITY = 0.85
SURE_CHUNK_SECONDS = 3.0
ACCUMULATED_SECONDS = 6.0
# Share of the reported progress spent detecting languages; decoding takes the rest.
DETECTION_SHARE = 0.2
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


def confident_minorities(
    chunks: list[Chunk], probabilities: list[dict[str, float] | None], dominant: set[str]
) -> set[str]:
    """Languages outside `dominant` that the detector is sure about (see the constants above)."""
    sure: set[str] = set()
    accumulated: dict[str, float] = {}
    for (start, end), probs in zip(chunks, probabilities, strict=True):
        if not probs:
            continue
        top = max(probs, key=probs.__getitem__)
        if top in dominant:
            continue
        seconds = end - start
        if probs[top] >= SURE_LANGUAGE_PROBABILITY and seconds >= SURE_CHUNK_SECONDS:
            sure.add(top)
        if probs[top] >= CONFIDENT_LANGUAGE_PROBABILITY:
            accumulated[top] = accumulated.get(top, 0.0) + seconds
    return sure | {name for name, seconds in accumulated.items() if seconds >= ACCUMULATED_SECONDS}


def restrict(probs: dict[str, float] | None, allowed: set[str]) -> str | None:
    """The most probable of the languages allowed for the meeting."""
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

    def _load_checked(self) -> Any:
        """Load the model; any failure (download, out of memory…) is a provider error, so the
        worker takes the ADR 0003 fallback path instead of failing the job as internal."""
        try:
            return self._load()
        except ProviderError:
            raise
        except Exception as error:
            # Only the exception type is logged (no path, URL or message), so a persistent
            # cause (typo in the model name, offline cache, out of memory) is visible.
            logger.error("model load failed: %s", type(error).__name__)
            raise ProviderError("MODEL_LOAD_FAILED") from error

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

    def transcribe(
        self, pcm_path: Path, on_progress: ProgressCallback | None = None
    ) -> list[AsrSegment]:
        try:
            audio = np.fromfile(pcm_path, dtype="<i2").astype(np.float32) / 32768.0
        except Exception as error:
            raise ProviderError("AUDIO_READ_FAILED") from error
        with self._lock:
            model = self._load_checked()
            try:
                chunks = self._chunks(audio)
                # Progress is measured, not estimated: seconds of speech already processed
                # over the speech found by VAD, first for language detection, then decoding.
                total = sum(end - start for start, end in chunks) or 1.0
                report = on_progress or (lambda _fraction: None)
                done = 0.0
                probabilities: list[dict[str, float] | None] = []
                for start, end in chunks:
                    done += end - start
                    report(DETECTION_SHARE * done / total)
                    piece = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
                    if end - start < MIN_DETECT_SECONDS:
                        probabilities.append(None)
                    else:
                        _language, _prob, all_probs = model.detect_language(piece)
                        probabilities.append(dict(all_probs))
                dominant = dominant_languages(chunks, probabilities)
                allowed = dominant | confident_minorities(chunks, probabilities, dominant)
                detected = [restrict(probs, allowed) for probs in probabilities]
                languages = assign_languages(chunks, detected)
                logger.info("track languages: %s", sorted(allowed))  # codes only
                segments: list[AsrSegment] = []
                done = 0.0
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
                    done += end - start
                    report(DETECTION_SHARE + (1 - DETECTION_SHARE) * done / total)
            except ProviderError:
                raise
            except Exception as error:
                raise ProviderError("FASTER_WHISPER_FAILED") from error
        return segments
