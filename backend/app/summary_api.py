"""Summary API (spec §20): GET and POST /api/meetings/{id}/summary.

States: `blocked` (no definitive transcript), `not_started`, `queued`, `running`,
`completed`, `empty` and `failed`. The result is served as one document, as spec §20 describes.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input, runtime_settings, summary_jobs
from app.config import Settings, get_settings
from app.database import get_session
from app.models import Meeting, SummaryExtraction, SummaryJob

router = APIRouter(prefix="/api/meetings", tags=["summary"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]

SummaryState = Literal[
    "blocked", "not_started", "queued", "running", "completed", "empty", "failed"
]


class SummaryJobView(BaseModel):
    job_id: str
    status: str
    provider: str
    model: str
    prompt_version: str
    language: str
    attempts: int
    max_attempts: int
    error: str | None


class SummaryResponse(BaseModel):
    meeting_id: str
    state: SummaryState
    llm_configured: bool
    job: SummaryJobView | None = None
    result: dict[str, Any] | None = None
    generated_at: str | None = None


def _job_view(job: SummaryJob) -> SummaryJobView:
    return SummaryJobView(
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


async def _transcript_hash(request: Request, session: AsyncSession, meeting_id: str) -> str | None:
    """What Summary reads now: transcript, notes and speakers' names (ADR 0020/0021)."""
    analysis = await analysis_input.load(
        session, request.app.state.storage, meeting_id, expand=False
    )
    return analysis.summary_sha256 if analysis else None


@router.get("/{meeting_id}/summary", response_model=SummaryResponse)
async def get_summary(
    meeting_id: str, request: Request, session: Session, settings: AppSettings
) -> SummaryResponse:
    if await session.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    configured = runtime_settings.load(settings).llm_configured
    input_sha256 = await _transcript_hash(request, session, meeting_id)
    if input_sha256 is None:
        return SummaryResponse(meeting_id=meeting_id, state="blocked", llm_configured=configured)
    job = (
        await session.execute(
            select(SummaryJob)
            .where(SummaryJob.meeting_id == meeting_id, SummaryJob.input_sha256 == input_sha256)
            .order_by(SummaryJob.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return SummaryResponse(
            meeting_id=meeting_id, state="not_started", llm_configured=configured
        )
    if job.status != "completed":
        return SummaryResponse(
            meeting_id=meeting_id, state=job.status, llm_configured=configured, job=_job_view(job)
        )
    extraction = (
        await session.execute(select(SummaryExtraction).where(SummaryExtraction.job_id == job.id))
    ).scalar_one_or_none()
    if extraction is None:
        return SummaryResponse(
            meeting_id=meeting_id, state="failed", llm_configured=configured, job=_job_view(job)
        )
    return SummaryResponse(
        meeting_id=meeting_id,
        state=extraction.status,
        llm_configured=configured,
        job=_job_view(job),
        result=extraction.result,
        generated_at=extraction.generated_at.isoformat(),
    )


@router.post("/{meeting_id}/summary", response_model=SummaryResponse, status_code=202)
async def regenerate_summary(
    meeting_id: str, request: Request, session: Session, settings: AppSettings
) -> SummaryResponse:
    """Create, retry or force the Summary job for the current definitive transcript."""
    if await session.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    input_sha256 = await _transcript_hash(request, session, meeting_id)
    if input_sha256 is None:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_AVAILABLE")
    if await summary_jobs.active_job(session, meeting_id):
        raise HTTPException(status_code=409, detail="SUMMARY_ALREADY_RUNNING")
    runtime = runtime_settings.load(settings)
    if not runtime.llm_configured:
        raise HTTPException(status_code=409, detail="LLM_NOT_CONFIGURED")
    job = await summary_jobs.create_or_reuse(
        session,
        meeting_id=meeting_id,
        input_sha256=input_sha256,
        runtime=runtime,
        settings=settings,
        force=True,
    )
    await session.commit()
    await summary_jobs.publish(request.app.state.summary_queue, job.id)
    return SummaryResponse(
        meeting_id=meeting_id, state=job.status, llm_configured=True, job=_job_view(job)
    )
