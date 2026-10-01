"""Queue the text analysis of a meeting again after its notes or speakers' names changed.

Only the text stages run again (Brain, its concept projection, Memory chunks); the audio is
never processed again. Jobs are keyed by what they read (`analysis_input`), so saving the same
content twice queues nothing new.
"""

import logging
from typing import Literal

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import analysis_input, brain_jobs, memory_jobs, runtime_settings
from app.config import Settings

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
