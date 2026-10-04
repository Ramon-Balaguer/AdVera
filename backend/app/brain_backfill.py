"""Historical backfill (historical-brain-backfill.md).

Creates Brain index jobs, and with `--summary` Summary jobs, for every meeting whose definitive
transcript has no up-to-date projection. Idempotent: an existing job for the same input is
reused, so running it twice creates nothing new. Only definitive transcripts are considered.

`--concepts` fills the concept graph: it queues Summary extraction (the current prompt extracts
concepts), and each completed extraction schedules its own concept projection. `--reproject`
projects each meeting's latest stored extraction again, without calling the model: for a change
in the projection itself (identity, mentions, aliases). `--meeting ID` (repeatable)
limits the run to those meetings and `--exclude-title TITLE` (repeatable) skips meetings with
that exact title, for meetings that must not be reprocessed.

Usage: python -m app.brain_backfill [--summary|--concepts|--reproject] [--rebuild]
       [--meeting ID] [--exclude-title TITLE]
"""

import argparse
import asyncio
import logging

from sqlalchemy import select

from app import analysis_input, brain_jobs, runtime_settings, summary_jobs
from app.brain_worker import INDEX_GROUP
from app.config import get_settings
from app.database import create_engine, create_sessionmaker
from app.job_queue import RedisStreamQueue, create_redis
from app.models import Meeting, SummaryExtraction, SummaryJob
from app.storage import MeetingStorage

logger = logging.getLogger("advera.brain_backfill")


async def backfill(
    with_summary: bool,
    rebuild: bool,
    meeting_ids: list[str] | None = None,
    exclude_titles: list[str] | None = None,
    reproject: bool = False,
) -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    storage = MeetingStorage(settings.audio_storage_path)
    index_queue = RedisStreamQueue(redis, settings.brain_index_queue_name, INDEX_GROUP)
    summary_queue = RedisStreamQueue(redis, settings.summary_queue_name, "summary-workers")
    runtime = runtime_settings.load(settings)
    counts = {"meetings": 0, "index_jobs": 0, "summary_jobs": 0, "concept_jobs": 0}
    try:
        async with create_sessionmaker(engine)() as session:
            meetings = (await session.execute(select(Meeting))).scalars().all()
            skipped_titles = {title.strip().lower() for title in exclude_titles or []}
            for meeting in meetings:
                if meeting_ids and meeting.id not in meeting_ids:
                    continue
                if meeting.title.strip().lower() in skipped_titles:
                    continue
                analysis = await analysis_input.load(session, storage, meeting.id, expand=False)
                if analysis is None:
                    continue
                counts["meetings"] += 1
                if reproject:
                    job = await _reproject(session, meeting.id, settings)
                    await session.commit()
                    if job is not None and job.status == "queued":
                        await index_queue.publish(job.id)
                        counts["concept_jobs"] += 1
                    continue
                index_job = await brain_jobs.create_or_reuse_index_job(
                    session,
                    meeting_id=meeting.id,
                    input_sha256=analysis.brain_sha256,
                    settings=settings,
                    force=rebuild,
                )
                summary_job = None
                if with_summary and runtime.llm_configured:
                    summary_job = await summary_jobs.create_or_reuse(
                        session,
                        meeting_id=meeting.id,
                        input_sha256=analysis.summary_sha256,
                        runtime=runtime,
                        settings=settings,
                        force=rebuild,
                    )
                await session.commit()
                if index_job.status == "queued":
                    await index_queue.publish(index_job.id)
                    counts["index_jobs"] += 1
                if summary_job is not None and summary_job.status == "queued":
                    await summary_queue.publish(summary_job.id)
                    counts["summary_jobs"] += 1
    finally:
        await redis.aclose()
        await engine.dispose()
    return counts


async def _reproject(session, meeting_id: str, settings):
    """Queue the projection of the meeting's latest extraction again (no model call)."""
    latest = (
        await session.execute(
            select(SummaryExtraction)
            .where(SummaryExtraction.meeting_id == meeting_id)
            .order_by(SummaryExtraction.generated_at.desc(), SummaryExtraction.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return None
    summary_job = await session.get(SummaryJob, latest.job_id)
    if summary_job is None:
        return None
    return await brain_jobs.create_or_reuse_concept_job(
        session, summary_job=summary_job, settings=settings, force=True
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", action="store_true", help="also queue Summary extraction")
    parser.add_argument(
        "--concepts",
        action="store_true",
        help="queue Summary extraction to fill the concept graph",
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
                args.summary or args.concepts,
                args.rebuild,
                args.meeting,
                args.exclude_title,
                args.reproject,
            )
        )
    )


if __name__ == "__main__":
    main()
