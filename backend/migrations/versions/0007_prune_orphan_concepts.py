"""Delete concepts that no meeting mentions or tags (operator decision, 2026-10-01).

From now on a concept left without meetings is deleted when that happens; this removes the
ones that were left behind before (deleted meetings, re-extractions). Their aliases and
relationships go by cascade. Data only: there is nothing to restore on downgrade.

Revision ID: 0007_prune_orphans
Revises: 0006_concept_identity
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_prune_orphans"
down_revision: str | None = "0006_concept_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """DELETE FROM memory_concepts c
           WHERE NOT EXISTS (SELECT 1 FROM memory_concept_mentions m WHERE m.concept_id = c.id)
             AND NOT EXISTS (
                 SELECT 1 FROM memory_concept_assignments a WHERE a.concept_id = c.id)"""
    )


def downgrade() -> None:
    pass  # deleted orphans are not restored
