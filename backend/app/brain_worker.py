"""Brain worker (docs/redis.md §2; ADR 0002, 0009).

Consumes `advera:brain:jobs`. The worker re-validates that the persisted transcript is
definitive and still matches the job's input hash before calling the LLM, so it never uses
stale or provisional input. It persists an `LLMRun` for every provider call (final output
only) and a `BrainExtraction` for a valid result. Provider and invalid-output failures retry
up to `max_attempts`; configuration and oversized-input failures are terminal. A Brain failure
never touches the transcript or audio. Logs carry ids and codes only.

Run with `python -m app.brain_worker`.
"""

import asyncio
import logging
import socket
import time
import uuid
from collections.abc import Callable

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import analysis_input, leases, memory_jobs
from app.brain import (
    OUTPUT_RESERVE_TOKENS,
    BrainValidationError,
    build_prompt,
    build_relations_prompt,
    merge_relations,
    output_schema,
    relations_schema,
    transcript_seconds,
    validate_output,
)
from app.config import Settings, get_settings
from app.database import create_engine, create_sessionmaker
from app.job_queue import JobQueue, RedisStreamQueue, create_redis
from app.llm import LLMError, LLMProvider, OllamaProvider, estimate_tokens
from app.models import BrainExtraction, BrainJob, LLMRun, utcnow
from app.storage import MeetingStorage

logger = logging.getLogger("advera.brain_worker")

CONSUMER_GROUP = "brain-workers"
ProviderFactory = Callable[[BrainJob, Settings], LLMProvider]


def default_provider(job: BrainJob, settings: Settings) -> LLMProvider:
    if job.provider != "ollama":
        raise LLMError("UNKNOWN_LLM_PROVIDER")
    return OllamaProvider(
        job.base_url,
        job.model,
        settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
    )


