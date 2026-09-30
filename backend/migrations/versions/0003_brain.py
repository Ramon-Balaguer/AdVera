"""Create brain_jobs, llm_runs and brain_extractions (spec §9-11; ADR 0009).

Revision ID: 0003_brain
Revises: 0002_meetings_transcription_jobs
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_brain"
down_revision: str | None = "0002_meetings_transcription_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brain_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.String(36),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(30), nullable=False, server_default="EXTRACT_BRAIN"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="es"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("error", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_brain_jobs_meeting_id", "brain_jobs", ["meeting_id"])
    op.create_index("ix_brain_jobs_status", "brain_jobs", ["status"])
    op.create_table(
        "llm_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("brain_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_llm_runs_job_id", "llm_runs", ["job_id"])
    op.create_table(
        "brain_extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.String(36),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("brain_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "llm_run_id",
            sa.String(36),
            sa.ForeignKey("llm_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_brain_extractions_meeting_id", "brain_extractions", ["meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_brain_extractions_meeting_id", table_name="brain_extractions")
    op.drop_table("brain_extractions")
    op.drop_index("ix_llm_runs_job_id", table_name="llm_runs")
    op.drop_table("llm_runs")
    op.drop_index("ix_brain_jobs_status", table_name="brain_jobs")
    op.drop_index("ix_brain_jobs_meeting_id", table_name="brain_jobs")
    op.drop_table("brain_jobs")
