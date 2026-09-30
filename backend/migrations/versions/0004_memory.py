"""Create memory_index_jobs, memory_chunks, memory_evidence, memory_query_runs (spec §9).

vector(1024) with an HNSW cosine index (ADR 0001) and a GIN full-text index on the chunk text
(`simple` configuration: no language-specific stemming for ca/es/en content).

Revision ID: 0004_memory
Revises: 0003_brain
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "0004_memory"
down_revision: str | None = "0003_brain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_query_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("error", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_query_runs_status"), "memory_query_runs", ["status"], unique=False
    )
    op.create_table(
        "memory_index_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("source_brain_job_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("projection_version", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("error", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        op.f("ix_memory_index_jobs_meeting_id"), "memory_index_jobs", ["meeting_id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_index_jobs_status"), "memory_index_jobs", ["status"], unique=False
    )
    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("index_job_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=50), nullable=False),
        sa.Column("source_segment_ids", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("transcript_sha256", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("speaker", sa.String(length=50), nullable=True),
        sa.Column("track", sa.String(length=20), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding_provider", sa.String(length=50), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column("embedding_model_version", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["index_job_id"], ["memory_index_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_chunks_content_fts",
        "memory_chunks",
        [sa.literal_column("to_tsvector('simple', content)")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_memory_chunks_embedding_hnsw",
        "memory_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_memory_chunks_index_job_id"), "memory_chunks", ["index_job_id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_chunks_meeting_id"), "memory_chunks", ["meeting_id"], unique=False
    )
    op.create_table(
        "memory_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("index_job_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("relationship_id", sa.String(length=36), nullable=True),
        sa.Column("segment_id", sa.String(length=50), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("transcript_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("projection_version", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["memory_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["index_job_id"], ["memory_index_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_evidence_chunk_id"), "memory_evidence", ["chunk_id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_evidence_index_job_id"), "memory_evidence", ["index_job_id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_evidence_meeting_id"), "memory_evidence", ["meeting_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_evidence_meeting_id"), table_name="memory_evidence")
    op.drop_index(op.f("ix_memory_evidence_index_job_id"), table_name="memory_evidence")
    op.drop_index(op.f("ix_memory_evidence_chunk_id"), table_name="memory_evidence")
    op.drop_table("memory_evidence")
    op.drop_index(op.f("ix_memory_chunks_meeting_id"), table_name="memory_chunks")
    op.drop_index(op.f("ix_memory_chunks_index_job_id"), table_name="memory_chunks")
    op.drop_index(
        "ix_memory_chunks_embedding_hnsw",
        table_name="memory_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(
        "ix_memory_chunks_content_fts", table_name="memory_chunks", postgresql_using="gin"
    )
    op.drop_table("memory_chunks")
    op.drop_index(op.f("ix_memory_index_jobs_status"), table_name="memory_index_jobs")
    op.drop_index(op.f("ix_memory_index_jobs_meeting_id"), table_name="memory_index_jobs")
    op.drop_table("memory_index_jobs")
    op.drop_index(op.f("ix_memory_query_runs_status"), table_name="memory_query_runs")
    op.drop_table("memory_query_runs")
