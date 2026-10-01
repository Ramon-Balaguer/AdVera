"""Queue the text analysis of a meeting again after its notes or speakers' names changed.

Only the text stages run again (Brain, its concept projection, Memory chunks); the audio is
never processed again. Jobs are keyed by what they read (`analysis_input`), so saving the same
content twice queues nothing new.
"""

import logging
from typing import Literal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input, brain_jobs, memory_jobs, runtime_settings
from app.config import Settings
from app.models import BrainExtraction, MemoryChunk

logger = logging.getLogger("advera.reanalysis")

Analysis = Literal["queued", "waiting_transcript", "llm_not_configured", "unchanged"]


async def queue(
    request: Request,
    session: AsyncSession,
    settings: Settings,
    meeting_id: str,
    *,
    memory: bool,
) -> Analysis:
    """Queue Brain (and with `memory` the Memory chunks) for what the meeting holds now.

    Call after the change is committed. A meeting still recording or transcribing has no
    definitive transcript yet: its first analysis will read the saved notes and names.
    """
    analysis = await analysis_input.load(
        session, request.app.state.storage, meeting_id, expand=False
    )
    if analysis is None:
        return "waiting_transcript"
    queued: list[tuple[str, str]] = []
    if memory:
        index_job = await memory_jobs.create_or_reuse_index_job(
            session, meeting_id=meeting_id, input_sha256=analysis.memory_sha256, settings=settings
        )
        current = (
            await session.execute(
                select(MemoryChunk.index_job_id)
                .where(MemoryChunk.meeting_id == meeting_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if index_job.status == "completed" and current != index_job.id:
            # The same input was indexed before, then replaced (notes A -> B -> A): index again.
            index_job = await memory_jobs.create_or_reuse_index_job(
                session,
                meeting_id=meeting_id,
                input_sha256=analysis.memory_sha256,
                settings=settings,
                force=True,
            )
        if index_job.status == "queued":
            queued.append(("index", index_job.id))
    runtime = runtime_settings.load(settings)
    brain_job = None
    if runtime.llm_configured:
        brain_job = await brain_jobs.create_or_reuse(
            session,
            meeting_id=meeting_id,
            input_sha256=analysis.brain_sha256,
            runtime=runtime,
            settings=settings,
        )
        latest = (
            await session.execute(
                select(BrainExtraction.job_id)
                .where(BrainExtraction.meeting_id == meeting_id)
                .order_by(BrainExtraction.generated_at.desc(), BrainExtraction.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if brain_job.status == "completed" and latest != brain_job.id:
            # An earlier extraction for this same input was superseded by a newer one: run it
            # again so it becomes the latest (the graph projects only the latest extraction).
            brain_job = await brain_jobs.create_or_reuse(
                session,
                meeting_id=meeting_id,
                input_sha256=analysis.brain_sha256,
                runtime=runtime,
                settings=settings,
                force=True,
            )
        if brain_job.status == "queued":
            queued.append(("brain", brain_job.id))
    await session.commit()
    for kind, job_id in queued:
        if kind == "brain":
            await brain_jobs.publish(request.app.state.brain_queue, job_id)
        else:
            await memory_jobs.publish(request.app.state.memory_index_queue, job_id, "index")
    if not runtime.llm_configured:
        return "llm_not_configured"
    return "queued" if queued else "unchanged"
