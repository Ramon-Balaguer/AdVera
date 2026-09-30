"""Local diarization core with a deterministic encoder: synthetic tones stand in for voices."""

from pathlib import Path

import numpy as np
import pytest

from app.diarization import (
    DiarizationUnavailable,
    LocalDiarizationProvider,
    SpeechSpan,
    relabel_by_first_appearance,
    speaker_label,
)

RATE = 16_000


class ToneEncoder:
    """Embeds a window by its dominant frequency, so each tone is a distinct 'voice'."""

    name = "tone-encoder"

    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.window_lengths: list[int] = []

    def encode(self, windows):
        if self.fail:
            raise self.fail
        rows = []
        for window in windows:
            self.window_lengths.append(len(window))
            spectrum = np.abs(np.fft.rfft(window))
            frequency = np.fft.rfftfreq(len(window), 1 / RATE)[int(np.argmax(spectrum))]
            angle = frequency / 1000 * np.pi  # 200 Hz and 700 Hz end up far apart
            rows.append([np.cos(angle), np.sin(angle)])
        return np.array(rows)


def write_tones(path: Path, schedule: list[tuple[float, float]]) -> Path:
    """schedule: (seconds, frequency); frequency 0 writes silence."""
    chunks = []
    for seconds, frequency in schedule:
        t = np.arange(int(seconds * RATE)) / RATE
        chunks.append(0.3 * np.sin(2 * np.pi * frequency * t) if frequency else np.zeros_like(t))
    audio = np.concatenate(chunks)
    path.write_bytes((audio * 32767).astype("<i2").tobytes())
    return path


def spans(*pairs):
    return [SpeechSpan(start, end) for start, end in pairs]


def test_alternating_voices_get_two_speakers_labelled_by_first_appearance(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(3, 200), (3, 700), (3, 200), (3, 700)])
    provider = LocalDiarizationProvider(ToneEncoder())

    result = provider.diarize(pcm, spans((0, 3), (3, 6), (6, 9), (9, 12)))

    assert result.status == "completed"
    assert result.labels == [0, 1, 0, 1]
    assert result.speaker_count == 2
    assert result.provider == "local" and result.model == "tone-encoder"
    assert result.parameters["threshold"] == 0.5


def test_single_voice_is_one_speaker(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(4, 300)])
    result = LocalDiarizationProvider(ToneEncoder()).diarize(pcm, spans((0, 2), (2, 4)))
    assert result.labels == [0, 0]


def test_short_segment_keeps_partial_window(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(0.8, 200)])
    encoder = ToneEncoder()
    result = LocalDiarizationProvider(encoder).diarize(pcm, spans((0, 0.8)))
    assert result.labels == [0]
    assert encoder.window_lengths == [int(0.8 * RATE)]


def test_too_short_audio_is_insufficient_without_failing(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(0.2, 200)])
    result = LocalDiarizationProvider(ToneEncoder()).diarize(pcm, spans((0, 0.2)))
    assert (result.status, result.labels) == ("insufficient_audio", [None])


@pytest.mark.parametrize("error", [DiarizationUnavailable("MODEL"), RuntimeError("boom")])
def test_encoder_failure_leaves_no_labels(tmp_path, error):
    pcm = write_tones(tmp_path / "t.pcm", [(2, 200)])
    result = LocalDiarizationProvider(ToneEncoder(fail=error)).diarize(pcm, spans((0, 2)))
    assert (result.status, result.labels) == ("unavailable", [None])


def test_speaker_bounds_are_respected(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(2, 200), (2, 450), (2, 700)])
    three = spans((0, 2), (2, 4), (4, 6))
    capped = LocalDiarizationProvider(ToneEncoder(), max_speakers=2).diarize(pcm, three)
    assert capped.speaker_count == 2
    single = write_tones(tmp_path / "s.pcm", [(4, 300)])
    forced = LocalDiarizationProvider(ToneEncoder(), min_speakers=2, threshold=0.99).diarize(
        single, spans((0, 2), (2, 4))
    )
    assert forced.speaker_count == 2


def test_clustering_is_deterministic(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(2, 200), (2, 700)] * 3)
    provider = LocalDiarizationProvider(ToneEncoder())
    segments = spans(*[(i * 2, i * 2 + 2) for i in range(6)])
    assert provider.diarize(pcm, segments).labels == provider.diarize(pcm, segments).labels


def test_labels():
    assert relabel_by_first_appearance([3, None, 1, 3]) == [0, None, 1, 0]
    assert speaker_label(2) == "SPEAKER_02"


def test_short_segments_join_the_closest_speaker_instead_of_creating_one(tmp_path):
    # A 0.6 s segment with a slightly different "voice" must not become a third speaker.
    pcm = write_tones(tmp_path / "t.pcm", [(3, 200), (0.6, 260), (3, 700), (3, 200)])
    result = LocalDiarizationProvider(ToneEncoder()).diarize(
        pcm, spans((0, 3), (3, 3.6), (3.6, 6.6), (6.6, 9.6))
    )
    assert result.labels == [0, 0, 1, 0]
    assert result.speaker_count == 2


