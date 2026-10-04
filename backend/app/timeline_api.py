"""Timeline of a concept or tag across meetings (rebuild-concept-timeline.md).

GET /api/brain/concepts/{id}/timeline

Every meeting where the concept appears, newest first (by when the meeting started, else when
it was created): how it appears (mentioned, tagged, a speaker who is this person), quotes with
the moments that cite it, and the facts of that meeting's latest Summary extraction related to
it (decisions, actions, risks, questions, topics), so the evolution of a project can be read
in order. A fact is related when it cites a segment where the concept is mentioned or its text
names the concept or an alias; for a tag, the whole meeting carries it, so its main facts are
shown. Read-only; nothing is generated here.
"""

import asyncio
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.concept_graph_api import _segment_texts
from app.concepts import canonical_key
from app.database import get_session
from app.models import MeetingNotes, SummaryExtraction
from app.notes import split_blocks

router = APIRouter(tags=["brain"])
Session = Annotated[AsyncSession, Depends(get_session)]

MAX_MEETINGS = 60
MAX_QUOTES = 3
MAX_FACTS = 8
FACT_KINDS = {
    "decisions": "decision",
    "actions": "action",
    "risks": "risk",
    "open_questions": "question",
    "topics": "topic",
}
Kind = Literal["decision", "action", "risk", "question", "topic"]


class TimelineCitation(BaseModel):
    segment_id: str
    start: float | None
    track: str | None = None
    text: str | None = None


class TimelineFact(BaseModel):
    kind: Kind
    text: str
    state: str | None = None
    owner: str | None = None
    due_date: str | None = None
    evidence: list[TimelineCitation]


class TimelineEntry(BaseModel):
    meeting_id: str
    title: str
    date: datetime
    mentioned: bool
    tagged: bool
    spoke: bool
    quotes: list[TimelineCitation]
    facts: list[TimelineFact]
    summary: str | None = None


class Timeline(BaseModel):
    concept_id: str
    label: str
    type: str
    is_tag: bool
    entries: list[TimelineEntry]
    truncated: bool


def _related(item_text: str, keys: set[str]) -> bool:
    words = f" {canonical_key(item_text)} "
    return any(f" {key} " in words or (len(key) > 4 and key in words) for key in keys)


@router.get("/api/brain/concepts/{concept_id}/timeline", response_model=Timeline)
async def concept_timeline(concept_id: str, session: Session, request: Request) -> Timeline:
    concept = (
        await session.execute(
            text(
                """SELECT id, concept_type, canonical_name, canonical_key, identity
                   FROM brain_concepts WHERE id = :id"""
            ),
            {"id": concept_id},
        )
    ).one_or_none()
    if concept is None:
        raise HTTPException(status_code=404, detail="CONCEPT_NOT_FOUND")
    _id, concept_type, name, key, identity = concept
    is_tag = identity == "tag"
    aliases = (
        await session.execute(
            text("SELECT normalized_alias FROM brain_concept_aliases WHERE concept_id = :id"),
            {"id": concept_id},
        )
    ).scalars()
    keys = {key, *aliases}

    rows = (
        await session.execute(
            text(
                """WITH links AS (
                       SELECT meeting_id, 'mention' AS how FROM brain_concept_mentions
                       WHERE concept_id = :id
                       UNION ALL SELECT meeting_id, 'tag' FROM brain_concept_assignments
                       WHERE concept_id = :id
                       UNION ALL SELECT meeting_id, 'speaker' FROM meeting_speakers
                       WHERE concept_id = :id)
                   SELECT m.id, m.title, COALESCE(m.started_at, m.created_at) AS date,
                          ARRAY_AGG(DISTINCT l.how) AS hows
                   FROM links l JOIN meetings m ON m.id = l.meeting_id
                   GROUP BY m.id, m.title, date
                   ORDER BY date DESC, m.id DESC"""
            ),
            {"id": concept_id},
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="CONCEPT_NOT_FOUND")  # nobody's any more
    truncated = len(rows) > MAX_MEETINGS
    rows = rows[:MAX_MEETINGS]  # the most recent ones
    meeting_ids = [r[0] for r in rows]

    mentions: dict[str, list[dict]] = {}
    for meeting_id, evidence in (
        await session.execute(
            text(
                """SELECT meeting_id, evidence FROM brain_concept_mentions
                   WHERE concept_id = :id AND meeting_id = ANY(:ids)"""
            ),
            {"id": concept_id, "ids": meeting_ids},
        )
    ).all():
        mentions.setdefault(meeting_id, []).extend(evidence or [])

    extractions: dict[str, dict] = {}
    for meeting_id, result in (
        await session.execute(
            select(SummaryExtraction.meeting_id, SummaryExtraction.result)
            .where(SummaryExtraction.meeting_id.in_(meeting_ids))
            .order_by(SummaryExtraction.generated_at)
        )
    ).all():
        extractions[meeting_id] = result or {}  # ordered: the latest one wins

    texts = await asyncio.to_thread(_segment_texts, request.app.state.storage, meeting_ids)
    for notes in (
        (
            await session.execute(
                select(MeetingNotes).where(MeetingNotes.meeting_id.in_(meeting_ids))
            )
        )
        .scalars()
        .all()
    ):
        for block in split_blocks(notes.content):
            texts.setdefault(notes.meeting_id, {})[block.id] = block.text

    def citation(meeting_id: str, raw: dict) -> TimelineCitation:
        return TimelineCitation(
            segment_id=raw["segment_id"],
            start=raw.get("start"),
            track=raw.get("track"),
            text=raw.get("text") or texts.get(meeting_id, {}).get(raw["segment_id"]),
        )

    entries = []
    for meeting_id, title, date, hows in rows:
        cited = mentions.get(meeting_id, [])
        cited_ids = {e["segment_id"] for e in cited}
        result = extractions.get(meeting_id, {})
        facts: list[TimelineFact] = []
        for category, kind in FACT_KINDS.items():
            for item in result.get(category) or []:
                evidence = item.get("evidence") or []
                if not (
                    is_tag
                    and kind != "topic"
                    or cited_ids & {e["segment_id"] for e in evidence}
                    or _related(item.get("text", ""), keys)
                ):
                    continue
                facts.append(
                    TimelineFact(
                        kind=kind,
                        text=item.get("text", ""),
                        state=item.get("state"),
                        owner=item.get("owner"),
                        due_date=item.get("due_date"),
                        evidence=[citation(meeting_id, e) for e in evidence[:MAX_QUOTES]],
                    )
                )
        summary = ((result.get("summary") or {}).get("text") or None) if is_tag else None
        entries.append(
            TimelineEntry(
                meeting_id=meeting_id,
                title=title,
                date=date,
                mentioned="mention" in hows,
                tagged="tag" in hows,
                spoke="speaker" in hows,
                quotes=[citation(meeting_id, e) for e in cited[:MAX_QUOTES]],
                facts=facts[:MAX_FACTS],
                summary=summary,
            )
        )
    return Timeline(
        concept_id=concept_id,
        label=name,
        type=concept_type,
        is_tag=is_tag,
        entries=entries,
        truncated=truncated,
    )
