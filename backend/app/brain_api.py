"""Brain API (spec §20): GET and POST /api/meetings/{id}/brain.

States: `blocked` (no definitive transcript), `not_started`, `queued`, `running`,
`completed`, `empty` and `failed`. The result is served as one document, as spec §20 describes.
"""

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import brain_jobs, runtime_settings
from app.config import Settings, get_settings
from app.database import get_session
from app.models import BrainExtraction, BrainJob, Meeting
from app.transcripts import parse_definitive

router = APIRouter(prefix="/api/meetings", tags=["brain"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]

BrainState = Literal["blocked", "not_started", "queued", "running", "completed", "empty", "failed"]


class BrainJobView(BaseModel):
    job_id: str
    status: str
    provider: str
    model: str
    prompt_version: str
    language: str
    attempts: int
    max_attempts: int
    error: str | None


class BrainResponse(BaseModel):
    meeting_id: str
    state: BrainState
    llm_configured: bool
    job: BrainJobView | None = None
    result: dict[str, Any] | None = None
    generated_at: str | None = None


def _job_view(job: BrainJob) -> BrainJobView:
    return BrainJobView(
        job_id=job.id,
        status=job.status,
        provider=job.provider,
        model=job.model,
        prompt_version=job.prompt_version,
        language=job.language,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error=job.error,
    )


async def _transcript_hash(request: Request, meeting_id: str) -> str | None:
    storage = request.app.state.storage
    transcript = parse_definitive(await asyncio.to_thread(storage.read_transcript, meeting_id))
    return transcript.segments_sha256 if transcript else None


@router.get("/{meeting_id}/brain", response_model=BrainResponse)
async def get_brain(
    meeting_id: str, request: Request, session: Session, settings: AppSettings
) -> BrainResponse:
    if await session.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    configured = runtime_settings.load(settings).llm_configured
    input_sha256 = await _transcript_hash(request, meeting_id)
    if input_sha256 is None:
        return BrainResponse(meeting_id=meeting_id, state="blocked", llm_configured=configured)
    job = (
        await session.execute(
            select(BrainJob)
            .where(BrainJob.meeting_id == meeting_id, BrainJob.input_sha256 == input_sha256)
            .order_by(BrainJob.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return BrainResponse(meeting_id=meeting_id, state="not_started", llm_configured=configured)
    if job.status != "completed":
        return BrainResponse(
            meeting_id=meeting_id, state=job.status, llm_configured=configured, job=_job_view(job)
        )
    extraction = (
        await session.execute(select(BrainExtraction).where(BrainExtraction.job_id == job.id))
    ).scalar_one_or_none()
    if extraction is None:
        return BrainResponse(
            meeting_id=meeting_id, state="failed", llm_configured=configured, job=_job_view(job)
        )
    return BrainResponse(
        meeting_id=meeting_id,
        state=extraction.status,
        llm_configured=configured,
        job=_job_view(job),
        result=extraction.result,
        generated_at=extraction.generated_at.isoformat(),
    )


@router.post("/{meeting_id}/brain", response_model=BrainResponse, status_code=202)
async def regenerate_brain(
    meeting_id: str, request: Request, session: Session, settings: AppSettings
) -> BrainResponse:
    """Create, retry or force the Brain job for the current definitive transcript."""
    if await session.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    input_sha256 = await _transcript_hash(request, meeting_id)
    if input_sha256 is None:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_AVAILABLE")
    if await brain_jobs.active_job(session, meeting_id):
        raise HTTPException(status_code=409, detail="BRAIN_ALREADY_RUNNING")
    runtime = runtime_settings.load(settings)
    if not runtime.llm_configured:
        raise HTTPException(status_code=409, detail="LLM_NOT_CONFIGURED")
    job = await brain_jobs.create_or_reuse(
        session,
        meeting_id=meeting_id,
        input_sha256=input_sha256,
        runtime=runtime,
        settings=settings,
        force=True,
    )
    await session.commit()
    await brain_jobs.publish(request.app.state.brain_queue, job.id)
    return BrainResponse(
        meeting_id=meeting_id, state=job.status, llm_configured=True, job=_job_view(job)
    )
