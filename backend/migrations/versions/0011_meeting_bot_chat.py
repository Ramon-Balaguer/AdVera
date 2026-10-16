"""Meeting bot sessions (Vexa, ADR 0026) and the meeting chat annex (ADR 0027).

`meeting_bot_sessions` records each bot sent to a call: the provider's meeting id, the URL,
the lifecycle status, and the ingestion lease once the bot has left. At most one session per
meeting is live at a time (partial unique index). `meeting_chat_messages` keeps the chat of
the call, a citable annex like the notes; both go with the meeting.

Revision ID: 0011_meeting_bot_chat
Revises: 0010_brain_facts
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_meeting_bot_chat"
down_revision: str | None = "0010_brain_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TERMINAL = "status NOT IN ('completed', 'failed')"


def upgrade() -> None:
    op.create_table(
        "meeting_bot_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("native_meeting_id", sa.String(length=255), nullable=False),
        sa.Column("vexa_meeting_id", sa.String(length=50), nullable=True),
        sa.Column("meet_url", sa.String(length=500), nullable=False),
        sa.Column("bot_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_status", sa.String(length=30), nullable=True),
        sa.Column("consent_notice", sa.String(length=20), nullable=False),
        sa.Column("error", sa.String(length=50), nullable=True),
        sa.Column("speaker_timeline", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_meeting_bot_sessions_meeting_id", "meeting_bot_sessions", ["meeting_id"])
    op.create_index("ix_meeting_bot_sessions_status", "meeting_bot_sessions", ["status"])
    op.create_index(
        "uq_meeting_bot_sessions_live",
        "meeting_bot_sessions",
        ["meeting_id"],
        unique=True,
        postgresql_where=sa.text(TERMINAL),
    )
    op.create_table(
        "meeting_chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sender", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offset_s", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_meeting_chat_messages_meeting_id", "meeting_chat_messages", ["meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_meeting_chat_messages_meeting_id", table_name="meeting_chat_messages")
    op.drop_table("meeting_chat_messages")
    op.drop_index("uq_meeting_bot_sessions_live", table_name="meeting_bot_sessions")
    op.drop_index("ix_meeting_bot_sessions_status", table_name="meeting_bot_sessions")
    op.drop_index("ix_meeting_bot_sessions_meeting_id", table_name="meeting_bot_sessions")
    op.drop_table("meeting_bot_sessions")
