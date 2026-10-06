"""Unit tests that need no database, Redis or models."""

import pytest
from fastapi import HTTPException

from app.asr import AsrSegment, ProviderConfigurationError, build_engine
from app.audio_http import HEADER_SIZE, _iter_bytes, _parse_range, wav_header
from app.config import Settings
from app.media_import import MediaImportError, validate_media
from app.transcription_worker import normalize_segments
from app.transcripts import attendee_count, distinct_languages, merge_segments


def test_wav_header_describes_pcm16_mono_16k():
    header = wav_header(32_000)
    assert len(header) == HEADER_SIZE
    assert header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    assert int.from_bytes(header[24:28], "little") == 16_000
    assert int.from_bytes(header[40:44], "little") == 32_000


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("bytes=0-99", (0, 99)), ("bytes=100-", (100, 143)), ("bytes=-10", (134, 143))],
)
def test_parse_range(header, expected):
    assert _parse_range(header, 144) == expected


def test_parse_range_rejects_unsatisfiable():
    with pytest.raises(HTTPException) as error:
        _parse_range("bytes=500-", 144)
    assert error.value.status_code == 416


def test_iter_bytes_spans_header_and_pcm(tmp_path):
    pcm = tmp_path / "t.pcm"
    pcm.write_bytes(bytes(range(100)))
    header = wav_header(100)
    data = b"".join(_iter_bytes(header, pcm, 40, 49))
    assert data == header[40:44] + bytes(range(6))


def test_normalize_segments_assigns_track_ids_and_drops_blank_text():
    raw = [
        AsrSegment(2.0, 3.0, " second ", "es"),
        AsrSegment(0.0, 1.0, "first", "es", "SPEAKER_01"),
        AsrSegment(4.0, 3.5, "clamped", None),
        AsrSegment(5.0, 6.0, "   ", "es"),
    ]
    segments = normalize_segments("system", raw)
    assert [s.id for s in segments] == ["system-00000", "system-00001", "system-00002"]
    assert [s.text for s in segments] == ["first", "second", "clamped"]
    assert segments[2].end == segments[2].start
    assert all(s.track == "system" for s in segments)


def test_normalize_segments_drops_hallucinated_phrases_only_at_the_start_of_a_track():
    raw = [
        AsrSegment(0.0, 1.0, "Thanks for watching!", None),
        AsrSegment(1.0, 2.0, " Thank you for watching. ", None),
        AsrSegment(2.0, 4.0, "Hola, ¿me oyes?", "es"),
        AsrSegment(5.0, 6.0, "Thanks for watching!", "en"),
    ]
    segments = normalize_segments("system", raw)
    assert [s.text for s in segments] == ["Hola, ¿me oyes?", "Thanks for watching!"]
    assert [s.id for s in segments] == ["system-00000", "system-00001"]


def test_merge_keeps_track_provenance_in_chronological_order():
    mic = normalize_segments("microphone", [AsrSegment(1.0, 2.0, "b", "en")])
    system = normalize_segments("system", [AsrSegment(0.0, 1.0, "a", "ca")])
    merged = merge_segments({"microphone": mic, "system": system})
    assert [(s.track, s.text) for s in merged] == [("system", "a"), ("microphone", "b")]
    assert distinct_languages(merged) == ["ca", "en"]


def test_attendee_count_is_null_without_valid_definitive_transcript():
    assert attendee_count(None) is None
    assert attendee_count({"status": "provisional", "segments": []}) is None


def test_validate_media_allowlist():
    assert validate_media("clip.MP4", "video/mp4") == ".mp4"
    assert validate_media("voice.m4a", "application/octet-stream") == ".m4a"
    with pytest.raises(MediaImportError):
        validate_media("notes.pdf", "application/pdf")
    with pytest.raises(MediaImportError):
        validate_media("song.mp3", "text/plain")


def test_moss_is_not_available_in_this_increment():
    with pytest.raises(ProviderConfigurationError):
        build_engine("moss", "definitive", Settings())


def test_default_settings_never_force_moss_or_a_language():
    settings = Settings(_env_file=None)
    assert settings.asr_definitive_provider == "faster-whisper"
    assert settings.asr_fallback_provider == ""
    # ADR 0014: the ASR never receives a language. (The LLM output language is ADR 0009.)
    assert not any(
        "language" in name for name in Settings.model_fields if not name.startswith("llm_")
    )
