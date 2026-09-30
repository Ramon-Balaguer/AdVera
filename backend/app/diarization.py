"""Local speaker diarization (spec §5, §8; ADR 0003, 0005).

DiarizationEngine
  -> LocalDiarizationProvider   ECAPA-VoxCeleb embeddings + deterministic clustering

Speakers are anonymous labels (`SPEAKER_00`, ...), never people. Each track is diarized on
its own; labels are not reconciled across tracks (ADR 0005). Voice regions come from the
definitive ASR segments. Each segment is cut into fixed windows; a final partial window is
kept when it still holds enough audio (speaker-diarization-quality.md). Window embeddings
are averaged per segment and the segments are clustered with average linkage on cosine
similarity. Missing models, too little audio or an encoder failure return no labels and
never fail the transcript (local-speaker-diarization.md).
"""

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import numpy as np

from app.storage import SAMPLE_RATE

logger = logging.getLogger("advera.diarization")

DiarizationStatus = Literal["completed", "insufficient_audio", "unavailable", "skipped"]


class EmbeddingEncoder(Protocol):
    name: str

    def encode(self, windows: list[np.ndarray]) -> np.ndarray:
        """Return one embedding row per float32 mono 16 kHz window."""
        ...


@dataclass(frozen=True)
class SpeechSpan:
    start: float
    end: float


@dataclass
class DiarizationResult:
    labels: list[int | None]
    status: DiarizationStatus
    provider: str
    model: str
    parameters: dict[str, float | int | None] = field(default_factory=dict)

    @property
    def speaker_count(self) -> int:
        return len({label for label in self.labels if label is not None})


class DiarizationEngine(Protocol):
    name: str

    def diarize(self, pcm_path: Path, spans: list[SpeechSpan]) -> DiarizationResult: ...


class DiarizationUnavailable(Exception):
    """The encoder or its model cannot be loaded. The message is never logged."""


