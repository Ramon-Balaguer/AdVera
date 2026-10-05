"""Facts of a meeting (decisions, actions, risks, questions, topics) as Brain data (ADR 0024).

They were only inside the JSON of each Summary. The table is derived: the projection replaces
the rows of a meeting as a whole, and they go with the meeting. Existing meetings are filled
with `python -m app.brain_backfill --reproject`, which does not call the model.

Revision ID: 0010_brain_facts
Revises: 0009_brain_naming
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_brain_facts"
down_revision: str | None = "0009_brain_naming"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brain_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("summary_job_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=True),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("due_date", sa.String(length=100), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["summary_job_id"], ["summary_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_brain_facts_meeting_id", "brain_facts", ["meeting_id"])
    op.create_index("ix_brain_facts_kind_state", "brain_facts", ["kind", "state"])


def downgrade() -> None:
    op.drop_index("ix_brain_facts_kind_state", table_name="brain_facts")
    op.drop_index("ix_brain_facts_meeting_id", table_name="brain_facts")
    op.drop_table("brain_facts")
