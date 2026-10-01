"""Meeting notes and @references (ADR 0020).

GET /api/meetings/{id}/notes          the notes (Markdown)
PUT /api/meetings/{id}/notes          save them; queues the text analysis again
GET /api/meetings/{id}/references     meetings whose notes reference this one
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import reanalysis
from app.config import Settings, get_settings
from app.database import get_session
from app.models import Meeting, MeetingNotes, MeetingReference, utcnow
from app.notes import MAX_NOTES_CHARS, notes_sha256, split_blocks

router = APIRouter(prefix="/api/meetings", tags=["notes"])
Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class NotesBody(BaseModel):
    content: str = Field(max_length=MAX_NOTES_CHARS)


class NotesResponse(BaseModel):
    meeting_id: str
    content: str
    updated_at: datetime | None
    analysis: reanalysis.Analysis | None = None


class Backlink(BaseModel):
    meeting_id: str
    title: str
    segment_id: str | None
    note_block_id: str


async def _meeting(session: AsyncSession, meeting_id: str) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    return meeting


@router.get("/{meeting_id}/notes", response_model=NotesResponse)
async def get_notes(meeting_id: str, session: Session) -> NotesResponse:
    await _meeting(session, meeting_id)
    notes = await session.get(MeetingNotes, meeting_id)
    return NotesResponse(
        meeting_id=meeting_id,
        content=notes.content if notes else "",
        updated_at=notes.updated_at if notes else None,
    )


@router.put("/{meeting_id}/notes", response_model=NotesResponse)
async def save_notes(
    meeting_id: str, body: NotesBody, request: Request, session: Session, settings: AppSettings
) -> NotesResponse:
    """Save the notes and their @references; when the meeting already has a definitive
    transcript, Brain and Memory are queued again with them (never the audio)."""
    await _meeting(session, meeting_id)
    # One save of this meeting's notes at a time: the first insert and the references rebuild
    # must not interleave with another save.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"notes:{meeting_id}"}
    )
    content = body.content.replace("\r\n", "\n")
    digest = notes_sha256(content) or ""
    notes = await session.get(MeetingNotes, meeting_id)
    changed = notes is None or notes.content_sha256 != digest
    if notes is None:
        notes = MeetingNotes(meeting_id=meeting_id, content=content, content_sha256=digest)
        session.add(notes)
    notes.content = content
    notes.content_sha256 = digest
    notes.updated_at = utcnow()

    # References are rebuilt from the text; one to a meeting that no longer exists is skipped.
    await session.execute(
        delete(MeetingReference).where(MeetingReference.source_meeting_id == meeting_id)
    )
    wanted = [
        (block.id, reference)
        for block in split_blocks(content)
        for reference in block.references
        if reference.meeting_id != meeting_id
    ]
    existing = set(
        (
            await session.execute(
                select(Meeting.id).where(Meeting.id.in_({r.meeting_id for _b, r in wanted} or {""}))
            )
        ).scalars()
    )
    for block_id, reference in wanted:
        if reference.meeting_id in existing:
            session.add(
                MeetingReference(
                    source_meeting_id=meeting_id,
                    target_meeting_id=reference.meeting_id,
                    target_segment_id=reference.segment_id,
                    note_block_id=block_id,
                    label=reference.label[:200],
                )
            )
    await session.commit()
    analysis = (
        await reanalysis.queue(request, session, settings, meeting_id, memory=True)
        if changed
        else "unchanged"
    )
    return NotesResponse(
        meeting_id=meeting_id,
        content=notes.content,
        updated_at=notes.updated_at,
        analysis=analysis,
    )


@router.get("/{meeting_id}/references", response_model=list[Backlink])
async def backlinks(meeting_id: str, session: Session) -> list[Backlink]:
    await _meeting(session, meeting_id)
    rows = (
        await session.execute(
            select(
                MeetingReference.source_meeting_id,
                Meeting.title,
                MeetingReference.target_segment_id,
                MeetingReference.note_block_id,
            )
            .join(Meeting, Meeting.id == MeetingReference.source_meeting_id)
            .where(MeetingReference.target_meeting_id == meeting_id)
            .order_by(Meeting.created_at.desc(), MeetingReference.note_block_id)
        )
    ).all()
    return [
        Backlink(meeting_id=source, title=title, segment_id=segment, note_block_id=block)
        for source, title, segment, block in rows
    ]
