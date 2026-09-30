"""Per-chunk language detection with a fake model: no GPU, no downloads."""

from types import SimpleNamespace

import numpy as np
import pytest

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


def test_progress_is_measured_in_speech_seconds_and_monotonic(tmp_path):
    reported: list[float] = []
    model = FakeModel(["ca", "es", "en"])
    chunks = [(0.0, 2.0), (3.0, 9.0), (10.0, 12.0)]  # 2 s + 6 s + 2 s of speech

    provider(chunks, model).transcribe(pcm(tmp_path, 12), on_progress=reported.append)

    assert reported == sorted(reported) and reported[-1] == pytest.approx(1.0)
    detection, decoding = reported[:3], reported[3:]
    assert detection == pytest.approx([0.04, 0.16, 0.2])  # 20% share, by seconds
    assert decoding == pytest.approx([0.36, 0.84, 1.0])


def test_a_confident_short_catalan_turn_keeps_its_language_inside_a_spanish_meeting(tmp_path):
    # 117 s of Spanish and one 3 s Catalan turn (2.5% of the speech, under MIN_LANGUAGE_SHARE)
    # detected with probability 0.9: it is a real language of the meeting, not noise.
    model = FakeModel(["es", {"ca": 0.9, "es": 0.1}, "es"])
    chunks = [(0.0, 58.0), (59.0, 62.0), (63.0, 122.0)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 125))

    assert [s.language for s in segments] == ["es", "ca", "es"]
    assert model.transcribed == ["es", "ca", "es"]


def test_a_doubtful_minor_detection_is_still_reassigned(tmp_path):
    model = FakeModel(["es", {"ja": 0.3, "ca": 0.25, "es": 0.2}, "es"])
    chunks = [(0.0, 58.0), (59.0, 62.0), (63.0, 122.0)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 125))

    assert [s.language for s in segments] == ["es", "es", "es"]


def test_model_load_and_audio_read_failures_are_provider_errors(tmp_path):
    from app.asr import ProviderError

    def broken_loader():
        raise RuntimeError("download failed")

    loader_provider = FasterWhisperProvider(
        "large-v3", "cpu", "int8", model_loader=broken_loader, vad=lambda audio: [(0.0, 3.0)]
    )
    with pytest.raises(ProviderError) as error:
        loader_provider.transcribe(pcm(tmp_path, 3))
    assert error.value.code == "MODEL_LOAD_FAILED"

    with pytest.raises(ProviderError) as error:
        provider([(0.0, 3.0)], FakeModel([])).transcribe(tmp_path / "missing.pcm")
    assert error.value.code == "AUDIO_READ_FAILED"


def test_a_single_short_confident_detection_of_a_stray_language_is_noise(tmp_path):
    # Real recordings produced chunks like these: 1.8 s of "Romanian" at 0.96 inside Catalan.
    model = FakeModel(["ca", {"ro": 0.96, "ca": 0.02}, "ca"])
    chunks = [(0.0, 58.0), (59.0, 60.8), (62.0, 120.0)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 122))

    assert [s.language for s in segments] == ["ca", "ca", "ca"]


def test_a_minority_language_confident_across_several_short_chunks_is_kept(tmp_path):
    # Several 2 s turns of English at 0.75 add up to 8 s: a real language of the meeting.
    english = {"en": 0.75, "ca": 0.2}
    model = FakeModel(["ca", english, english, english, english, "ca"])
    chunks = [(0.0, 60.0), (61.0, 63.0), (64.0, 66.0), (67.0, 69.0), (70.0, 72.0), (73.0, 133.0)]

    segments = provider(chunks, model).transcribe(pcm(tmp_path, 135))

    assert [s.language for s in segments] == ["ca", "en", "en", "en", "en", "ca"]


def test_the_language_rule_boundaries():
    from app.asr_fasterwhisper import confident_minorities

    chunk = [(0.0, 3.0)]
    # Exactly at the sure-chunk boundary (>= 0.85 and >= 3 s) it counts; just below it does not.
    assert confident_minorities(chunk, [{"ca": 0.85, "es": 0.1}], {"es"}) == {"ca"}
    assert confident_minorities(chunk, [{"ca": 0.84, "es": 0.1}], {"es"}) == set()
    assert confident_minorities([(0.0, 2.9)], [{"ca": 0.99, "es": 0.01}], {"es"}) == set()
    # Below 0.7 never accumulates, however long.
    assert confident_minorities([(0.0, 30.0)], [{"ca": 0.69, "es": 0.3}], {"es"}) == set()
