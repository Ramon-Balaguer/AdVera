"""SQLAlchemy models. Alembic owns the schema; nothing here emits DDL at runtime.

Field lists follow meeting_manager_project_spec.md §9.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Untyped text in the database; the enum is enforced by meeting_contracts (spec §9).
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    # Distinct detected segment languages, populated after definitive transcription (ADR 0014).
    primary_language: Mapped[list[str]] = mapped_column(JSON, default=list)
    # No stable principal while authentication is deferred (ADR 0015).
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    # Orthogonal to status: the internal phase while the job runs (spec §9, §17).
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    track: Mapped[str | None] = mapped_column(String(20), nullable=True)
    processed_tracks: Mapped[int] = mapped_column(Integer, default=0)
    total_tracks: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # A stable, sanitized error code; never raw provider text.
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BrainJob(Base):
    """Durable Brain extraction job (spec §9). ADR 0009: LLM settings are snapshotted here."""

    __tablename__ = "brain_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(30), default="EXTRACT_BRAIN")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    # Hash of the definitive transcript segments: the Brain input identity.
    input_sha256: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    prompt_version: Mapped[str] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(10), default="es")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class LLMRun(Base):
    """One provider call. Only the final structured output is kept, never reasoning (§3.4)."""

    __tablename__ = "llm_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brain_jobs.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50))
    input_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrainExtraction(Base):
    """Validated Brain result as one schema-checked JSON document (spec §9, §11)."""

    __tablename__ = "brain_extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brain_jobs.id", ondelete="CASCADE"), unique=True
    )
    llm_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("llm_runs.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(20))
    input_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
