"""Per-chunk language detection with a fake model: no GPU, no downloads."""

from types import SimpleNamespace

import numpy as np

from app.asr_fasterwhisper import FasterWhisperProvider, assign_languages

RATE = 16_000


class FakeModel:
    def __init__(self, languages):
        # Each entry is a language, or a {language: probability} dict for ambiguous chunks.
        self.languages = list(languages)
        self.transcribed: list[str | None] = []

    def detect_language(self, piece):
        entry = self.languages.pop(0)
        probs = entry if isinstance(entry, dict) else {entry: 0.99}
        top = max(probs, key=probs.__getitem__)
        return top, probs[top], list(probs.items())

    def transcribe(self, piece, language=None, **_options):
        self.transcribed.append(language)
        item = SimpleNamespace(start=0.0, end=len(piece) / RATE, text=f" text in {language} ")
        return [item], None


class WordTimedModel(FakeModel):
    def transcribe(self, piece, language=None, **_options):
        words = [SimpleNamespace(start=0.4, end=0.9), SimpleNamespace(start=1.0, end=1.6)]
        item = SimpleNamespace(start=0.0, end=3.0, text=" hi ", words=words)
        return [item], None


def provider(chunks, model):
    return FasterWhisperProvider(
        "large-v3", "cpu", "int8", model_loader=lambda: model, vad=lambda audio: chunks
    )


def pcm(tmp_path, seconds):
    path = tmp_path / "t.pcm"
    path.write_bytes((np.zeros(int(seconds * RATE))).astype("<i2").tobytes())
    return path


def test_each_chunk_is_decoded_in_its_own_language_with_absolute_timestamps(tmp_path):
    model = FakeModel(["es", "en", "ca"])
    chunks = [(0.0, 3.0), (4.0, 8.0), (9.0, 12.0)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 12))

    assert [s.language for s in segments] == ["es", "en", "ca"]
    assert model.transcribed == ["es", "en", "ca"]  # forced per chunk, never translated
    assert [s.start for s in segments] == [0.0, 4.0, 9.0]
    assert segments[1].end == 8.0
    assert segments[1].text == "text in en"


def test_short_chunks_inherit_the_nearest_reliable_language(tmp_path):
    model = FakeModel(["en", "ca"])  # only the two long chunks are detected
    chunks = [(0.0, 3.0), (3.5, 4.0), (5.0, 8.0)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 8))

    assert [s.language for s in segments] == ["en", "en", "ca"]


def test_assign_languages_edge_cases():
    assert assign_languages([(0, 1)], [None]) == [None]
    assert assign_languages([(0, 1), (1, 5)], [None, "ca"]) == ["ca", "ca"]


def test_model_failure_is_a_controlled_provider_error(tmp_path):
    class Broken(FakeModel):
        def detect_language(self, piece):
            raise RuntimeError("boom")

    import pytest

    from app.asr import ProviderError

    with pytest.raises(ProviderError) as error:
        provider([(0.0, 3.0)], Broken([])).transcribe(pcm(tmp_path, 3))
    assert error.value.code == "FASTER_WHISPER_FAILED"


def test_segment_bounds_follow_word_times_not_padded_segment_times(tmp_path):
    segments = provider([(10.0, 13.0)], WordTimedModel(["en"])).transcribe(pcm(tmp_path, 13))
    assert (segments[0].start, segments[0].end) == (10.4, 11.6)


def test_minor_languages_are_reassigned_to_the_dominant_ones(tmp_path):
    # 20 s of Catalan and 20 s of Spanish, plus a 1.5 s chunk "detected" as Japanese that is
    # really Catalan with noise (3.6% of the speech): it must not become a language of the meeting.
    ambiguous = {"ja": 0.5, "ca": 0.4, "es": 0.1}
    model = FakeModel(["ca", "es", ambiguous])
    chunks = [(0.0, 20.0), (21.0, 41.0), (42.0, 43.5)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 45))

    assert [s.language for s in segments] == ["ca", "es", "ca"]
