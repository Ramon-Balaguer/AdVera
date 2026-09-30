"""WhisperX provider: live transcription and explicit definitive fallback (ADR 0003).

WhisperX and torch are optional dependencies (`pip install .[asr]`) imported lazily, so the
API and tests never load models. No language is passed: WhisperX detects one language per
track, attached to every segment of that track (definitive-transcription-segment-language.md).
Alignment is best effort per detected language (spec §7.1); without an alignment model the
unaligned segments are kept.
"""

import threading
from pathlib import Path
from typing import Any

from app.asr import AsrSegment, ProgressCallback, ProviderConfigurationError, ProviderError

BATCH_SIZE = 8


class WhisperXProvider:
    name = "whisperx"

    def __init__(self, model: str, device: str, compute_type: str) -> None:
        # nvidia-cuda-asr-runtime.md: reject the known incompatible CUDA + int8 combination.
        if device == "cuda" and compute_type == "int8":
            raise ProviderConfigurationError("CUDA_INT8_UNSUPPORTED")
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self._asr_model: Any = None
        self._align_models: dict[str, tuple[Any, Any] | None] = {}
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._asr_model is None:
            try:
                import torch
                import whisperx
            except ImportError as error:
                raise ProviderConfigurationError("WHISPERX_NOT_INSTALLED") from error
            if self.device == "cuda" and not torch.cuda.is_available():
                raise ProviderConfigurationError("CUDA_UNAVAILABLE")
            self._asr_model = whisperx.load_model(
                self.model, self.device, compute_type=self.compute_type
            )
        return self._asr_model

    def _align_model(self, language: str) -> tuple[Any, Any] | None:
        if language not in self._align_models:
            import whisperx

            try:
                self._align_models[language] = whisperx.load_align_model(
                    language_code=language, device=self.device
                )
            except Exception:  # no alignment model for this language
                self._align_models[language] = None
        return self._align_models[language]

    def transcribe(
        self, pcm_path: Path, on_progress: ProgressCallback | None = None
    ) -> list[AsrSegment]:
        # WhisperX exposes no reliable internal progress: progress advances per track.
        import numpy as np
        import whisperx

        with self._lock:
            try:
                model = self._load()
            except ProviderError:
                raise
            except Exception as error:  # download, out of memory…: let the worker decide
                raise ProviderError("MODEL_LOAD_FAILED") from error
            try:
                audio = np.fromfile(pcm_path, dtype="<i2").astype(np.float32) / 32768.0
                result = model.transcribe(audio, batch_size=BATCH_SIZE)
            except ProviderError:
                raise
            except Exception as error:
                raise ProviderError("WHISPERX_FAILED") from error

            language = result.get("language") or None
            segments = result.get("segments", [])
            aligner = self._align_model(language) if language else None
            if aligner is not None and segments:
                align_model, metadata = aligner
                try:
                    segments = whisperx.align(
                        segments,
                        align_model,
                        metadata,
                        audio,
                        self.device,
                        return_char_alignments=False,
                    )["segments"]
                except Exception:
                    pass  # keep unaligned segments; alignment is an enhancement

        normalized: list[AsrSegment] = []
        for segment in segments:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            normalized.append(
                AsrSegment(
                    start=float(segment["start"]),
                    end=float(segment["end"]),
                    text=text,
                    language=language,
                    speaker=segment.get("speaker"),
                )
            )
        return normalized