class BrainFailure(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class BrainWorker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: MeetingStorage,
        queue: JobQueue,
        settings: Settings,
        provider_factory: ProviderFactory = default_provider,
        on_completed: Callable[[BrainJob], object] | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.storage = storage
        self.queue = queue
        self.settings = settings
        self.provider_factory = provider_factory
        self.on_completed = on_completed

    async def _write(self, job_id: str, token: str, **values) -> None:
        async with self.sessionmaker() as session:
            if not await leases.fenced_update(session, BrainJob, job_id, token, **values):
                raise leases.LeaseLost
            await session.commit()

    async def process(self, job_id: str) -> None:
        token = str(uuid.uuid4())
        async with self.sessionmaker() as session:
            if not await leases.claim(session, BrainJob, job_id, token):
                return
            job = await session.get(BrainJob, job_id)
        if job is None:
            return
        logger.info("brain job %s claimed (attempt %s)", job_id, job.attempts)
        try:
            await self._run(job, token)
        except leases.LeaseLost:
            logger.warning("brain job %s lost its lease", job_id)
        except BrainFailure as failure:
            await self._fail(job, token, failure)
        except Exception as error:
            logger.error("brain job %s internal error: %s", job_id, type(error).__name__)
            await self._fail(job, token, BrainFailure("INTERNAL_ERROR", retryable=True))

    async def _run(self, job: BrainJob, token: str) -> None:
        async with self.sessionmaker() as session:
            analysis = await analysis_input.load(session, self.storage, job.meeting_id)
        if analysis is None:
            raise BrainFailure("TRANSCRIPT_UNAVAILABLE", retryable=False)
        transcript = analysis.transcript
        if analysis.brain_sha256 != job.input_sha256:
            # The transcript, the notes or the speakers' names changed after the job was
            # created: this job is stale (a newer one was queued with the change).
            raise BrainFailure("INPUT_CHANGED", retryable=False)

        system, user = build_prompt(
            transcript,
            job.language,
            people=analysis.people,
            notes=[(block.id, block.text) for block in analysis.notes],
            context=[
                (block_id, line)
                for block_id, lines in analysis.expansions.items()
                for line in lines
            ],
        )
        context = self.settings.llm_context_tokens
        if estimate_tokens(system + user) + OUTPUT_RESERVE_TOKENS > context:
            raise BrainFailure("TRANSCRIPT_TOO_LONG", retryable=False)  # never truncate silently

        try:
            provider = self.provider_factory(job, self.settings)
        except LLMError as error:
            raise BrainFailure(error.code, retryable=False) from None

        run = LLMRun(
            job_id=job.id,
            provider=job.provider,
            model=job.model,
            prompt_version=job.prompt_version,
            input_sha256=job.input_sha256,
            status="running",
        )
        async with self.sessionmaker() as session:
            session.add(run)
            await session.commit()

        try:

            async def beat() -> None:
                await self._write(job.id, token)

            try:
                llm = await leases.with_heartbeat(
                    provider.complete_json(
                        system,
                        user,
                        output_schema(transcript_seconds(transcript)),
                        context_tokens=context,
                    ),
                    beat,
                    self.settings.brain_heartbeat_seconds,
                )
            except LLMError as error:
                await self._finish_run(run.id, "failed", error=error.code)
                raise BrainFailure(error.code, retryable=error.retryable) from None

            try:
                result, status = validate_output(
                    llm.parsed, transcript, job.language, analysis.notes
                )
            except BrainValidationError as error:
                await self._finish_run(run.id, "failed", raw=llm.raw, error=error.code)
                raise BrainFailure(error.code, retryable=True) from None

            await self._relations_pass(job, provider, analysis, result, beat)

            async with self.sessionmaker() as session:
                stored = await session.get(LLMRun, run.id)
                stored.status = "completed"
                stored.raw_output = llm.raw
                stored.output = llm.parsed
                stored.completed_at = utcnow()
                session.add(
                    BrainExtraction(
                        meeting_id=job.meeting_id,
                        job_id=job.id,
                        llm_run_id=run.id,
                        status=status,
                        input_sha256=job.input_sha256,
                        result=result,
                    )
                )
                done = await leases.fenced_update(
                    session,
                    BrainJob,
                    job.id,
                    token,
                    status="completed",
                    lease_token=None,
                    completed_at=utcnow(),
                )
                if not done:
                    await session.rollback()
                    raise leases.LeaseLost
                await session.commit()
            counts = {key: len(result[key]) for key in ("decisions", "actions", "topics")}
            logger.info("brain job %s %s: %s", job.id, status, counts)
            if self.on_completed is not None:
                await self.on_completed(job)
        except leases.LeaseLost:
            # The job was taken over or reconciled while the model ran: the run must not stay
            # "running" forever (its own session, because the job transaction rolled back).
            await self._finish_run(run.id, "failed", error="LEASE_LOST")
            raise
        except BaseException as error:
            # Anything else (database error, shutdown, a failing completion hook) must not leave
            # the run "running" either. Runs already closed above are left as they are.
            await self._close_open_run(run.id, type(error).__name__)
            raise

    async def _relations_pass(self, job, provider, analysis, result, beat) -> None:
        """Second request: only the relationships between the concepts already found.

        The first request does everything at once and gives few, mostly generic, relationships.
        This one is best effort: if it fails, the extraction keeps what the first one found, and
        the failure is recorded on its own run and in the result, never as a failed job.
        """
        concepts = result["concepts"]
        if len(concepts) < 2:
            return
        transcript = analysis.transcript
        system, user = build_relations_prompt(
            transcript,
            concepts,
            result["relationships"],
            people=analysis.people,
            notes=[(block.id, block.text) for block in analysis.notes],
            context=[
                (block_id, line)
                for block_id, lines in analysis.expansions.items()
                for line in lines
            ],
        )
        context = self.settings.llm_context_tokens
        if estimate_tokens(system + user) + OUTPUT_RESERVE_TOKENS > context:
            result["relations_pass"] = {"status": "skipped", "added": 0}
            return
        run = LLMRun(
            job_id=job.id,
            provider=job.provider,
            model=job.model,
            prompt_version=f"{job.prompt_version}:relations",
            input_sha256=job.input_sha256,
            status="running",
        )
        async with self.sessionmaker() as session:
            session.add(run)
            await session.commit()
        try:
            # A new prompt is read from scratch by the model, which can take longer than a
            # reverse proxy in front of it waits before cutting the request; the model keeps
            # what it read, so a second try starts writing at once. Hence one retry.
            for attempt in (1, 2):
                try:
                    llm = await leases.with_heartbeat(
                        provider.complete_json(
                            system,
                            user,
                            relations_schema(transcript_seconds(transcript)),
                            context_tokens=context,
                        ),
                        beat,
                        self.settings.brain_heartbeat_seconds,
                    )
                    break
                except LLMError as error:
                    if attempt == 2 or not error.retryable:
                        raise
                    logger.info("brain job %s relations pass retried after %s", job.id, error.code)
            added = merge_relations(result, llm.parsed, transcript, analysis.notes)
        except (LLMError, BrainValidationError) as error:
            await self._finish_run(run.id, "failed", error=error.code)
            result["relations_pass"] = {"status": "failed", "added": 0, "error": error.code}
            logger.warning("brain job %s relations pass failed: %s", job.id, error.code)
            return
        except BaseException as error:
            await self._close_open_run(run.id, type(error).__name__)
            raise
        async with self.sessionmaker() as session:
            stored = await session.get(LLMRun, run.id)
            stored.status = "completed"
            stored.raw_output = llm.raw
            stored.output = llm.parsed
            stored.completed_at = utcnow()
            await session.commit()
        result["relations_pass"] = {"status": "completed", "added": added}
        logger.info("brain job %s relations pass: %s added", job.id, added)

    async def _close_open_run(self, run_id: str, cause: str) -> None:
        """Close a run that is still `running`; shielded so a cancelled worker still records it."""

        async def close() -> None:
            async with self.sessionmaker() as session:
                run = await session.get(LLMRun, run_id)
                if run is not None and run.status == "running":
                    run.status = "failed"
                    run.error = "INTERRUPTED"
                    run.completed_at = utcnow()
                    await session.commit()

        try:
            await asyncio.shield(close())
        except Exception as error:  # never mask the original failure
            logger.warning(
                "llm run %s not closed after %s: %s", run_id, cause, type(error).__name__
            )

    async def _finish_run(self, run_id: str, status: str, *, raw=None, error=None) -> None:
        async with self.sessionmaker() as session:
            run = await session.get(LLMRun, run_id)
            if run is not None:
                run.status = status
                run.raw_output = raw
                run.error = error
                run.completed_at = utcnow()
                await session.commit()

    async def _fail(self, job: BrainJob, token: str, failure: BrainFailure) -> None:
        async with self.sessionmaker() as session:
            current = await session.get(BrainJob, job.id)
            if current is None or current.lease_token != token or current.status != "running":
                return
            retry = failure.retryable and current.attempts < current.max_attempts
            values = {"lease_token": None, "error": failure.code}
            values |= (
                {"status": "queued"} if retry else {"status": "failed", "completed_at": utcnow()}
            )
            if not await leases.fenced_update(session, BrainJob, job.id, token, **values):
                return
            await session.commit()
        if retry:
            logger.warning("brain job %s requeued: %s", job.id, failure.code)
            try:
                await self.queue.publish(job.id)
            except Exception as error:
                logger.warning("brain job %s republish deferred: %s", job.id, type(error).__name__)
        else:
            logger.warning("brain job %s failed: %s", job.id, failure.code)

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            job_ids = await leases.reconcile(
                session,
                BrainJob,
                lease_seconds=self.settings.brain_lease_seconds,
                republish_after_seconds=self.settings.transcription_reconcile_seconds,
            )
        for job_id in job_ids:
            await self.queue.publish(job_id)


async def consume(queue: RedisStreamQueue, worker, settings: Settings, stop: asyncio.Event) -> None:
    """Shared consumer loop: replay own pending entries, reconcile periodically, survive Redis."""
    consumer = socket.gethostname()
    read_pending = True
    last_reconcile = 0.0
    while not stop.is_set():
        try:
            await queue.ensure_group()
            if time.monotonic() - last_reconcile >= settings.transcription_reconcile_seconds:
                await worker.reconcile()
                last_reconcile = time.monotonic()
            messages = await queue.read(consumer, pending=read_pending)
            read_pending = read_pending and bool(messages)
            for message_id, job_id in messages:
                try:
                    if job_id:
                        await worker.process(job_id)
                finally:
                    await queue.ack(message_id)
        except (RedisError, OSError) as error:
            logger.warning("worker waiting for Redis: %s", type(error).__name__)
            await asyncio.sleep(5)


async def run(settings: Settings, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    queue = RedisStreamQueue(redis, settings.brain_queue_name, CONSUMER_GROUP)
    sessionmaker = create_sessionmaker(engine)
    index_queue = RedisStreamQueue(redis, settings.memory_index_queue_name, "memory-index-workers")

    async def project_concepts(job: BrainJob) -> None:
        # A completed extraction feeds the concept graph (docs/redis.md: Brain triggers it).
        await memory_jobs.schedule_concept_projection(sessionmaker, index_queue, settings, job)

    worker = BrainWorker(
        sessionmaker,
        MeetingStorage(settings.audio_storage_path),
        queue,
        settings,
        on_completed=project_concepts,
    )
    logger.info("brain worker started")
    try:
        await consume(queue, worker, settings, stop)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
