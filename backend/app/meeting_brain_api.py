"""Everything the Brain holds about one meeting (ADR 0024). Read only.

The index state, the facts (decisions, actions, risks, questions and topics), the concepts and
relationships found in it, its tags and the people named as its speakers. The Summary stays its
own endpoint: it is the result of one job, this is the projection of it into the Brain.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input
from app.brain_jobs import CONCEPT_PROJECTION_VERSION
from app.database import get_session
from app.facts_api import KINDS, FactView, citations, meeting_date
from app.models import (
    BrainChunk,
    BrainConcept,
    BrainConceptAssignment,
    BrainConceptMention,
    BrainConceptRelationship,
    BrainConceptRelationshipOccurrence,
    BrainFact,
    BrainIndexJob,
    Meeting,
    MeetingSpeaker,
)

router = APIRouter(prefix="/api/meetings", tags=["brain"])
Session = Annotated[AsyncSession, Depends(get_session)]

JobState = Literal["none", "queued", "running", "completed", "failed"]


class JobStatus(BaseModel):
    state: JobState
    error: str | None = None
    completed_at: datetime | None = None
    # Whether the last completed job read what the meeting holds now; None when it cannot be
    # told (no definitive transcript).
    up_to_date: bool | None = None


class IndexStatus(JobStatus):
    chunks: int
    embedded: int


class ConceptItem(BaseModel):
    id: str
    name: str
    type: str
    mentions: int


class RelationshipItem(BaseModel):
    source_id: str
    source: str
    target_id: str
    target: str
    type: str
    evidence: int


class PersonItem(BaseModel):
    id: str
    name: str
    speakers: list[str]


class MeetingBrain(BaseModel):
    meeting_id: str
    title: str
    date: datetime
    index: IndexStatus
    projection: JobStatus
    facts: dict[str, list[FactView]]
    concepts: list[ConceptItem]
    relationships: list[RelationshipItem]
    tags: list[str]
    people: list[PersonItem]


async def _job_status(
    session: AsyncSession, meeting_id: str, kind: str, expected_sha: str | None, version: str | None
) -> JobStatus:
    jobs = (
        (
            await session.execute(
                select(BrainIndexJob)
                .where(BrainIndexJob.meeting_id == meeting_id, BrainIndexJob.kind == kind)
                .order_by(BrainIndexJob.created_at.desc(), BrainIndexJob.id.desc())
            )
        )
        .scalars()
        .all()
    )
    if not jobs:
        return JobStatus(state="none")
    last = jobs[0]
    state: JobState = (
        last.status if last.status in ("queued", "completed", "failed") else "running"  # type: ignore[assignment]
    )
    done = next((job for job in jobs if job.status == "completed"), None)
    current = None
    if expected_sha is not None:
        current = bool(
            done
            and done.input_sha256 == expected_sha
            and (version is None or done.projection_version == version)
        )
    return JobStatus(
        state=state,
        error=last.error if last.status == "failed" else None,
        completed_at=done.completed_at if done else None,
        up_to_date=current,
    )


@router.get("/{meeting_id}/brain", response_model=MeetingBrain)
async def get_meeting_brain(meeting_id: str, request: Request, session: Session) -> MeetingBrain:
    row = (
        await session.execute(select(Meeting.title, meeting_date()).where(Meeting.id == meeting_id))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    title, date = row

    analysis = await analysis_input.load(
        session, request.app.state.storage, meeting_id, expand=False
    )
    chunks = (
        await session.execute(
            select(func.count(), func.count(BrainChunk.embedding)).where(
                BrainChunk.meeting_id == meeting_id
            )
        )
    ).one()
    index = await _job_status(
        session, meeting_id, "chunks", analysis.brain_sha256 if analysis else None, None
    )
    projection = await _job_status(
        session,
        meeting_id,
        "concepts",
        analysis.summary_sha256 if analysis else None,
        CONCEPT_PROJECTION_VERSION,
    )

    grouped: dict[str, list[FactView]] = {kind: [] for kind in KINDS}
    for fact in (
        (
            await session.execute(
                select(BrainFact)
                .where(BrainFact.meeting_id == meeting_id)
                .order_by(BrainFact.position)
            )
        )
        .scalars()
        .all()
    ):
        grouped[fact.kind].append(
            FactView(
                id=fact.id,
                kind=fact.kind,
                text=fact.text,
                state=fact.state,
                owner=fact.owner,
                due_date=fact.due_date,
                evidence=citations(fact.evidence),
                meeting_id=meeting_id,
                meeting_title=title,
                meeting_date=date,
            )
        )

    concepts = [
        ConceptItem(id=cid, name=name, type=mention_type or ctype, mentions=len(evidence or []))
        for cid, name, ctype, mention_type, evidence in (
            await session.execute(
                select(
                    BrainConcept.id,
                    BrainConcept.canonical_name,
                    BrainConcept.concept_type,
                    BrainConceptMention.concept_type,
                    BrainConceptMention.evidence,
                )
                .join(BrainConceptMention, BrainConceptMention.concept_id == BrainConcept.id)
                .where(BrainConceptMention.meeting_id == meeting_id)
                .order_by(BrainConcept.canonical_name)
            )
        ).all()
    ]
    concepts.sort(key=lambda item: (-item.mentions, item.name.lower()))

    source, target = BrainConcept.__table__.alias("s"), BrainConcept.__table__.alias("t")
    relationships = [
        RelationshipItem(
            source_id=sid,
            source=sname,
            target_id=tid,
            target=tname,
            type=kind,
            evidence=len(ev or []),
        )
        for sid, sname, tid, tname, kind, ev in (
            await session.execute(
                select(
                    source.c.id,
                    source.c.canonical_name,
                    target.c.id,
                    target.c.canonical_name,
                    BrainConceptRelationship.relationship_type,
                    BrainConceptRelationshipOccurrence.evidence,
                )
                .join(
                    BrainConceptRelationship,
                    BrainConceptRelationship.id
                    == BrainConceptRelationshipOccurrence.relationship_id,
                )
                .join(source, source.c.id == BrainConceptRelationship.source_concept_id)
                .join(target, target.c.id == BrainConceptRelationship.target_concept_id)
                .where(BrainConceptRelationshipOccurrence.meeting_id == meeting_id)
                .order_by(source.c.canonical_name, target.c.canonical_name)
            )
        ).all()
    ]

    tags = list(
        (
            await session.execute(
                select(BrainConceptAssignment.label)
                .where(BrainConceptAssignment.meeting_id == meeting_id)
                .order_by(BrainConceptAssignment.label)
            )
        ).scalars()
    )

    people: dict[str, PersonItem] = {}
    for cid, name, label in (
        await session.execute(
            select(BrainConcept.id, BrainConcept.canonical_name, MeetingSpeaker.speaker_label)
            .join(MeetingSpeaker, MeetingSpeaker.concept_id == BrainConcept.id)
            .where(MeetingSpeaker.meeting_id == meeting_id)
            .order_by(BrainConcept.canonical_name, MeetingSpeaker.speaker_label)
        )
    ).all():
        people.setdefault(cid, PersonItem(id=cid, name=name, speakers=[])).speakers.append(label)

    return MeetingBrain(
        meeting_id=meeting_id,
        title=title,
        date=date,
        index=IndexStatus(**index.model_dump(), chunks=chunks[0], embedded=chunks[1]),
        projection=projection,
        facts=grouped,
        concepts=concepts,
        relationships=relationships,
        tags=tags,
        people=list(people.values()),
    )
