"""Queue the text analysis of a meeting again after its notes or speakers' names changed.

Only the text stages run again (Summary, its concept projection, Brain chunks); the audio is
never processed again. Jobs are keyed by what they read (`analysis_input`), so saving the same
content twice queues nothing new.
"""

import logging
from typing import Literal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input, brain_jobs, runtime_settings, summary_jobs
from app.config import Settings
from app.models import BrainChunk, SummaryExtraction

logger = logging.getLogger("advera.reanalysis")

Analysis = Literal["queued", "waiting_transcript", "llm_not_configured", "unchanged"]


async def queue(
    request: Request,
    session: AsyncSession,
    settings: Settings,
    meeting_id: str,
    *,
    brain: bool,
) -> Analysis:
    """Queue Summary (and with `brain` the Brain chunks) for what the meeting holds now.

    Call after the change is committed. A meeting still recording or transcribing has no
    definitive transcript yet: its first analysis will read the saved notes and names.
    """
    analysis = await analysis_input.load(
        session, request.app.state.storage, meeting_id, expand=False
    )
    if analysis is None:
        return "waiting_transcript"
    queued: list[tuple[str, str]] = []
    if brain:
        index_job = await brain_jobs.create_or_reuse_index_job(
            session, meeting_id=meeting_id, input_sha256=analysis.brain_sha256, settings=settings
        )
        current = (
            await session.execute(
                select(BrainChunk.index_job_id).where(BrainChunk.meeting_id == meeting_id).limit(1)
            )
        ).scalar_one_or_none()
        if index_job.status == "completed" and current != index_job.id:
            # The same input was indexed before, then replaced (notes A -> B -> A): index again.
            index_job = await brain_jobs.create_or_reuse_index_job(
                session,
                meeting_id=meeting_id,
                input_sha256=analysis.brain_sha256,
                settings=settings,
                force=True,
            )
        if index_job.status == "queued":
            queued.append(("index", index_job.id))
    runtime = runtime_settings.load(settings)
    summary_job = None
    if runtime.llm_configured:
        summary_job = await summary_jobs.create_or_reuse(
            session,
            meeting_id=meeting_id,
            input_sha256=analysis.summary_sha256,
            runtime=runtime,
            settings=settings,
        )
        latest = (
            await session.execute(
                select(SummaryExtraction.job_id)
                .where(SummaryExtraction.meeting_id == meeting_id)
                .order_by(SummaryExtraction.generated_at.desc(), SummaryExtraction.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if summary_job.status == "completed" and latest != summary_job.id:
            # An earlier extraction for this same input was superseded by a newer one: run it
            # again so it becomes the latest (the graph projects only the latest extraction).
            summary_job = await summary_jobs.create_or_reuse(
                session,
                meeting_id=meeting_id,
                input_sha256=analysis.summary_sha256,
                runtime=runtime,
                settings=settings,
                force=True,
            )
        if summary_job.status == "queued":
            queued.append(("summary", summary_job.id))
    await session.commit()
    for kind, job_id in queued:
        if kind == "summary":
            await summary_jobs.publish(request.app.state.summary_queue, job_id)
        else:
            await brain_jobs.publish(request.app.state.brain_index_queue, job_id, "index")
    if not runtime.llm_configured:
        return "llm_not_configured"
    return "queued" if queued else "unchanged"
