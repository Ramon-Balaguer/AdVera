"""Definitive transcript document contract (ADR 0002, 0005, 0011, 0014).

The persisted definitive transcript is the only source of truth for intelligence.
Segments from each track are merged only by chronological order and keep their track.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.storage import Track

TRANSCRIPT_SCHEMA_VERSION = 1


class TranscriptSegment(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1)
    track: Track
    language: str | None = None
    speaker: str | None = None


class TrackProvenance(BaseModel):
    track: Track
    source_sha256: str
    provider: str
    model: str
    language: str | None = None
    fallback_reason: str | None = None
    segment_count: int


class TranscriptProvenance(BaseModel):
    job_id: str
    input_sha256: str
    pcm_format: str = "pcm_s16le;rate=16000;channels=1"
    tracks: list[TrackProvenance]


class TranscriptDocument(BaseModel):
    schema_version: int = TRANSCRIPT_SCHEMA_VERSION
    meeting_id: str
    status: Literal["definitive"] = "definitive"
    generated_at: datetime
    segments_sha256: str
    primary_language: list[str]
    provenance: TranscriptProvenance
    segments: list[TranscriptSegment]


def segments_sha256(segments: list[TranscriptSegment]) -> str:
    canonical = json.dumps(
        [segment.model_dump(mode="json") for segment in segments],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def merge_segments(per_track: dict[Track, list[TranscriptSegment]]) -> list[TranscriptSegment]:
    merged = [segment for segments in per_track.values() for segment in segments]
    return sorted(merged, key=lambda segment: (segment.start, segment.end, segment.track))


def distinct_languages(segments: list[TranscriptSegment]) -> list[str]:
    languages: list[str] = []
    for segment in segments:
        if segment.language and segment.language not in languages:
            languages.append(segment.language)
    return languages


def parse_definitive(document: dict[str, Any] | None) -> TranscriptDocument | None:
    """Return a valid definitive transcript, or None when absent, malformed or non-definitive."""
    if document is None:
        return None
    try:
        return TranscriptDocument.model_validate(document)
    except ValidationError:
        return None


def attendee_count(document: dict[str, Any] | None) -> int | None:
    """Distinct non-empty speakers of a valid definitive transcript (ADR 0011)."""
    transcript = parse_definitive(document)
    if transcript is None:
        return None
    return len({segment.speaker for segment in transcript.segments if segment.speaker})
