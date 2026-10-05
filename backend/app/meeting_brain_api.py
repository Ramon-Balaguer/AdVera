"""What the Brain knows of one meeting that its summary does not (ADR 0024). Read only.

The summary tells what happened in the meeting; this tells how it connects to the rest: the
state of its index and projection, the concepts and relationships found in it and in how many
other meetings each one appears, its tags and the people named as its speakers (the same), and
how many facts (decisions, actions...) it holds. The facts themselves are listed by
`/api/brain/facts`, and the summary stays its own endpoint.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input
from app.brain_jobs import CONCEPT_PROJECTION_VERSION
from app.database import get_session
from app.facts_api import KINDS, meeting_date
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


class Reach(BaseModel):
    """How far a concept, tag or person goes beyond this meeting."""

    other_meetings: int
    first_seen: datetime | None = None  # the earliest meeting it appears in


class ConceptItem(Reach):
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


class TagItem(Reach):
    id: str
    label: str


class PersonItem(Reach):
    id: str
    name: str
    speakers: list[str]


class MeetingBrain(BaseModel):
    meeting_id: str
    title: str
    date: datetime
    index: IndexStatus
    projection: JobStatus
    fact_counts: dict[str, int]
    concepts: list[ConceptItem]
    relationships: list[RelationshipItem]
    tags: list[TagItem]
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


async def _reach(
    session: AsyncSession, meeting_id: str, concept_ids: list[str]
) -> dict[str, Reach]:
    """In how many meetings besides this one each concept appears (mentioned, tagged or
    spoken as a person), and since when."""
    if not concept_ids:
        return {}
    rows = (
        await session.execute(
            text(
                """WITH links AS (
                       SELECT concept_id, meeting_id FROM brain_concept_mentions
                       UNION SELECT concept_id, meeting_id FROM brain_concept_assignments
                       UNION SELECT concept_id, meeting_id FROM meeting_speakers)
                   SELECT l.concept_id,
                          COUNT(DISTINCT l.meeting_id) FILTER (WHERE l.meeting_id <> :meeting),
                          MIN(COALESCE(m.started_at, m.created_at))
                   FROM links l JOIN meetings m ON m.id = l.meeting_id
                   WHERE l.concept_id = ANY(:ids)
                   GROUP BY l.concept_id"""
            ),
            {"meeting": meeting_id, "ids": concept_ids},
        )
    ).all()
    return {cid: Reach(other_meetings=others, first_seen=first) for cid, others, first in rows}


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

    counted = dict(
        (
            await session.execute(
                select(BrainFact.kind, func.count())
                .where(BrainFact.meeting_id == meeting_id)
                .group_by(BrainFact.kind)
            )
        ).all()
    )

    mentioned = (
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
        )
    ).all()

    tags = (
        await session.execute(
            select(BrainConcept.id, BrainConceptAssignment.label)
            .join(BrainConceptAssignment, BrainConceptAssignment.concept_id == BrainConcept.id)
            .where(BrainConceptAssignment.meeting_id == meeting_id)
            .order_by(BrainConceptAssignment.label)
        )
    ).all()

    speakers = (
        await session.execute(
            select(BrainConcept.id, BrainConcept.canonical_name, MeetingSpeaker.speaker_label)
            .join(MeetingSpeaker, MeetingSpeaker.concept_id == BrainConcept.id)
            .where(MeetingSpeaker.meeting_id == meeting_id)
            .order_by(BrainConcept.canonical_name, MeetingSpeaker.speaker_label)
        )
    ).all()

    reach = await _reach(
        session,
        meeting_id,
        list(
            {row[0] for row in mentioned} | {row[0] for row in tags} | {row[0] for row in speakers}
        ),
    )
    alone = Reach(other_meetings=0)

    concepts = [
        ConceptItem(
            id=cid,
            name=name,
            type=mention_type or ctype,
            mentions=len(evidence or []),
            **reach.get(cid, alone).model_dump(),
        )
        for cid, name, ctype, mention_type, evidence in mentioned
    ]
    concepts.sort(key=lambda item: (-item.other_meetings, -item.mentions, item.name.lower()))

    people: dict[str, PersonItem] = {}
    for cid, name, label in speakers:
        person = people.setdefault(
            cid, PersonItem(id=cid, name=name, speakers=[], **reach.get(cid, alone).model_dump())
        )
        person.speakers.append(label)

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

    return MeetingBrain(
        meeting_id=meeting_id,
        title=title,
        date=date,
        index=IndexStatus(**index.model_dump(), chunks=chunks[0], embedded=chunks[1]),
        projection=projection,
        fact_counts={kind: counted.get(kind, 0) for kind in KINDS},
        concepts=concepts,
        relationships=relationships,
        tags=[
            TagItem(id=cid, label=label, **reach.get(cid, alone).model_dump())
            for cid, label in tags
        ],
        people=list(people.values()),
    )
