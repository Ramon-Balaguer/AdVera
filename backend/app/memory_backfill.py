"""Historical backfill (historical-memory-backfill.md).

Creates Memory index jobs, and with `--brain` Brain jobs, for every meeting whose definitive
transcript has no up-to-date projection. Idempotent: an existing job for the same input is
reused, so running it twice creates nothing new. Only definitive transcripts are considered.

`--concepts` fills the concept graph: it queues Brain extraction (the current prompt extracts
concepts), and each completed extraction schedules its own concept projection. `--reproject`
projects each meeting's latest stored extraction again, without calling the model: for a change
in the projection itself (identity, mentions, aliases). `--meeting ID` (repeatable)
limits the run to those meetings and `--exclude-title TITLE` (repeatable) skips meetings with
that exact title, for meetings that must not be reprocessed.

Usage: python -m app.memory_backfill [--brain|--concepts|--reproject] [--rebuild]
       [--meeting ID] [--exclude-title TITLE]
"""

import argparse
import asyncio
import logging

from sqlalchemy import select

from app import brain_jobs, memory_jobs, runtime_settings
from app.config import get_settings
from app.database import create_engine, create_sessionmaker
from app.job_queue import RedisStreamQueue, create_redis
from app.memory_worker import INDEX_GROUP
from app.models import BrainExtraction, BrainJob, Meeting
from app.storage import MeetingStorage
from app.transcripts import parse_definitive

logger = logging.getLogger("advera.memory_backfill")


async def backfill(
    with_brain: bool,
    rebuild: bool,
    meeting_ids: list[str] | None = None,
    exclude_titles: list[str] | None = None,
    reproject: bool = False,
) -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    storage = MeetingStorage(settings.audio_storage_path)
    index_queue = RedisStreamQueue(redis, settings.memory_index_queue_name, INDEX_GROUP)
    brain_queue = RedisStreamQueue(redis, settings.brain_queue_name, "brain-workers")
    runtime = runtime_settings.load(settings)
    counts = {"meetings": 0, "index_jobs": 0, "brain_jobs": 0, "concept_jobs": 0}
    try:
        async with create_sessionmaker(engine)() as session:
            meetings = (await session.execute(select(Meeting))).scalars().all()
            skipped_titles = {title.strip().lower() for title in exclude_titles or []}
            for meeting in meetings:
                if meeting_ids and meeting.id not in meeting_ids:
                    continue
                if meeting.title.strip().lower() in skipped_titles:
                    continue
                transcript = parse_definitive(storage.read_transcript(meeting.id))
                if transcript is None:
                    continue
                counts["meetings"] += 1
                if reproject:
                    job = await _reproject(session, meeting.id, settings)
                    await session.commit()
                    if job is not None and job.status == "queued":
                        await index_queue.publish(job.id)
                        counts["concept_jobs"] += 1
                    continue
                index_job = await memory_jobs.create_or_reuse_index_job(
                    session,
                    meeting_id=meeting.id,
                    input_sha256=transcript.segments_sha256,
                    settings=settings,
                    force=rebuild,
                )
                brain_job = None
                if with_brain and runtime.llm_configured:
                    brain_job = await brain_jobs.create_or_reuse(
                        session,
                        meeting_id=meeting.id,
                        input_sha256=transcript.segments_sha256,
                        runtime=runtime,
                        settings=settings,
                        force=rebuild,
                    )
                await session.commit()
                if index_job.status == "queued":
                    await index_queue.publish(index_job.id)
                    counts["index_jobs"] += 1
                if brain_job is not None and brain_job.status == "queued":
                    await brain_queue.publish(brain_job.id)
                    counts["brain_jobs"] += 1
    finally:
        await redis.aclose()
        await engine.dispose()
    return counts


async def _reproject(session, meeting_id: str, settings):
    """Queue the projection of the meeting's latest extraction again (no model call)."""
    latest = (
        await session.execute(
            select(BrainExtraction)
            .where(BrainExtraction.meeting_id == meeting_id)
            .order_by(BrainExtraction.generated_at.desc(), BrainExtraction.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return None
    brain_job = await session.get(BrainJob, latest.job_id)
    if brain_job is None:
        return None
    return await memory_jobs.create_or_reuse_concept_job(
        session, brain_job=brain_job, settings=settings, force=True
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brain", action="store_true", help="also queue Brain extraction")
    parser.add_argument(
        "--concepts",
        action="store_true",
        help="queue Brain extraction to fill the concept graph",
    )
    parser.add_argument(
        "--reproject",
        action="store_true",
        help="project the latest stored extractions into the concept graph again (no model)",
    )
    parser.add_argument("--meeting", action="append", help="only this meeting id (repeatable)")
    parser.add_argument(
        "--exclude-title", action="append", help="skip meetings with this exact title (repeatable)"
    )
    parser.add_argument("--rebuild", action="store_true", help="re-run completed jobs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(
        asyncio.run(
            backfill(
                args.brain or args.concepts,
                args.rebuild,
                args.meeting,
                args.exclude_title,
                args.reproject,
            )
        )
    )


if __name__ == "__main__":
    main()
