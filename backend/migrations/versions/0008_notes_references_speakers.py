"""Meeting notes, @references between meetings and speaker-to-person assignments.

Notes are a Markdown annex to the transcript, cited by block (ADR 0020); references are the
@links inside them, rebuilt on every save; speakers name a diarized label as a person concept
of the directory (ADR 0021). Everything belongs to its meeting and goes with it.

Revision ID: 0008_notes_speakers
Revises: 0007_prune_orphans
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_notes_speakers"
down_revision: str | None = "0007_prune_orphans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_notes",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id"),
    )
    op.create_table(
        "meeting_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_meeting_id", sa.String(length=36), nullable=False),
        sa.Column("target_meeting_id", sa.String(length=36), nullable=False),
        sa.Column("target_segment_id", sa.String(length=50), nullable=True),
        sa.Column("note_block_id", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["source_meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_meeting_references_source_meeting_id"),
        "meeting_references",
        ["source_meeting_id"],
    )
    op.create_index(
        op.f("ix_meeting_references_target_meeting_id"),
        "meeting_references",
        ["target_meeting_id"],
    )
    op.create_table(
        "meeting_speakers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("track", sa.String(length=20), nullable=False),
        sa.Column("speaker_label", sa.String(length=50), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["memory_concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "track", "speaker_label"),
    )
    op.create_index(op.f("ix_meeting_speakers_meeting_id"), "meeting_speakers", ["meeting_id"])
    op.create_index(op.f("ix_meeting_speakers_concept_id"), "meeting_speakers", ["concept_id"])


def downgrade() -> None:
    op.drop_table("meeting_speakers")
    op.drop_table("meeting_references")
    op.drop_table("meeting_notes")
