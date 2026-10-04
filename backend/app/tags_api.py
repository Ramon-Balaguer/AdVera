"""Manual meeting tags (ADR 0013; spec §20).

A tag is a shared concept of type "tag" assigned to a meeting. Assigning is idempotent: the
same label in any case or spacing reuses the concept and the assignment. Removing a tag
deletes only that meeting's assignment; the shared concept stays. Tags are metadata typed by
the user and never count as transcript evidence. This router is included before the meetings
router so `/api/meetings/tags` is not taken for a meeting id.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.concepts import (
    canonical_key,
    display_name,
    link_relationship,
    lock_concepts,
    prune_orphans,
    resolve_concept,
)
from app.database import get_session
from app.meeting_contracts import TagRef
from app.models import BrainConcept, BrainConceptAssignment, Meeting, new_id

logger = logging.getLogger("advera.tags")

router = APIRouter(prefix="/api/meetings", tags=["tags"])

Session = Annotated[AsyncSession, Depends(get_session)]

MAX_TAG_LENGTH = 60
MAX_TAGS_PER_MEETING = 20
SUGGESTION_LIMIT = 10


class TagSummary(BaseModel):
    """A tag in use, with how many meetings carry it."""

    concept_id: str
    label: str
    meetings: int


class TagCreate(BaseModel):
    label: str = Field(max_length=500)


async def _meeting(session: AsyncSession, meeting_id: str) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    return meeting


async def tags_for(session: AsyncSession, meeting_ids: list[str]) -> dict[str, list[TagRef]]:
    """The tags of several meetings in one query, oldest first (for list and detail views)."""
    if not meeting_ids:
        return {}
    rows = (
        await session.execute(
            select(BrainConceptAssignment)
            .where(BrainConceptAssignment.meeting_id.in_(meeting_ids))
            .order_by(BrainConceptAssignment.created_at, BrainConceptAssignment.id)
        )
    ).scalars()
    result: dict[str, list[TagRef]] = {meeting_id: [] for meeting_id in meeting_ids}
    for row in rows:
        result[row.meeting_id].append(
            TagRef(
                assignment_id=row.id,
                concept_id=row.concept_id,
                label=row.label,
                created_at=row.created_at,
            )
        )
    return result


@router.get("/tags", response_model=list[TagSummary])
async def list_tags(session: Session) -> list[TagSummary]:
    count = func.count(BrainConceptAssignment.id)
    rows = (
        await session.execute(
            select(BrainConcept.id, BrainConcept.canonical_name, count)
            .join(BrainConceptAssignment, BrainConceptAssignment.concept_id == BrainConcept.id)
            .where(BrainConcept.concept_type == "tag")
            .group_by(BrainConcept.id, BrainConcept.canonical_name)
            .order_by(count.desc(), BrainConcept.canonical_name)
        )
    ).all()
    return [TagSummary(concept_id=i, label=name, meetings=n) for i, name, n in rows]


@router.get("/{meeting_id}/tags", response_model=list[TagRef])
async def meeting_tags(meeting_id: str, session: Session) -> list[TagRef]:
    await _meeting(session, meeting_id)
    return (await tags_for(session, [meeting_id]))[meeting_id]


@router.get("/{meeting_id}/tags/suggestions", response_model=list[TagSummary])
async def tag_suggestions(meeting_id: str, session: Session, q: str = "") -> list[TagSummary]:
    """Existing tags this meeting does not have yet, prefix matches first, most used first."""
    await _meeting(session, meeting_id)
    key = canonical_key(q[:200])
    count = func.count(BrainConceptAssignment.id)
    query = (
        select(BrainConcept.id, BrainConcept.canonical_name, BrainConcept.canonical_key, count)
        .join(BrainConceptAssignment, BrainConceptAssignment.concept_id == BrainConcept.id)
        .where(
            BrainConcept.concept_type == "tag",
            BrainConcept.id.not_in(
                select(BrainConceptAssignment.concept_id).where(
                    BrainConceptAssignment.meeting_id == meeting_id
                )
            ),
        )
        .group_by(BrainConcept.id, BrainConcept.canonical_name, BrainConcept.canonical_key)
    )
    if key:
        escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(BrainConcept.canonical_key.like(f"%{escaped}%", escape="\\"))
    rows = (await session.execute(query)).all()
    rows.sort(key=lambda r: (not r[2].startswith(key), -r[3], r[2]))
    return [TagSummary(concept_id=i, label=name, meetings=n) for i, name, _k, n in rows][
        :SUGGESTION_LIMIT
    ]


def clean_label(raw: str) -> str:
    """The label as stored; 422 INVALID_TAG when empty or too long."""
    label = display_name(raw)
    if not canonical_key(label) or len(label) > MAX_TAG_LENGTH:
        raise HTTPException(status_code=422, detail="INVALID_TAG")
    return label


async def assign_tag(session: AsyncSession, meeting_id: str, raw_label: str) -> tuple[TagRef, bool]:
    """Assign a tag to a meeting (ADR 0013) and say whether it is new. The caller commits.

    Idempotent across case, accents and spacing; at most MAX_TAGS_PER_MEETING per meeting.
    """
    label = clean_label(raw_label)
    key = canonical_key(label)
    await lock_concepts(session)
    concept = await resolve_concept(session, "tag", label)
    assert concept is not None  # the key is non-empty

    def ref(row: BrainConceptAssignment) -> TagRef:
        return TagRef(
            assignment_id=row.id, concept_id=concept.id, label=row.label, created_at=row.created_at
        )

    async def current() -> BrainConceptAssignment | None:
        return (
            await session.execute(
                select(BrainConceptAssignment).where(
                    BrainConceptAssignment.meeting_id == meeting_id,
                    BrainConceptAssignment.concept_id == concept.id,
                )
            )
        ).scalar_one_or_none()

    existing = await current()
    if existing is not None:
        return ref(existing), False

    # Serialize tag changes of one meeting: count-then-insert must not race past the limit.
    await session.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
    total = (
        await session.execute(
            select(func.count(BrainConceptAssignment.id)).where(
                BrainConceptAssignment.meeting_id == meeting_id
            )
        )
    ).scalar_one()
    if total >= MAX_TAGS_PER_MEETING:
        raise HTTPException(status_code=409, detail="TOO_MANY_TAGS")

    inserted = (
        await session.execute(
            insert(BrainConceptAssignment)
            .values(
                id=new_id(),
                concept_id=concept.id,
                meeting_id=meeting_id,
                label=label,
                source_type="manual_user",
                source_user_id=None,  # ADR 0015: no users
            )
            .on_conflict_do_nothing(index_elements=["meeting_id", "concept_id"])
            .returning(BrainConceptAssignment.id)
        )
    ).scalar_one_or_none()
    if inserted is None:  # a concurrent request assigned the same tag first
        return ref(await current()), False  # type: ignore[arg-type]

    # Best effort (ADR 0013): a tag named exactly like an existing concept is related to it.
    try:
        async with session.begin_nested():
            others = (
                (
                    await session.execute(
                        select(BrainConcept).where(
                            BrainConcept.canonical_key == key, BrainConcept.identity == "concept"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for other in others:
                await link_relationship(session, concept.id, other.id, "related_to", "manual_user")
    except Exception as error:  # the assignment must not fail because of this
        logger.warning("tag relationship skipped: %s", type(error).__name__)
    return ref(await current()), True  # type: ignore[arg-type]


@router.post("/{meeting_id}/tags", response_model=TagRef, status_code=201)
async def add_tag(meeting_id: str, body: TagCreate, session: Session) -> TagRef:
    from fastapi.responses import JSONResponse

    await _meeting(session, meeting_id)
    tag, created = await assign_tag(session, meeting_id, body.label)
    await session.commit()
    if not created:
        return JSONResponse(tag.model_dump(mode="json"), status_code=200)  # type: ignore[return-value]
    return tag


@router.delete("/{meeting_id}/tags/{assignment_id}", status_code=204)
async def remove_tag(meeting_id: str, assignment_id: str, session: Session) -> None:
    """Removes this meeting's assignment only; the tag stays while another meeting has it."""
    await _meeting(session, meeting_id)
    await lock_concepts(session)
    assignment = await session.get(BrainConceptAssignment, assignment_id)
    if assignment is None or assignment.meeting_id != meeting_id:
        raise HTTPException(status_code=404, detail="TAG_NOT_FOUND")
    await session.delete(assignment)
    await session.flush()
    await prune_orphans(session)
    await session.commit()
