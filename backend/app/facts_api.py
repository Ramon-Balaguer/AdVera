"""Facts across meetings: decisions, actions, risks, open questions and topics (ADR 0024).

Read only. The rows are projected from each meeting's Summary (`brain_facts`), so the same
filters as the rest of the Brain apply: meeting, any of several tags, and a date range over
the meeting's date. Every fact keeps the citations that open the meeting at the cited second.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.concepts import canonical_key
from app.database import get_session
from app.models import BrainConcept, BrainConceptAssignment, BrainFact, Meeting

router = APIRouter(tags=["brain"])
Session = Annotated[AsyncSession, Depends(get_session)]

Kind = Literal["decision", "action", "risk", "question", "topic"]
KINDS: tuple[Kind, ...] = ("decision", "action", "risk", "question", "topic")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Citation(BaseModel):
    segment_id: str
    start: float | None = None
    track: str | None = None
    text: str | None = None


class FactView(BaseModel):
    id: str
    kind: Kind
    text: str
    state: str | None = None
    owner: str | None = None
    due_date: str | None = None
    evidence: list[Citation]
    meeting_id: str
    meeting_title: str
    meeting_date: datetime


class FactsResponse(BaseModel):
    total: int
    counts: dict[str, int]  # per kind, with every filter except the kind and the state
    facts: list[FactView]


def citations(raw: list | None) -> list[Citation]:
    return [
        Citation(**item) for item in raw or [] if isinstance(item, dict) and item.get("segment_id")
    ]


def like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def meeting_date():
    return func.coalesce(Meeting.started_at, Meeting.created_at)


def scope_filters(
    meeting_id: str | None,
    tags: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None,
    owner: str | None,
) -> list:
    """The conditions shared by the list and the counts."""
    clauses: list = []
    if meeting_id:
        clauses.append(BrainFact.meeting_id == meeting_id)
    if tags:
        keys = [canonical_key(tag) for tag in tags if canonical_key(tag)]
        clauses.append(
            BrainFact.meeting_id.in_(
                select(BrainConceptAssignment.meeting_id)
                .join(BrainConcept, BrainConcept.id == BrainConceptAssignment.concept_id)
                .where(BrainConcept.identity == "tag", BrainConcept.canonical_key.in_(keys))
            )
        )
    if date_from:
        clauses.append(meeting_date() >= date_from)
    if date_to:
        clauses.append(meeting_date() <= date_to)
    if q and q.strip():
        clauses.append(BrainFact.text.ilike(like(q.strip()), escape="\\"))
    if owner and owner.strip():
        clauses.append(BrainFact.owner.ilike(like(owner.strip()), escape="\\"))
    return clauses


@router.get("/api/brain/facts", response_model=FactsResponse)
async def list_facts(
    session: Session,
    kind: Annotated[Kind | None, Query()] = None,
    state: Annotated[str | None, Query(max_length=20)] = None,
    owner: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    meeting_id: Annotated[str | None, Query(max_length=36)] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FactsResponse:
    shared = scope_filters(meeting_id, tag or [], date_from, date_to, q, owner)
    counts = dict(
        (
            await session.execute(
                select(BrainFact.kind, func.count())
                .join(Meeting, Meeting.id == BrainFact.meeting_id)
                .where(*shared)
                .group_by(BrainFact.kind)
            )
        ).all()
    )
    selected = list(shared)
    if kind:
        selected.append(BrainFact.kind == kind)
    if state:
        selected.append(BrainFact.state == state)
    base = (
        select(BrainFact, Meeting.title, meeting_date().label("date"))
        .join(Meeting, Meeting.id == BrainFact.meeting_id)
        .where(*selected)
    )
    total = (
        await session.execute(select(func.count()).select_from(base.order_by(None).subquery()))
    ).scalar_one()
    order = case({name: index for index, name in enumerate(KINDS)}, value=BrainFact.kind)
    rows = (
        await session.execute(
            base.order_by(meeting_date().desc(), Meeting.id, order, BrainFact.position)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return FactsResponse(
        total=total,
        counts={name: counts.get(name, 0) for name in KINDS},
        facts=[
            FactView(
                id=fact.id,
                kind=fact.kind,
                text=fact.text,
                state=fact.state,
                owner=fact.owner,
                due_date=fact.due_date,
                evidence=citations(fact.evidence),
                meeting_id=fact.meeting_id,
                meeting_title=title,
                meeting_date=date,
            )
            for fact, title, date in rows
        ],
    )
