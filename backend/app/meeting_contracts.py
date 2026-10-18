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
    # Manual tags given when the meeting is created (ADR 0013); same rules as adding them later.
    tags: list[str] = Field(default_factory=list, max_length=20)

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


BotStatus = Literal[
    "requested",
    "joining",
    "awaiting_admission",
    "needs_help",
    "active",
    "stopping",
    "ended",
    "ingesting",
    "completed",
    "failed",
]


class BotStartRequest(BaseModel):
    """Send the meeting bot to a Google Meet or Teams call (ADR 0026)."""

    meet_url: str = Field(max_length=2000)
    # Optional language hint for the provider's own transcription; AdVera autodetects.
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")


class BotSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    meeting_id: str
    provider: str
    platform: Literal["google_meet", "teams"]
    meet_url: str
    bot_name: str
    status: BotStatus
    # pending | sent | unsupported: whether the recording notice reached the call's chat.
    consent_notice: Literal["pending", "sent", "unsupported"]
    error: str | None
    active: bool = False
    joined_at: datetime | None
    left_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BotCapabilitiesResponse(BaseModel):
    configured: bool
    available: bool
    bot_name: str | None = None
    platforms: list[Literal["google_meet", "teams"]] = []


class ChatMessageResponse(BaseModel):
    """One chat message of the call; `id` is how Summary and Brain cite it (ADR 0027)."""

    id: str
    sender: str
    text: str
    sent_at: datetime | None
    offset_s: float | None
