"""Memory worker: indexing and cited queries (docs/redis.md §3-4; ADR 0001, 0002).

Consumes `advera:memory:index` and `advera:memory:query` in one process.

Indexing validates that the transcript is definitive and still matches the job hash, replaces
the meeting's chunks and evidence atomically, and embeds the chunks with BGE-M3. When
embeddings are unavailable the text chunks are still stored (full-text search keeps
working) and the job completes with `EMBEDDINGS_UNAVAILABLE` recorded, so the index shows as
partial.

Queries move through `retrieving` and `synthesizing`. No retrieved evidence gives `empty`
without calling the LLM. An unavailable LLM gives `failed` with the retrieved sources kept,
and never an invented answer. Logs carry ids and codes only.

Run with `python -m app.memory_worker`.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import leases
from app.brain_worker import consume
from app.config import Settings, get_settings
from app.database import create_engine, create_sessionmaker
from app.embeddings import BgeM3Provider, EmbeddingProvider, EmbeddingUnavailable
from app.job_queue import JobQueue, RedisStreamQueue, create_redis
from app.llm import LLMError, LLMProvider, OllamaProvider
from app.memory_answer import (
    NO_MATCH,
    NO_SEGMENTS,
    answer_schema,
    build_context,
    no_answer_reason,
    system_prompt,
    validate_answer,
)
from app.memory_indexing import PROJECTION_VERSION, build_chunks
from app.memory_retrieval import Filters, retrieve
from app.models import (
    EMBEDDING_DIMENSION,
    MemoryChunk,
    MemoryEvidence,
    MemoryIndexJob,
    MemoryQueryRun,
    utcnow,
)
from app.storage import MeetingStorage
from app.transcripts import parse_definitive

logger = logging.getLogger("advera.memory_worker")

INDEX_GROUP = "memory-index-workers"
QUERY_GROUP = "memory-query-workers"
QUERY_STATUSES = ("retrieving", "synthesizing")
LLMFactory = Callable[[MemoryQueryRun, Settings], LLMProvider]


def default_llm(run: MemoryQueryRun, settings: Settings) -> LLMProvider:
    return OllamaProvider(run.base_url, run.model, settings.llm_timeout_seconds)


class Failure(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class MemoryIndexWorker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: MeetingStorage,
        queue: JobQueue,
        settings: Settings,
        embeddings: EmbeddingProvider | None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.storage = storage
        self.queue = queue
        self.settings = settings
        self.embeddings = embeddings

    async def process(self, job_id: str) -> None:
        token = str(uuid.uuid4())
        async with self.sessionmaker() as session:
            if not await leases.claim(session, MemoryIndexJob, job_id, token):
                return
            job = await session.get(MemoryIndexJob, job_id)
        if job is None:
            return
        try:
            await self._run(job, token)
        except leases.LeaseLost:
            logger.warning("memory index job %s lost its lease", job_id)
        except Failure as failure:
            await self._fail(job, token, failure)
        except Exception as error:
            logger.error("memory index job %s internal error: %s", job_id, type(error).__name__)
            await self._fail(job, token, Failure("INTERNAL_ERROR", retryable=True))

    async def _run(self, job: MemoryIndexJob, token: str) -> None:
        transcript = parse_definitive(
            await asyncio.to_thread(self.storage.read_transcript, job.meeting_id)
        )
        if transcript is None:
            raise Failure("TRANSCRIPT_UNAVAILABLE", retryable=False)
        if transcript.segments_sha256 != job.input_sha256:
            raise Failure("INPUT_CHANGED", retryable=False)
        chunks = build_chunks(transcript)

        vectors = None
        embedding_error = None
        if self.embeddings is not None and chunks:
            try:
                vectors = await leases.with_heartbeat(
                    asyncio.to_thread(self.embeddings.encode, [chunk.content for chunk in chunks]),
                    self._beat(job.id, token),
                    self.settings.brain_heartbeat_seconds,
                )
            except EmbeddingUnavailable as error:
                if job.attempts < job.max_attempts:
                    raise Failure(error.code, retryable=True) from None
                embedding_error = error.code  # last attempt: keep full-text chunks
        elif self.embeddings is None:
            embedding_error = "EMBEDDINGS_DISABLED"

        async with self.sessionmaker() as session:
            # Replace the meeting's previous projection: derived data is regenerable (ADR 0001).
            await session.execute(
                delete(MemoryEvidence).where(MemoryEvidence.meeting_id == job.meeting_id)
            )
            await session.execute(
                delete(MemoryChunk).where(MemoryChunk.meeting_id == job.meeting_id)
            )
            for index, chunk in enumerate(chunks):
                row = MemoryChunk(
                    meeting_id=job.meeting_id,
                    index_job_id=job.id,
                    segment_id=chunk.segments[0].id,
                    source_segment_ids=[segment.id for segment in chunk.segments],
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    transcript_sha256=transcript.segments_sha256,
                    start_time=chunk.start,
                    end_time=chunk.end,
                    language=chunk.language,
                    speaker=chunk.speaker,
                    track=chunk.track,
                )
                if vectors is not None:
                    row.embedding = vectors[index].tolist()
                    row.embedding_dimension = EMBEDDING_DIMENSION
                    row.embedding_provider = self.embeddings.name
                    row.embedding_model = self.embeddings.model
                    row.embedding_model_version = self.embeddings.model_version
                session.add(row)
                await session.flush()
                for segment in chunk.segments:
                    session.add(
                        MemoryEvidence(
                            meeting_id=job.meeting_id,
                            index_job_id=job.id,
                            chunk_id=row.id,
                            segment_id=segment.id,
                            start_time=segment.start,
                            end_time=segment.end,
                            transcript_sha256=transcript.segments_sha256,
                            input_sha256=job.input_sha256,
                            projection_version=PROJECTION_VERSION,
                            provider=job.provider,
                            model=job.model,
                            model_version=job.model_version,
                        )
                    )
            done = await leases.fenced_update(
                session,
                MemoryIndexJob,
                job.id,
                token,
                status="completed",
                lease_token=None,
                error=embedding_error,
                completed_at=utcnow(),
            )
            if not done:
                await session.rollback()
                raise leases.LeaseLost
            await session.commit()
        logger.info(
            "memory index job %s completed: %s chunks, embeddings=%s",
            job.id,
            len(chunks),
            vectors is not None,
        )

    def _beat(self, job_id: str, token: str):
        async def beat() -> None:
            async with self.sessionmaker() as session:
                if not await leases.fenced_update(session, MemoryIndexJob, job_id, token):
                    raise leases.LeaseLost
                await session.commit()

        return beat

    async def _fail(self, job: MemoryIndexJob, token: str, failure: Failure) -> None:
        async with self.sessionmaker() as session:
            current = await session.get(MemoryIndexJob, job.id)
            if current is None or current.lease_token != token:
                return
            retry = failure.retryable and current.attempts < current.max_attempts
            values = {"lease_token": None, "error": failure.code}
            values |= (
                {"status": "queued"} if retry else {"status": "failed", "completed_at": utcnow()}
            )
            if not await leases.fenced_update(session, MemoryIndexJob, job.id, token, **values):
                return
            await session.commit()
        logger.warning(
            "memory index job %s %s: %s", job.id, "requeued" if retry else "failed", failure.code
        )
        if retry:
            try:
                await self.queue.publish(job.id)
            except Exception:
                pass

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            job_ids = await leases.reconcile(
                session,
                MemoryIndexJob,
                lease_seconds=self.settings.brain_lease_seconds,
                republish_after_seconds=self.settings.transcription_reconcile_seconds,
            )
        for job_id in job_ids:
            await self.queue.publish(job_id)


class MemoryQueryWorker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: MeetingStorage,
        queue: JobQueue,
        settings: Settings,
        embeddings: EmbeddingProvider | None,
        llm_factory: LLMFactory = default_llm,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.storage = storage
        self.queue = queue
        self.settings = settings
        self.embeddings = embeddings
        self.llm_factory = llm_factory

    async def _write(self, run_id: str, token: str, **values) -> None:
        async with self.sessionmaker() as session:
            if not await leases.fenced_update(
                session, MemoryQueryRun, run_id, token, running_statuses=QUERY_STATUSES, **values
            ):
                raise leases.LeaseLost
            await session.commit()

    async def process(self, run_id: str) -> None:
        token = str(uuid.uuid4())
        async with self.sessionmaker() as session:
            if not await leases.claim(
                session, MemoryQueryRun, run_id, token, running_status="retrieving"
            ):
                return
            run = await session.get(MemoryQueryRun, run_id)
        if run is None:
            return
        try:
            await self._run(run, token)
        except leases.LeaseLost:
            logger.warning("memory query %s lost its lease", run_id)
        except Exception as error:
            logger.error("memory query %s internal error: %s", run_id, type(error).__name__)
            try:
                await self._write(
                    run.id,
                    token,
                    status="failed",
                    error="INTERNAL_ERROR",
                    lease_token=None,
                    completed_at=utcnow(),
                )
            except leases.LeaseLost:
                pass

    async def _run(self, run: MemoryQueryRun, token: str) -> None:
        query_vector = None
        retrieval_mode = "text"
        if self.embeddings is not None:
            try:
                vectors = await asyncio.to_thread(self.embeddings.encode, [run.query])
                query_vector = vectors[0].tolist()
                retrieval_mode = "hybrid"
            except EmbeddingUnavailable:
                retrieval_mode = "text"  # full-text still answers (ADR 0001 rollback path)
        async with self.sessionmaker() as session:
            retrieved = await retrieve(
                session, run.query, query_vector, Filters.from_dict(run.filters or {}), run.top_k
            )
        base = {"retrieval": retrieval_mode, "retrieved": [_brief(chunk) for chunk in retrieved]}
        if not retrieved:
            await self._write(
                run.id,
                token,
                status="empty",
                lease_token=None,
                completed_at=utcnow(),
                result=base | {"answer": None, "sources": [], "reason": NO_MATCH},
            )
            return

        await self._write(run.id, token, status="synthesizing")
        transcripts = {}
        for meeting_id in {chunk["meeting_id"] for chunk in retrieved}:
            document = parse_definitive(
                await asyncio.to_thread(self.storage.read_transcript, meeting_id)
            )
            if document is not None:
                transcripts[meeting_id] = {
                    segment.id: segment.text for segment in document.segments
                }
        user, keys = build_context(run.query, retrieved, transcripts, run.language)
        if not keys:
            # Chunks were found but none resolves to a definitive segment: no evidence, and the
            # LLM is not called (brain-memoria-global.md).
            await self._write(
                run.id,
                token,
                status="empty",
                lease_token=None,
                completed_at=utcnow(),
                result=base | {"answer": None, "sources": [], "reason": NO_SEGMENTS},
            )
            return

        async def beat() -> None:
            await self._write(run.id, token)

        try:
            llm = self.llm_factory(run, self.settings)
            output = await leases.with_heartbeat(
                llm.complete_json(
                    system_prompt(run.language),
                    user,
                    answer_schema(),
                    context_tokens=self.settings.llm_context_tokens,
                ),
                beat,
                self.settings.brain_heartbeat_seconds,
            )
        except LLMError as error:
            await self._write(
                run.id,
                token,
                status="failed",
                error=error.code,
                lease_token=None,
                completed_at=utcnow(),
                result=base | {"answer": None, "sources": []},
            )
            logger.warning("memory query %s failed: %s", run.id, error.code)
            return
        answer, sources = validate_answer(output.parsed, keys)
        status = "completed" if answer else "empty"
        await self._write(
            run.id,
            token,
            status=status,
            lease_token=None,
            completed_at=utcnow(),
            result=base
            | {"answer": answer, "sources": sources}
            | ({} if answer else {"reason": no_answer_reason(output.parsed)}),
        )
        logger.info("memory query %s %s: %s sources", run.id, status, len(sources))

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            job_ids = await leases.reconcile(
                session,
                MemoryQueryRun,
                lease_seconds=self.settings.brain_lease_seconds,
                republish_after_seconds=self.settings.transcription_reconcile_seconds,
                running_statuses=QUERY_STATUSES,
            )
        for job_id in job_ids:
            await self.queue.publish(job_id)


def _brief(chunk: dict) -> dict:
    """What a retrieved chunk keeps in the query result, so that fragments the model could not
    use are still shown like sources: a link to the meeting at that second, with the text."""
    brief = {
        key: chunk[key]
        for key in (
            "chunk_id",
            "meeting_id",
            "meeting_title",
            "start",
            "end",
            "speaker",
            "language",
            "score",
            "matched",
            "content",
        )
    }
    evidence = chunk.get("evidence") or []
    brief["segment_id"] = evidence[0]["segment_id"] if evidence else None
    return brief


def build_embeddings(settings: Settings) -> EmbeddingProvider | None:
    if settings.embedding_provider == "none":
        return None
    return BgeM3Provider(
        settings.embedding_model, settings.embedding_device, settings.embedding_cache_dir
    )


async def run(settings: Settings, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    sessionmaker = create_sessionmaker(engine)
    storage = MeetingStorage(settings.audio_storage_path)
    embeddings = build_embeddings(settings)
    index_queue = RedisStreamQueue(redis, settings.memory_index_queue_name, INDEX_GROUP)
    query_queue = RedisStreamQueue(redis, settings.memory_query_queue_name, QUERY_GROUP)
    index_worker = MemoryIndexWorker(sessionmaker, storage, index_queue, settings, embeddings)
    query_worker = MemoryQueryWorker(sessionmaker, storage, query_queue, settings, embeddings)
    logger.info("memory worker started")
    try:
        await asyncio.gather(
            consume(index_queue, index_worker, settings, stop),
            consume(query_queue, query_worker, settings, stop),
        )
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
