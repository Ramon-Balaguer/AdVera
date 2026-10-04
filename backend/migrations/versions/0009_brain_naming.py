"""Rename the data model to the new product names (operator decision, 2026-10-04).

What was called Brain (the per-meeting extraction) is now Summary, and what was called Memory
(the index, search, concept graph and timeline) is now Brain. Tables, columns, constraints and
indexes carry the names, so they are all renamed here from the catalog, in one pass for each
kind of object; the rows are not touched, except the stored error codes of the summary jobs
(`BRAIN_*` became `SUMMARY_*`). The names of the stored prompt and projection versions
(`brain-extraction-v10`, `memory-chunks-v1`, `memory-concepts-v1`) stay: they only identify what
produced a row, and changing them would make every result look out of date.

Revision ID: 0009_brain_naming
Revises: 0008_notes_speakers
Create Date: 2026-10-04
"""

import re
from collections.abc import Callable, Sequence

from alembic import op

revision: str = "0009_brain_naming"
down_revision: str | None = "0008_notes_speakers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Each name is rewritten once with both words at the same time (brain->summary, memory->brain),
# never one after the other, which would turn the old memory names into summary names.
UP = {"brain": "summary", "memory": "brain"}
DOWN = {"brain": "memory", "summary": "brain"}
FIRST_UP = "brain_"
FIRST_DOWN = "brain_"


def _rewriter(mapping: dict[str, str]) -> Callable[[str], str]:
    pattern = re.compile(r"(?<![a-z])(" + "|".join(mapping) + r")_")
    return lambda name: pattern.sub(lambda match: mapping[match.group(1)] + "_", name)


def _ordered(names: list[str], first: str) -> list[str]:
    # Names that start from the word that is going to be reused go first, so that a rename
    # never lands on a name that is still taken.
    return sorted(names, key=lambda name: (first not in name, name))


def _rename(mapping: dict[str, str], first: str) -> None:
    rewrite = _rewriter(mapping)
    words = "|".join(mapping)
    like = f"~ '(^|[^a-z])({words})_'"
    connection = op.get_bind()

    def rows(sql: str) -> list[tuple]:
        return [tuple(row) for row in connection.exec_driver_sql(sql).fetchall()]

    tables = [
        name
        for (name,) in rows(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename " + like
        )
    ]
    for name in _ordered(tables, first):
        op.execute(f'ALTER TABLE "{name}" RENAME TO "{rewrite(name)}"')

    columns = rows(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name " + like
    )
    for table, column in sorted(columns, key=lambda item: (first not in item[1], item)):
        op.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{column}" TO "{rewrite(column)}"')

    constraints = rows(
        "SELECT c.conname, t.relname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE t.relnamespace = 'public'::regnamespace AND c.conname " + like
    )
    for name, table in sorted(constraints, key=lambda item: (first not in item[0], item)):
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{name}" TO "{rewrite(name)}"')

    # Only the indexes that are not behind a constraint: those were renamed with it above.
    indexes = [
        name
        for (name,) in rows(
            "SELECT c.relname FROM pg_class c JOIN pg_index x ON x.indexrelid = c.oid "
            "WHERE c.relnamespace = 'public'::regnamespace AND c.relname " + like + " "
            "AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = c.oid)"
        )
    ]
    for name in _ordered(indexes, first):
        op.execute(f'ALTER INDEX "{name}" RENAME TO "{rewrite(name)}"')


def upgrade() -> None:
    _rename(UP, FIRST_UP)
    for table in ("summary_jobs", "llm_runs"):
        op.execute(
            f"UPDATE {table} SET error = regexp_replace(error, '^BRAIN_', 'SUMMARY_') "
            r"WHERE error LIKE 'BRAIN\_%'"
        )


def downgrade() -> None:
    for table in ("summary_jobs", "llm_runs"):
        op.execute(
            f"UPDATE {table} SET error = regexp_replace(error, '^SUMMARY_', 'BRAIN_') "
            r"WHERE error LIKE 'SUMMARY\_%'"
        )
    _rename(DOWN, FIRST_DOWN)