class LocalDiarizationProvider:
    name = "local"

    def __init__(
        self,
        encoder: EmbeddingEncoder,
        *,
        window_seconds: float = 1.5,
        hop_seconds: float = 0.75,
        min_window_seconds: float = 0.25,
        min_cluster_seconds: float = 1.0,
        min_speaker_seconds: float = 8.0,
        min_speaker_fraction: float = 0.03,
        threshold: float = 0.5,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> None:
        self.encoder = encoder
        self.window_seconds = window_seconds
        self.hop_seconds = hop_seconds
        self.min_window_seconds = min_window_seconds
        self.min_cluster_seconds = min_cluster_seconds
        self.min_speaker_seconds = min_speaker_seconds
        self.min_speaker_fraction = min_speaker_fraction
        self.threshold = threshold
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers

    @property
    def parameters(self) -> dict[str, float | int | None]:
        return {
            "window_seconds": self.window_seconds,
            "hop_seconds": self.hop_seconds,
            "min_window_seconds": self.min_window_seconds,
            "min_cluster_seconds": self.min_cluster_seconds,
            "min_speaker_seconds": self.min_speaker_seconds,
            "min_speaker_fraction": self.min_speaker_fraction,
            "threshold": self.threshold,
            "min_speakers": self.min_speakers,
            "max_speakers": self.max_speakers,
        }

    def _result(self, labels: list[int | None], status: DiarizationStatus) -> DiarizationResult:
        return DiarizationResult(labels, status, self.name, self.encoder.name, self.parameters)

    def windows(self, audio: np.ndarray, span: SpeechSpan) -> list[np.ndarray]:
        start = int(span.start * SAMPLE_RATE)
        end = min(int(span.end * SAMPLE_RATE), len(audio))
        size = int(self.window_seconds * SAMPLE_RATE)
        hop = int(self.hop_seconds * SAMPLE_RATE)
        minimum = int(self.min_window_seconds * SAMPLE_RATE)
        windows = []
        position = start
        while position < end:
            window = audio[position : min(position + size, end)]
            if len(window) >= minimum:  # partial windows count when they hold enough audio
                windows.append(window)
            if position + size >= end:
                break
            position += hop
        return windows

    def diarize(self, pcm_path: Path, spans: list[SpeechSpan]) -> DiarizationResult:
        audio = np.fromfile(pcm_path, dtype="<i2").astype(np.float32) / 32768.0
        per_span = [self.windows(audio, span) for span in spans]
        usable = [index for index, windows in enumerate(per_span) if windows]
        if not usable:
            return self._result([None] * len(spans), "insufficient_audio")
        try:
            flat = [window for index in usable for window in per_span[index]]
            embeddings = np.asarray(self.encoder.encode(flat), dtype=np.float64)
        except DiarizationUnavailable:
            return self._result([None] * len(spans), "unavailable")
        except Exception as error:
            logger.warning("diarization encoder failed: %s", type(error).__name__)
            return self._result([None] * len(spans), "unavailable")

        vectors, offset = {}, 0
        for index in usable:
            count = len(per_span[index])
            vectors[index] = embeddings[offset : offset + count].mean(axis=0)
            offset += count

        # Short segments give noisy embeddings and would create spurious speakers
        # (speaker-diarization-quality.md): only reliable segments form clusters; short
        # ones join the most similar cluster.
        reliable = [
            index
            for index in usable
            if spans[index].end - spans[index].start >= self.min_cluster_seconds
        ] or usable
        clusters = self.cluster(np.vstack([vectors[index] for index in reliable]))
        clusters = self._absorb_small_clusters(clusters, reliable, vectors, spans)
        labels: list[int | None] = [None] * len(spans)
        for index, cluster in zip(reliable, clusters, strict=True):
            labels[index] = cluster
        centroids = {
            cluster: _unit(
                np.mean(
                    [vectors[i] for i, c in zip(reliable, clusters, strict=True) if c == cluster],
                    axis=0,
                )
            )
            for cluster in set(clusters)
        }
        for index in usable:
            if labels[index] is None:
                vector = _unit(vectors[index])
                labels[index] = max(
                    centroids, key=lambda cluster: float(vector @ centroids[cluster])
                )
        return self._result(relabel_by_first_appearance(labels), "completed")

    def _absorb_small_clusters(
        self,
        clusters: list[int],
        indexes: list[int],
        vectors: dict[int, np.ndarray],
        spans: list[SpeechSpan],
    ) -> list[int]:
        """Real recordings produce many tiny clusters (noise, laughter, very short turns).

        A cluster with too little speech is not a participant: it joins the most similar
        cluster that has enough speech. A participant who speaks less than the limit is merged
        too, which is the accepted cost of not inventing dozens of speakers.
        """
        seconds: dict[int, float] = {}
        for index, cluster in zip(indexes, clusters, strict=True):
            seconds[cluster] = seconds.get(cluster, 0.0) + spans[index].end - spans[index].start
        total = sum(seconds.values())
        # Capped at a quarter of the speech so short recordings are not wiped out.
        limit = min(max(self.min_speaker_seconds, self.min_speaker_fraction * total), total / 4)
        keep = {cluster for cluster, total in seconds.items() if total >= limit}
        if not keep:  # nobody has enough speech: the largest cluster is the only speaker
            keep = {max(seconds, key=seconds.__getitem__)}
        if len(keep) == len(seconds):
            return clusters
        centroids = {
            cluster: _unit(
                np.mean(
                    [vectors[i] for i, c in zip(indexes, clusters, strict=True) if c == cluster],
                    axis=0,
                )
            )
            for cluster in seconds
        }
        target = {
            cluster: cluster
            if cluster in keep
            else max(keep, key=lambda big: float(centroids[cluster] @ centroids[big]))
            for cluster in seconds
        }
        return [target[cluster] for cluster in clusters]

    def cluster(self, vectors: np.ndarray) -> list[int]:
        """Average-linkage agglomerative clustering on cosine similarity. Deterministic."""
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        unit = vectors / np.where(norms == 0, 1, norms)
        similarity = unit @ unit.T
        clusters: list[list[int]] = [[index] for index in range(len(unit))]
        floor = self.min_speakers or 1
        while len(clusters) > floor:
            best, pair = -np.inf, None
            for a in range(len(clusters)):
                for b in range(a + 1, len(clusters)):
                    score = similarity[np.ix_(clusters[a], clusters[b])].mean()
                    if score > best:
                        best, pair = score, (a, b)
            too_many = self.max_speakers is not None and len(clusters) > self.max_speakers
            if pair is None or (best < self.threshold and not too_many):
                break
            a, b = pair
            clusters[a] = sorted(clusters[a] + clusters[b])
            del clusters[b]
        assignment = [0] * len(unit)
        for label, members in enumerate(clusters):
            for member in members:
                assignment[member] = label
        return assignment


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def relabel_by_first_appearance(labels: list[int | None]) -> list[int | None]:
    mapping: dict[int, int] = {}
    result: list[int | None] = []
    for label in labels:
        if label is None:
            result.append(None)
            continue
        mapping.setdefault(label, len(mapping))
        result.append(mapping[label])
    return result


def speaker_label(index: int) -> str:
    return f"SPEAKER_{index:02d}"


class EcapaEncoder:
    """SpeechBrain ECAPA-TDNN speaker embeddings, loaded lazily (optional `asr` extra)."""

    def __init__(self, source: str, cache_dir: str, device: str) -> None:
        self.name = source
        self.source = source
        self.cache_dir = cache_dir
        self.device = device
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            try:
                from speechbrain.inference.speaker import EncoderClassifier
            except ImportError as error:
                raise DiarizationUnavailable("SPEECHBRAIN_NOT_INSTALLED") from error
            try:
                self._model = EncoderClassifier.from_hparams(
                    source=self.source,
                    savedir=str(Path(self.cache_dir) / self.source.replace("/", "--")),
                    run_opts={"device": self.device},
                )
            except Exception as error:
                raise DiarizationUnavailable("ECAPA_MODEL_UNAVAILABLE") from error
        return self._model

    def encode(self, windows: list[np.ndarray]) -> np.ndarray:
        import torch

        with self._lock:
            model = self._load()
            rows = []
            batch = 32
            for start in range(0, len(windows), batch):
                chunk = windows[start : start + batch]
                longest = max(len(window) for window in chunk)
                padded = np.zeros((len(chunk), longest), dtype=np.float32)
                lengths = np.zeros(len(chunk), dtype=np.float32)
                for row, window in enumerate(chunk):
                    padded[row, : len(window)] = window
                    lengths[row] = len(window) / longest
                with torch.no_grad():
                    output = model.encode_batch(
                        torch.from_numpy(padded), wav_lens=torch.from_numpy(lengths)
                    )
                rows.append(output.squeeze(1).cpu().numpy())
            return np.vstack(rows)
