"""Make a concept's identity its normalized name, not its type plus name (ADR 0019).

The model does not give the same concept the same type in every meeting ("documentación" came
out as a topic, a project and a technology), so identity by type split one subject into several
unconnected nodes. Now every non-tag concept with the same key is one concept; its shown type is
the one its mentions use most (kept per mention in `memory_concept_mentions.concept_type`).
Manual tags keep their own namespace (ADR 0013): `identity` is "tag" or "concept".

Existing duplicates are merged into the oldest concept: mentions and aliases move to it, and
each relationship is re-pointed (joined to an existing equal one, or dropped when it would
connect the concept to itself).

Revision ID: 0006_concept_identity
Revises: 0005_concepts
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_concept_identity"
down_revision: str | None = "0005_concepts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _merge(bind, keeper: str, loser: str) -> None:
    bind.execute(
        sa.text(
            """INSERT INTO memory_concept_aliases (id, concept_id, alias, normalized_alias,
                                                   source_sha256)
               SELECT gen_random_uuid()::text, :keeper, alias, normalized_alias, source_sha256
               FROM memory_concept_aliases WHERE concept_id = :loser
               ON CONFLICT (concept_id, normalized_alias) DO NOTHING"""
        ).bindparams(keeper=keeper, loser=loser)
    )
    bind.execute(
        sa.text("DELETE FROM memory_concept_aliases WHERE concept_id = :loser").bindparams(
            loser=loser
        )
    )
    bind.execute(
        sa.text(
            "UPDATE memory_concept_mentions SET concept_id = :keeper WHERE concept_id = :loser"
        ).bindparams(keeper=keeper, loser=loser)
    )
    relationships = bind.execute(
        sa.text(
            """SELECT id, source_concept_id, target_concept_id, relationship_type
               FROM memory_concept_relationships
               WHERE source_concept_id = :loser OR target_concept_id = :loser"""
        ).bindparams(loser=loser)
    ).all()
    for rel_id, source, target, rel_type in relationships:
        source = keeper if source == loser else source
        target = keeper if target == loser else target
        if source == target:
            bind.execute(
                sa.text("DELETE FROM memory_concept_relationships WHERE id = :id").bindparams(
                    id=rel_id
                )
            )
            continue
        existing = bind.execute(
            sa.text(
                """SELECT id FROM memory_concept_relationships
                   WHERE source_concept_id = :s AND target_concept_id = :t
                     AND relationship_type = :type AND id <> :id"""
            ).bindparams(s=source, t=target, type=rel_type, id=rel_id)
        ).scalar()
        if existing:
            bind.execute(
                sa.text(
                    """UPDATE memory_concept_relationship_occurrences
                       SET relationship_id = :existing WHERE relationship_id = :id"""
                ).bindparams(existing=existing, id=rel_id)
            )
            bind.execute(
                sa.text("DELETE FROM memory_concept_relationships WHERE id = :id").bindparams(
                    id=rel_id
                )
            )
        else:
            bind.execute(
                sa.text(
                    """UPDATE memory_concept_relationships
                       SET source_concept_id = :s, target_concept_id = :t WHERE id = :id"""
                ).bindparams(s=source, t=target, id=rel_id)
            )
    bind.execute(sa.text("DELETE FROM memory_concepts WHERE id = :loser").bindparams(loser=loser))


def upgrade() -> None:
    op.add_column(
        "memory_concepts",
        sa.Column("identity", sa.String(length=10), nullable=False, server_default="concept"),
    )
    op.execute("UPDATE memory_concepts SET identity = 'tag' WHERE concept_type = 'tag'")
    op.add_column(
        "memory_concept_mentions", sa.Column("concept_type", sa.String(length=30), nullable=True)
    )
    op.execute(
        """UPDATE memory_concept_mentions m SET concept_type = c.concept_type
           FROM memory_concepts c WHERE c.id = m.concept_id"""
    )

    bind = op.get_bind()
    groups = bind.execute(
        sa.text(
            """SELECT array_agg(id ORDER BY created_at, id) FROM memory_concepts
               GROUP BY identity, canonical_key HAVING COUNT(*) > 1"""
        )
    ).all()
    for (ids,) in groups:
        for loser in ids[1:]:
            _merge(bind, ids[0], loser)
    # The kept concept shows the type its mentions use most (ties: alphabetical).
    op.execute(
        """UPDATE memory_concepts c SET concept_type = t.concept_type FROM (
               SELECT DISTINCT ON (concept_id) concept_id, concept_type
               FROM memory_concept_mentions WHERE concept_type IS NOT NULL
               GROUP BY concept_id, concept_type
               ORDER BY concept_id, COUNT(*) DESC, concept_type) t
           WHERE c.id = t.concept_id AND c.identity = 'concept'"""
    )

    op.drop_constraint(
        "memory_concepts_concept_type_canonical_key_key", "memory_concepts", type_="unique"
    )
    op.create_unique_constraint(
        "memory_concepts_identity_canonical_key_key",
        "memory_concepts",
        ["identity", "canonical_key"],
    )


def downgrade() -> None:
    # Merged concepts stay merged; (type, key) is still unique because (identity, key) was.
    op.drop_constraint(
        "memory_concepts_identity_canonical_key_key", "memory_concepts", type_="unique"
    )
    op.create_unique_constraint(
        "memory_concepts_concept_type_canonical_key_key",
        "memory_concepts",
        ["concept_type", "canonical_key"],
    )
    op.drop_column("memory_concept_mentions", "concept_type")
    op.drop_column("memory_concepts", "identity")
