"""SQLAlchemy models. Alembic owns the schema; nothing here emits DDL at runtime.

Field lists follow meeting_manager_project_spec.md §9.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
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


EMBEDDING_DIMENSION = 1024  # BGE-M3 (ADR 0001)


class MemoryIndexJob(Base):
    """Builds chunks, embeddings and evidence from one definitive transcript (spec §9)."""

    __tablename__ = "memory_index_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    source_brain_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # "chunks": text chunks and embeddings; "concepts": the concept graph projection of one
    # Brain extraction (ADR 0019).
    kind: Mapped[str] = mapped_column(String(20), default="chunks", server_default="chunks")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    projection_version: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(50))
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


class MemoryChunk(Base):
    """Consecutive definitive segments of one speaker turn; the embedding is a column (§9)."""

    __tablename__ = "memory_chunks"
    __table_args__ = (
        Index(
            "ix_memory_chunks_content_fts",
            text("to_tsvector('simple', content)"),
            postgresql_using="gin",
        ),
        Index(
            "ix_memory_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    index_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_index_jobs.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[str] = mapped_column(String(50))
    source_segment_ids: Mapped[list[str]] = mapped_column(JSON)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    transcript_sha256: Mapped[str] = mapped_column(String(64))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    track: Mapped[str] = mapped_column(String(20))
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryEvidence(Base):
    """Provenance chain: memory -> meeting -> transcript segment -> timestamp -> audio."""

    __tablename__ = "memory_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    index_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_index_jobs.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("memory_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Concept relationships arrive with the concept graph increment.
    relationship_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    segment_id: Mapped[str] = mapped_column(String(50))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    transcript_sha256: Mapped[str] = mapped_column(String(64))
    input_sha256: Mapped[str] = mapped_column(String(64))
    projection_version: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(50))


class MemoryQueryRun(Base):
    """One global question: queued -> retrieving -> synthesizing -> completed|empty|failed."""

    __tablename__ = "memory_query_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    top_k: Mapped[int] = mapped_column(Integer, default=8)
    max_results: Mapped[int] = mapped_column(Integer, default=50)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(10), default="es")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MemoryConcept(Base):
    """A concept shared across meetings; a manual tag is a concept of type "tag" (ADR 0013).

    Identity is the normalized name within `identity` ("tag" or "concept"): the type is only
    what is shown, the one the concept's mentions use most (ADR 0019).
    """

    __tablename__ = "memory_concepts"
    __table_args__ = (
        UniqueConstraint(
            "identity", "canonical_key", name="memory_concepts_identity_canonical_key_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    identity: Mapped[str] = mapped_column(String(10), server_default="concept")
    concept_type: Mapped[str] = mapped_column(String(30), index=True)
    canonical_name: Mapped[str] = mapped_column(String(200))
    canonical_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryConceptAlias(Base):
    __tablename__ = "memory_concept_aliases"
    __table_args__ = (UniqueConstraint("concept_id", "normalized_alias"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_concepts.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(200))
    normalized_alias: Mapped[str] = mapped_column(String(100), index=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MemoryConceptMention(Base):
    """A concept found in one meeting's definitive transcript, with its evidence."""

    __tablename__ = "memory_concept_mentions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_concepts.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    brain_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brain_jobs.id", ondelete="CASCADE")
    )
    mention: Mapped[str] = mapped_column(String(200))
    concept_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryConceptAssignment(Base):
    """A manual tag on a meeting: metadata with no transcript evidence (ADR 0013)."""

    __tablename__ = "memory_concept_assignments"
    __table_args__ = (UniqueConstraint("meeting_id", "concept_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_concepts.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(20), default="manual_user")
    source_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # ADR 0015
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryConceptRelationship(Base):
    """A typed link between two concepts, global across meetings."""

    __tablename__ = "memory_concept_relationships"
    __table_args__ = (
        UniqueConstraint("source_concept_id", "target_concept_id", "relationship_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_concepts.id", ondelete="CASCADE"), index=True
    )
    target_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_concepts.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(30))
    source_type: Mapped[str] = mapped_column(String(20), default="brain")  # brain | manual_user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryConceptRelationshipOccurrence(Base):
    """Where (which meeting, with which evidence) a relationship was observed."""

    __tablename__ = "memory_concept_relationship_occurrences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    relationship_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memory_concept_relationships.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    brain_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brain_jobs.id", ondelete="CASCADE")
    )
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
