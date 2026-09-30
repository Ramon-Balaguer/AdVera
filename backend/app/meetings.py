"""Meeting REST API: CRUD, definitive transcript, durable transcription status, audio and
media import (spec §20; ADR 0008, 0011, 0012)."""

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio_http import wav_response
from app.config import Settings, get_settings
from app.database import get_session
from app.job_queue import JobQueue
from app.media_import import (
    MediaImportError,
    convert_to_system_track,
    imports_in_progress,
    store_upload,
    validate_media,
)
from app.meeting_contracts import (
    ImportResponse,
    MeetingCreate,
    MeetingResponse,
    MeetingUpdate,
    TranscriptionStatusResponse,
)
from app.models import Meeting
from app.storage import MeetingStorage
from app.transcription_jobs import (
    active_job,
    latest_job,
    publish,
    queue_meeting_transcription,
)
from app.transcripts import TranscriptDocument, attendee_count, parse_definitive

logger = logging.getLogger("advera.meetings")

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

# Imports in flight in this process; a second import for the same meeting is rejected.


def get_storage(request: Request) -> MeetingStorage:
    return request.app.state.storage


def get_queue(request: Request) -> JobQueue:
    return request.app.state.transcription_queue


Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[MeetingStorage, Depends(get_storage)]
Queue = Annotated[JobQueue, Depends(get_queue)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _read_transcript(storage: MeetingStorage, meeting_id: str) -> dict | None:
    try:
        return storage.read_transcript(meeting_id)
    except (OSError, ValueError):
        return None  # unreadable transcripts never make the meeting unavailable (ADR 0011)


def _to_response(meeting: Meeting, storage: MeetingStorage) -> MeetingResponse:
    response = MeetingResponse.model_validate(meeting)
    response.attendee_count = attendee_count(_read_transcript(storage, meeting.id))
    response.tracks = storage.non_empty_tracks(meeting.id)
    return response


async def _get_meeting(session: AsyncSession, meeting_id: str) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    return meeting


@router.get("", response_model=list[MeetingResponse])
async def list_meetings(session: Session, storage: Storage) -> list[MeetingResponse]:
    meetings = (
        (await session.execute(select(Meeting).order_by(Meeting.created_at.desc()))).scalars().all()
    )
    # Transcript reads for the derived attendee count run off the event loop.
    return await asyncio.to_thread(lambda: [_to_response(meeting, storage) for meeting in meetings])


@router.post("", response_model=MeetingResponse, status_code=201)
async def create_meeting(
    body: MeetingCreate, session: Session, storage: Storage
) -> MeetingResponse:
    meeting = Meeting(title=body.title, description=body.description, primary_language=[])
    session.add(meeting)
    await session.commit()
    return _to_response(meeting, storage)


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(meeting_id: str, session: Session, storage: Storage) -> MeetingResponse:
    return _to_response(await _get_meeting(session, meeting_id), storage)


@router.patch("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    meeting_id: str, body: MeetingUpdate, session: Session, storage: Storage
) -> MeetingResponse:
    meeting = await _get_meeting(session, meeting_id)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is None:
        raise HTTPException(status_code=422, detail="TITLE_REQUIRED")
    for field, value in changes.items():
        setattr(meeting, field, value)
    await session.commit()
    return _to_response(meeting, storage)


@router.delete("/{meeting_id}", status_code=204)
async def delete_meeting(
    meeting_id: str, session: Session, storage: Storage, request: Request
) -> Response:
    meeting = await _get_meeting(session, meeting_id)
    await session.delete(meeting)
    await session.commit()
    request.app.state.audio_sessions.forget(meeting_id)
    # Storage cleanup runs after the database commit; a failure is surfaced, never ignored.
    try:
        await asyncio.to_thread(storage.delete_meeting, meeting_id)
    except OSError as error:
        logger.error("meeting %s storage cleanup failed: %s", meeting_id, type(error).__name__)
        raise HTTPException(status_code=500, detail="STORAGE_CLEANUP_FAILED") from None
    return Response(status_code=204)


@router.get("/{meeting_id}/transcript", response_model=TranscriptDocument)
async def get_transcript(meeting_id: str, session: Session, storage: Storage) -> TranscriptDocument:
    await _get_meeting(session, meeting_id)
    transcript = parse_definitive(await asyncio.to_thread(_read_transcript, storage, meeting_id))
    if transcript is None:
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_AVAILABLE")
    return transcript


@router.get("/{meeting_id}/transcription", response_model=TranscriptionStatusResponse)
async def get_transcription_status(
    meeting_id: str, session: Session
) -> TranscriptionStatusResponse:
    """Durable transcription state: the recovery contract after any disconnect (ADR 0008)."""
    await _get_meeting(session, meeting_id)
    job = await latest_job(session, meeting_id)
    if job is None:
        raise HTTPException(status_code=404, detail="TRANSCRIPTION_NOT_FOUND")
    return TranscriptionStatusResponse.model_validate(job)


@router.get("/{meeting_id}/audio-metrics")
async def get_audio_metrics(meeting_id: str, session: Session, request: Request) -> dict:
    """Capture session cursor and per-track metrics, for recovery after a disconnect."""
    await _get_meeting(session, meeting_id)
    metrics = request.app.state.audio_sessions.metrics(meeting_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="AUDIO_SESSION_NOT_FOUND")
    return metrics


@router.get("/{meeting_id}/audio/{track}")
async def get_audio(
    meeting_id: str,
    track: Literal["microphone", "system"],
    session: Session,
    storage: Storage,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
):
    await _get_meeting(session, meeting_id)
    if track not in storage.non_empty_tracks(meeting_id):
        raise HTTPException(status_code=404, detail="TRACK_NOT_AVAILABLE")
    return wav_response(storage.track_path(meeting_id, track), range_header)


@router.post("/{meeting_id}/imports", response_model=ImportResponse, status_code=202)
async def import_media(
    meeting_id: str,
    file: Annotated[UploadFile, File()],
    session: Session,
    storage: Storage,
    queue: Queue,
    settings: AppSettings,
) -> ImportResponse:
    """Import one audio/video file as `system.pcm` and queue definitive transcription."""
    # Claim the meeting before any await: two requests must not both pass the check.
    if meeting_id in imports_in_progress:
        raise HTTPException(status_code=409, detail="IMPORT_IN_PROGRESS")
    imports_in_progress.add(meeting_id)
    try:
        meeting = await _get_meeting(session, meeting_id)
        if meeting.status in ("recording", "processing") or await active_job(session, meeting_id):
            raise HTTPException(status_code=409, detail="MEETING_BUSY")
        if "microphone" in storage.non_empty_tracks(meeting_id):
            # An import replaces system.pcm; beside a recorded microphone it would mix
            # unrelated audio into one transcript (ADR 0012).
            raise HTTPException(status_code=409, detail="MEETING_ALREADY_RECORDED")
        await session.rollback()  # do not hold a transaction open during upload and conversion

        extension = validate_media(file.filename, file.content_type)
        source = await store_upload(
            file, storage, meeting_id, extension, settings.media_import_max_bytes
        )
        try:
            await convert_to_system_track(
                source,
                storage,
                meeting_id,
                settings.ffmpeg_binary,
                settings.media_import_timeout_seconds,
                settings.media_import_max_seconds,
            )
        finally:
            # Only the extracted audio is kept, never the uploaded file (ADR 0016).
            source.unlink(missing_ok=True)
        meeting = await _get_meeting(session, meeting_id)
        job = await queue_meeting_transcription(session, storage, settings, meeting)
    except MediaImportError as error:
        raise HTTPException(status_code=error.status_code, detail=error.code) from None
    finally:
        imports_in_progress.discard(meeting_id)

    # Publish only after the job is committed; a Redis failure leaves it queued (ADR 0008).
    if job.status == "queued":
        await publish(queue, job.id)
    logger.info("meeting %s imported media; transcription job %s", meeting_id, job.id)
    return ImportResponse(
        meeting=_to_response(meeting, storage),
        transcription=TranscriptionStatusResponse.model_validate(job),
    )