def test_only_short_segments_still_cluster(tmp_path):
    pcm = write_tones(tmp_path / "t.pcm", [(0.6, 200), (0.6, 700)])
    result = LocalDiarizationProvider(ToneEncoder()).diarize(pcm, spans((0, 0.6), (0.6, 1.2)))
    assert result.labels == [0, 1]


def test_tiny_clusters_are_absorbed_instead_of_becoming_speakers(tmp_path):
    # Two real voices talk for 40 s each; ten 1.2 s bursts in other "voices" are noise.
    schedule = [(40, 200), (40, 700)] + [(1.2, 300 + 40 * i) for i in range(10)]
    pcm = write_tones(tmp_path / "t.pcm", schedule)
    starts = [0.0, 40.0] + [80.0 + 1.2 * i for i in range(10)]
    lengths = [40.0, 40.0] + [1.2] * 10
    # A strict threshold makes every burst its own cluster, as noisy real embeddings do.
    provider = LocalDiarizationProvider(ToneEncoder(), threshold=0.99)
    result = provider.diarize(
        pcm, spans(*[(s, s + n) for s, n in zip(starts, lengths, strict=True)])
    )
    assert result.speaker_count == 2
    assert result.labels[:2] == [0, 1]


def reference_cluster(provider, vectors):
    """The original block-averaging implementation, kept as the oracle for the fast one."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    unit = vectors / np.where(norms == 0, 1, norms)
    similarity = unit @ unit.T
    clusters = [[index] for index in range(len(unit))]
    floor = provider.min_speakers or 1
    while len(clusters) > floor:
        best, pair = -np.inf, None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                score = similarity[np.ix_(clusters[a], clusters[b])].mean()
                if score > best:
                    best, pair = score, (a, b)
        too_many = provider.max_speakers is not None and len(clusters) > provider.max_speakers
        if pair is None or (best < provider.threshold and not too_many):
            break
        a, b = pair
        clusters[a] = sorted(clusters[a] + clusters[b])
        del clusters[b]
    assignment = [0] * len(unit)
    for label, members in enumerate(clusters):
        for member in members:
            assignment[member] = label
    return assignment


@pytest.mark.parametrize("count", [1, 2, 7, 40, 60])
@pytest.mark.parametrize(
    "options",
    [{}, {"threshold": 0.2}, {"threshold": 0.8}, {"min_speakers": 3}, {"max_speakers": 2}],
)
def test_fast_clustering_matches_the_original_algorithm(count, options):
    rng = np.random.default_rng(count)
    centres = rng.normal(size=(4, 24))
    vectors = centres[rng.integers(0, 4, size=count)] + rng.normal(scale=0.7, size=(count, 24))
    provider = LocalDiarizationProvider(ToneEncoder(), **options)
    assert provider.cluster(vectors) == reference_cluster(provider, vectors)


def test_clustering_a_two_hour_track_takes_seconds():
    import time

    rng = np.random.default_rng(7)
    centres = rng.normal(size=(5, 24))
    vectors = centres[rng.integers(0, 5, size=1500)] + rng.normal(scale=0.8, size=(1500, 24))
    provider = LocalDiarizationProvider(ToneEncoder())
    started = time.monotonic()
    labels = provider.cluster(vectors)
    assert time.monotonic() - started < 60  # the cubic version needed hours
    assert len(set(labels)) >= 2


def test_a_nan_embedding_does_not_merge_everything():
    rng = np.random.default_rng(3)
    centres = rng.normal(size=(3, 16)) * 4
    vectors = centres[rng.integers(0, 3, size=12)] + rng.normal(scale=0.2, size=(12, 16))
    with_nan = vectors.copy()
    with_nan[4] = np.nan
    provider = LocalDiarizationProvider(ToneEncoder())
    labels = provider.cluster(with_nan)
    assert len(set(labels)) >= 3  # the three real voices survive the broken row
    assert labels == provider.cluster(np.where(np.isnan(with_nan), 0.0, with_nan))


def test_very_long_tracks_cluster_a_sample_and_still_label_every_segment(tmp_path, monkeypatch):
    import app.diarization as diarization

    monkeypatch.setattr(diarization, "MAX_CLUSTER_SEGMENTS", 12)
    pcm = write_tones(tmp_path / "long.pcm", [(2, 200), (2, 700)] * 15)
    provider = LocalDiarizationProvider(ToneEncoder())
    segments = spans(*[(i * 2, i * 2 + 2) for i in range(30)])
    result = provider.diarize(pcm, segments)
    assert result.status == "completed" and len(result.labels) == 30
    assert None not in result.labels
    assert len(set(result.labels)) == 2  # both voices, although only 12 segments were clustered
