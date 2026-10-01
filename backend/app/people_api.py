"""People directory and speaker-to-person assignment (ADR 0021).

GET /api/people?q=                  people to suggest: person concepts that speak or are
                                    mentioned in some meeting, most present first
GET /api/meetings/{id}/speakers     the meeting's diarized speakers and who each one is
PUT /api/meetings/{id}/speakers     name them; queues Brain again (never the audio)

A person is a concept of type "person" (the same node Brain creates when it extracts that
name), so naming a speaker links the meeting to the person in the concept graph.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input, reanalysis
from app.concepts import canonical_key, display_name, lock_concepts, prune_orphans, resolve_concept
from app.config import Settings, get_settings
from app.database import get_session
from app.models import Meeting, MeetingSpeaker, MemoryConcept

router = APIRouter(tags=["people"])
Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
MAX_NAME_LENGTH = 100
SUGGESTIONS = 10


class Person(BaseModel):
    concept_id: str
    name: str
    meetings: int


class Speaker(BaseModel):
    track: str
    speaker: str
    seconds: float
    segments: int
    sample: str
    person: str | None
    concept_id: str | None


class Assignment(BaseModel):
    track: str = Field(max_length=20)
    speaker: str = Field(max_length=50)
    person: str | None = Field(default=None, max_length=200)


class SpeakersBody(BaseModel):
    assignments: list[Assignment] = Field(max_length=50)


class SpeakersResponse(BaseModel):
    speakers: list[Speaker]
    analysis: reanalysis.Analysis | None = None


@router.get("/api/people", response_model=list[Person])
async def people(session: Session, q: str = "") -> list[Person]:
    key = canonical_key(q)
    escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        await session.execute(
            text(
                """WITH links AS (
                       SELECT concept_id, meeting_id FROM memory_concept_mentions
                       UNION SELECT concept_id, meeting_id FROM meeting_speakers)
                   SELECT c.id, c.canonical_name, COUNT(DISTINCT l.meeting_id) AS meetings
                   FROM memory_concepts c JOIN links l ON l.concept_id = c.id
                   WHERE c.identity = 'concept' AND c.concept_type = 'person'
                     AND (:key = '' OR c.canonical_key LIKE :like ESCAPE '\\')
                   GROUP BY c.id, c.canonical_name
                   ORDER BY (c.canonical_key LIKE :prefix ESCAPE '\\') DESC, meetings DESC,
                            c.canonical_name
                   LIMIT :limit"""
            ),
            {
                "key": key,
                "like": f"%{escaped}%",
                "prefix": f"{escaped}%",
                "limit": SUGGESTIONS if key else 50,
            },
        )
    ).all()
    return [Person(concept_id=i, name=name, meetings=n) for i, name, n in rows]


async def _speakers(request: Request, session: AsyncSession, meeting_id: str) -> list[Speaker]:
    if await session.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    analysis = await analysis_input.load(
        session, request.app.state.storage, meeting_id, expand=False
    )
    if analysis is None:
        return []
    assigned = dict(
        (
            (track, label),
            (concept_id, name),
        )
        for track, label, concept_id, name in (
            await session.execute(
                select(
                    MeetingSpeaker.track,
                    MeetingSpeaker.speaker_label,
                    MemoryConcept.id,
                    MemoryConcept.canonical_name,
                )
                .join(MemoryConcept, MemoryConcept.id == MeetingSpeaker.concept_id)
                .where(MeetingSpeaker.meeting_id == meeting_id)
            )
        ).all()
    )
    groups: dict[tuple[str, str], dict] = {}
    for segment in analysis.transcript.segments:
        if not segment.speaker:
            continue
        group = groups.setdefault(
            (segment.track, segment.speaker), {"seconds": 0.0, "segments": 0, "sample": ""}
        )
        group["seconds"] += max(0.0, segment.end - segment.start)
        group["segments"] += 1
        if len(group["sample"]) < 60:
            group["sample"] = (group["sample"] + " " + segment.text).strip()[:120]
    return [
        Speaker(
            track=track,
            speaker=label,
            seconds=round(group["seconds"], 1),
            segments=group["segments"],
            sample=group["sample"],
            person=assigned.get((track, label), (None, None))[1],
            concept_id=assigned.get((track, label), (None, None))[0],
        )
        for (track, label), group in sorted(groups.items())
    ]


@router.get("/api/meetings/{meeting_id}/speakers", response_model=SpeakersResponse)
async def meeting_speakers(meeting_id: str, request: Request, session: Session) -> SpeakersResponse:
    return SpeakersResponse(speakers=await _speakers(request, session, meeting_id))


@router.put("/api/meetings/{meeting_id}/speakers", response_model=SpeakersResponse)
async def name_speakers(
    meeting_id: str,
    body: SpeakersBody,
    request: Request,
    session: Session,
    settings: AppSettings,
) -> SpeakersResponse:
    """Replace who each speaker is. An empty name leaves the speaker unnamed."""
    current = await _speakers(request, session, meeting_id)
    known = {(s.track, s.speaker) for s in current}
    names: dict[tuple[str, str], str] = {}
    for item in body.assignments:
        if (item.track, item.speaker) not in known:
            raise HTTPException(status_code=422, detail="UNKNOWN_SPEAKER")
        name = display_name(item.person or "")
        if not name:
            continue
        if len(name) > MAX_NAME_LENGTH or not canonical_key(name):
            raise HTTPException(status_code=422, detail="INVALID_PERSON")
        names[(item.track, item.speaker)] = name
    before = {(s.track, s.speaker): s.person for s in current if s.person}

    await lock_concepts(session)
    await session.execute(delete(MeetingSpeaker).where(MeetingSpeaker.meeting_id == meeting_id))
    for (track, label), name in names.items():
        concept = await resolve_concept(session, "person", name)
        assert concept is not None  # the key is non-empty
        # Whatever Brain called it before, a speaker is a person.
        await session.execute(
            update(MemoryConcept)
            .where(MemoryConcept.id == concept.id, MemoryConcept.identity == "concept")
            .values(concept_type="person")
        )
        session.add(
            MeetingSpeaker(
                meeting_id=meeting_id, track=track, speaker_label=label, concept_id=concept.id
            )
        )
    await session.flush()
    await prune_orphans(session)  # a person nobody speaks as or mentions any more
    await session.commit()

    changed = {k: canonical_key(v) for k, v in before.items()} != {
        k: canonical_key(v) for k, v in names.items()
    }
    analysis = (
        await reanalysis.queue(request, session, settings, meeting_id, memory=False)
        if changed
        else "unchanged"
    )
    return SpeakersResponse(
        speakers=await _speakers(request, session, meeting_id), analysis=analysis
    )
