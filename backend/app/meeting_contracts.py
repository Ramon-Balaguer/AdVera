"""Meeting REST contracts. The status enum lives here, not in the database (spec §9)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MeetingStatus = Literal["scheduled", "recording", "processing", "ready", "failed", "archived"]
JobStatus = Literal["queued", "running", "completed", "failed"]
JobStage = Literal[
    "transcribing", "finalizing", "fallback", "completed", "retrying", "requeued", "failed"
]


def _clean_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("title must not be blank")
    return value


class MeetingCreate(BaseModel):
    title: str = Field(max_length=200)
    description: str | None = None

    _title = field_validator("title")(_clean_title)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _clean_title(value)


class TagRef(BaseModel):
    """A manual tag on a meeting (ADR 0013)."""

    assignment_id: str
    concept_id: str
    label: str
    created_at: datetime | None = None


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    status: MeetingStatus
    started_at: datetime | None
    ended_at: datetime | None
    duration: float | None
    primary_language: list[str]
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    # Derived from the definitive transcript; null when it is absent or invalid (ADR 0011).
    attendee_count: int | None = None
    tracks: list[Literal["microphone", "system"]] = []
    tags: list[TagRef] = []


class TranscriptionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str = Field(validation_alias="id")
    meeting_id: str
    status: JobStatus
    stage: JobStage | None
    progress: float
    track: str | None
    processed_tracks: int
    total_tracks: int
    attempts: int
    max_attempts: int
    provider: str
    model: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class ImportResponse(BaseModel):
    meeting: MeetingResponse
    transcription: TranscriptionStatusResponse
