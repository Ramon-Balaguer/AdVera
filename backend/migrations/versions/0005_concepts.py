"""Create the concept graph and tag tables, and add memory_index_jobs.kind (spec §9, ADR 0013/0019).

Concepts are shared across meetings. A meeting reaches a concept by a mention (found in the
transcript, with evidence) or by an assignment (a manual tag, no evidence). Deleting a meeting
deletes its mentions, occurrences and assignments; concepts and relationships stay.

Revision ID: 0005_concepts
Revises: 0004_memory
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_concepts"
down_revision: str | None = "0004_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(length=36), nullable=False)


def upgrade() -> None:
    op.add_column(
        "memory_index_jobs",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="chunks"),
    )

    op.create_table(
        "memory_concepts",
        _id(),
        sa.Column("concept_type", sa.String(length=30), nullable=False),
        sa.Column("canonical_name", sa.String(length=200), nullable=False),
        sa.Column("canonical_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_type", "canonical_key"),
    )
    op.create_index(op.f("ix_memory_concepts_concept_type"), "memory_concepts", ["concept_type"])

    op.create_table(
        "memory_concept_aliases",
        _id(),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("normalized_alias", sa.String(length=100), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["concept_id"], ["memory_concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_id", "normalized_alias"),
    )
    op.create_index(
        op.f("ix_memory_concept_aliases_concept_id"), "memory_concept_aliases", ["concept_id"]
    )
    op.create_index(
        op.f("ix_memory_concept_aliases_normalized_alias"),
        "memory_concept_aliases",
        ["normalized_alias"],
    )

    op.create_table(
        "memory_concept_mentions",
        _id(),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("brain_job_id", sa.String(length=36), nullable=False),
        sa.Column("mention", sa.String(length=200), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["memory_concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brain_job_id"], ["brain_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_concept_mentions_concept_id"), "memory_concept_mentions", ["concept_id"]
    )
    op.create_index(
        op.f("ix_memory_concept_mentions_meeting_id"), "memory_concept_mentions", ["meeting_id"]
    )

    op.create_table(
        "memory_concept_assignments",
        _id(),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["memory_concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "concept_id"),
    )
    op.create_index(
        op.f("ix_memory_concept_assignments_concept_id"),
        "memory_concept_assignments",
        ["concept_id"],
    )
    op.create_index(
        op.f("ix_memory_concept_assignments_meeting_id"),
        "memory_concept_assignments",
        ["meeting_id"],
    )

    op.create_table(
        "memory_concept_relationships",
        _id(),
        sa.Column("source_concept_id", sa.String(length=36), nullable=False),
        sa.Column("target_concept_id", sa.String(length=36), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_concept_id"], ["memory_concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_concept_id"], ["memory_concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_concept_id", "target_concept_id", "relationship_type"),
    )
    op.create_index(
        op.f("ix_memory_concept_relationships_source_concept_id"),
        "memory_concept_relationships",
        ["source_concept_id"],
    )
    op.create_index(
        op.f("ix_memory_concept_relationships_target_concept_id"),
        "memory_concept_relationships",
        ["target_concept_id"],
    )

    op.create_table(
        "memory_concept_relationship_occurrences",
        _id(),
        sa.Column("relationship_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("brain_job_id", sa.String(length=36), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["relationship_id"], ["memory_concept_relationships.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brain_job_id"], ["brain_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_concept_relationship_occurrences_relationship_id"),
        "memory_concept_relationship_occurrences",
        ["relationship_id"],
    )
    op.create_index(
        op.f("ix_memory_concept_relationship_occurrences_meeting_id"),
        "memory_concept_relationship_occurrences",
        ["meeting_id"],
    )


def downgrade() -> None:
    op.drop_table("memory_concept_relationship_occurrences")
    op.drop_table("memory_concept_relationships")
    op.drop_table("memory_concept_assignments")
    op.drop_table("memory_concept_mentions")
    op.drop_table("memory_concept_aliases")
    op.drop_table("memory_concepts")
    op.drop_column("memory_index_jobs", "kind")
