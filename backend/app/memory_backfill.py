"""Historical backfill (historical-memory-backfill.md).

Creates Memory index jobs, and with `--brain` Brain jobs, for every meeting whose definitive
transcript has no up-to-date projection. Idempotent: an existing job for the same input is
reused, so running it twice creates nothing new. Only definitive transcripts are considered.

Usage: python -m app.memory_backfill [--brain] [--rebuild]
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
from app.models import Meeting
from app.storage import MeetingStorage
from app.transcripts import parse_definitive

logger = logging.getLogger("advera.memory_backfill")


async def backfill(with_brain: bool, rebuild: bool) -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    storage = MeetingStorage(settings.audio_storage_path)
    index_queue = RedisStreamQueue(redis, settings.memory_index_queue_name, INDEX_GROUP)
    brain_queue = RedisStreamQueue(redis, settings.brain_queue_name, "brain-workers")
    runtime = runtime_settings.load(settings)
    counts = {"meetings": 0, "index_jobs": 0, "brain_jobs": 0}
    try:
        async with create_sessionmaker(engine)() as session:
            meetings = (await session.execute(select(Meeting))).scalars().all()
            for meeting in meetings:
                transcript = parse_definitive(storage.read_transcript(meeting.id))
                if transcript is None:
                    continue
                counts["meetings"] += 1
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brain", action="store_true", help="also queue Brain extraction")
    parser.add_argument("--rebuild", action="store_true", help="re-run completed jobs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(backfill(args.brain, args.rebuild)))


if __name__ == "__main__":
    main()
