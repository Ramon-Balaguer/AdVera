"""Concept identity for the concept graph and manual tags (ADR 0013, ADR 0019).

Two mentions are the same concept only when their normalized names match: lower case, no
accents, collapsed spaces, no punctuation at the ends ("Pressupost", "pressupost " and
"PRESSUPOST." are one concept). Aliases given by Brain count the same way, by exact normalized
match. Nothing is merged by similarity: a doubtful candidate stays a separate concept
(concept-graph.md: "ambiguous concepts stay separate"). The same function serves manual tags
(`concept_type="tag"`) and Brain concepts, so both share one canonicalization.

The type is not part of the identity: the model calls the same subject a topic in one meeting
and a project in another, and the user wants one node for it. Tags keep their own namespace
(ADR 0013), so `identity` is "tag" or "concept"; the shown type of a concept is the one its
mentions use most (`refresh_types`).
"""

import re
import unicodedata
from collections.abc import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    MemoryConcept,
    MemoryConceptAlias,
    MemoryConceptMention,
    MemoryConceptRelationship,
    new_id,
)

MAX_KEY_LENGTH = 80
MAX_NAME_LENGTH = 200
_SPACES = re.compile(r"\s+")
_EDGE_PUNCTUATION = ".,;:!?¿¡\"'“”‘’()[]{}<>"


def canonical_key(text: str) -> str:
    """The normalized identity of a name; empty when nothing is left."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = _SPACES.sub(" ", plain.lower()).strip()
    return collapsed.strip(_EDGE_PUNCTUATION + " ")[:MAX_KEY_LENGTH].strip()


def display_name(text: str) -> str:
    """The name as shown: spaces collapsed, length bounded; case and accents are kept."""
    return _SPACES.sub(" ", text or "").strip()[:MAX_NAME_LENGTH]


def identity_of(concept_type: str) -> str:
    return "tag" if concept_type == "tag" else "concept"


async def _find(session: AsyncSession, concept_type: str, key: str) -> list[MemoryConcept]:
    """Concepts of the same identity (tag or concept) whose key or an alias equals `key`."""
    identity = identity_of(concept_type)
    by_key = (
        (
            await session.execute(
                select(MemoryConcept).where(
                    MemoryConcept.identity == identity, MemoryConcept.canonical_key == key
                )
            )
        )
        .scalars()
        .all()
    )
    by_alias = (
        (
            await session.execute(
                select(MemoryConcept)
                .join(MemoryConceptAlias, MemoryConceptAlias.concept_id == MemoryConcept.id)
                .where(
                    MemoryConcept.identity == identity,
                    MemoryConceptAlias.normalized_alias == key,
                )
            )
        )
        .scalars()
        .all()
    )
    return list({concept.id: concept for concept in [*by_key, *by_alias]}.values())


async def _add_alias(
    session: AsyncSession, concept: MemoryConcept, alias: str, source_sha256: str | None
) -> None:
    key = canonical_key(alias)
    if not key or key == concept.canonical_key:
        return
    await session.execute(
        insert(MemoryConceptAlias)
        .values(
            id=new_id(),
            concept_id=concept.id,
            alias=display_name(alias),
            normalized_alias=key,
            source_sha256=source_sha256,
        )
        .on_conflict_do_nothing(index_elements=["concept_id", "normalized_alias"])
    )


async def resolve_concept(
    session: AsyncSession,
    concept_type: str,
    name: str,
    *,
    aliases: Iterable[str] = (),
    source_sha256: str | None = None,
) -> MemoryConcept | None:
    """The concept for `name` (created when new); None when the name normalizes to nothing.

    Name first; if unknown, the aliases, but only when they all point at one concept. Several
    candidates mean the name is ambiguous, so a new concept is kept separate.
    """
    key = canonical_key(name)
    if not key:
        return None
    alias_list = [a for a in aliases if canonical_key(a)]
    found = await _find(session, concept_type, key)
    concept: MemoryConcept | None = found[0] if len(found) == 1 else None
    if not found:
        via_alias: dict[str, MemoryConcept] = {}
        for alias in alias_list:
            for candidate in await _find(session, concept_type, canonical_key(alias)):
                via_alias[candidate.id] = candidate
        if len(via_alias) == 1:
            concept = next(iter(via_alias.values()))
            await _add_alias(session, concept, name, source_sha256)
    if concept is None and len(found) > 1:
        # The same key exists under an alias of another concept: keep the exact-key concept.
        exact = [c for c in found if c.canonical_key == key]
        concept = exact[0] if len(exact) == 1 else None
    if concept is None:
        await session.execute(
            insert(MemoryConcept)
            .values(
                id=new_id(),
                identity=identity_of(concept_type),
                concept_type=concept_type,
                canonical_name=display_name(name),
                canonical_key=key,
            )
            .on_conflict_do_nothing(index_elements=["identity", "canonical_key"])
        )
        concept = (
            await session.execute(
                select(MemoryConcept).where(
                    MemoryConcept.identity == identity_of(concept_type),
                    MemoryConcept.canonical_key == key,
                )
            )
        ).scalar_one()
    for alias in alias_list:
        await _add_alias(session, concept, alias, source_sha256)
    return concept


async def refresh_types(session: AsyncSession, concept_ids: Iterable[str]) -> None:
    """Show each concept with the type its mentions use most (ties: alphabetical)."""
    for concept_id in sorted(set(concept_ids)):
        row = (
            await session.execute(
                select(MemoryConceptMention.concept_type)
                .where(
                    MemoryConceptMention.concept_id == concept_id,
                    MemoryConceptMention.concept_type.is_not(None),
                )
                .group_by(MemoryConceptMention.concept_type)
                .order_by(func.count().desc(), MemoryConceptMention.concept_type)
                .limit(1)
            )
        ).scalar()
        if row:
            await session.execute(
                update(MemoryConcept)
                .where(MemoryConcept.id == concept_id, MemoryConcept.identity == "concept")
                .values(concept_type=row)
            )


async def link_relationship(
    session: AsyncSession, source_id: str, target_id: str, relationship_type: str, source_type: str
) -> MemoryConceptRelationship:
    """The global relationship between two concepts, created once (upsert)."""
    await session.execute(
        insert(MemoryConceptRelationship)
        .values(
            id=new_id(),
            source_concept_id=source_id,
            target_concept_id=target_id,
            relationship_type=relationship_type,
            source_type=source_type,
        )
        .on_conflict_do_nothing(
            index_elements=["source_concept_id", "target_concept_id", "relationship_type"]
        )
    )
    return (
        await session.execute(
            select(MemoryConceptRelationship).where(
                MemoryConceptRelationship.source_concept_id == source_id,
                MemoryConceptRelationship.target_concept_id == target_id,
                MemoryConceptRelationship.relationship_type == relationship_type,
            )
        )
    ).scalar_one()
