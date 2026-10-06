"""Brain worker: indexing and cited queries (docs/redis.md §3-4; ADR 0001, 0002).

Consumes `advera:brain:index` and `advera:brain:query` in one process.

Indexing validates that the transcript is definitive and still matches the job hash, replaces
the meeting's chunks and evidence atomically, and embeds the chunks with BGE-M3. When
embeddings are unavailable the text chunks are still stored (full-text search keeps
working) and the job completes with `EMBEDDINGS_UNAVAILABLE` recorded, so the index shows as
partial.

Queries move through `retrieving` and `synthesizing`. No retrieved evidence gives `empty`
without calling the LLM. An unavailable LLM gives `failed` with the retrieved sources kept,
and never an invented answer. Logs carry ids and codes only.

Run with `python -m app.brain_worker`.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import analysis_input, leases
from app.brain_answer import (
    NO_MATCH,
    NO_SEGMENTS,
    answer_schema,
    build_context,
    no_answer_reason,
    system_prompt,
    validate_answer,
)
from app.brain_indexing import PROJECTION_VERSION, build_chunks, note_chunks
from app.brain_retrieval import Filters, retrieve
from app.concepts import (
    attach,
    canonical_key,
    link_relationship,
    lock_concepts,
    prune_aliases,
    prune_orphans,
    refresh_types,
    resolve_concept,
)
from app.config import Settings, get_settings
from app.consumer import consume
from app.database import create_engine, create_sessionmaker
from app.embeddings import BgeM3Provider, EmbeddingProvider, EmbeddingUnavailable
from app.job_queue import (
    BRAIN_INDEX_GROUP,
    BRAIN_QUERY_GROUP,
    JobQueue,
    RedisStreamQueue,
    create_redis,
)
from app import runtime_settings
from app.llm import LLMError, LLMProvider, provider_for
from app.models import (
    EMBEDDING_DIMENSION,
    BrainChunk,
    BrainConcept,
    BrainConceptMention,
    BrainConceptRelationshipOccurrence,
    BrainEvidence,
    BrainFact,
    BrainIndexJob,
    BrainQueryRun,
    SummaryExtraction,
    utcnow,
)
from app.storage import MeetingStorage
from app.transcripts import parse_definitive

logger = logging.getLogger("advera.brain_worker")

INDEX_GROUP = BRAIN_INDEX_GROUP
QUERY_GROUP = BRAIN_QUERY_GROUP
QUERY_STATUSES = ("retrieving", "synthesizing")
LLMFactory = Callable[[BrainQueryRun, Settings], LLMProvider]


def default_llm(run: BrainQueryRun, settings: Settings) -> LLMProvider:
    return provider_for(
        run.provider,
        run.base_url,
        run.model,
        settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
        api_key=runtime_settings.load(settings).llm_api_key,
    )


FACT_KINDS = {
    "decisions": "decision",
    "actions": "action",
    "risks": "risk",
    "open_questions": "question",
    "topics": "topic",
}


def project_facts(result: dict, meeting_id: str, summary_job_id: str) -> list[BrainFact]:
    """The facts of a Summary result as rows (ADR 0024); an empty or odd item is skipped."""
    facts: list[BrainFact] = []
    for category, kind in FACT_KINDS.items():
        for position, item in enumerate(result.get(category) or []):
            text_ = (item or {}).get("text")
            if not isinstance(text_, str) or not text_.strip():
                continue
            facts.append(
                BrainFact(
                    meeting_id=meeting_id,
                    summary_job_id=summary_job_id,
                    kind=kind,
                    position=position,
                    text=text_.strip(),
                    state=item.get("state") if kind == "decision" else None,
                    owner=(item.get("owner") or None) and str(item["owner"])[:200],
                    due_date=(item.get("due_date") or None) and str(item["due_date"])[:100],
                    evidence=list(item.get("evidence") or []),
                )
            )
    return facts


class Failure(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class BrainIndexWorker:
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
            if not await leases.claim(session, BrainIndexJob, job_id, token):
                return
            job = await session.get(BrainIndexJob, job_id)
        if job is None:
            return
        try:
            await self._run(job, token)
        except leases.LeaseLost:
            logger.warning("brain index job %s lost its lease", job_id)
        except Failure as failure:
            await self._fail(job, token, failure)
        except Exception as error:
            logger.error("brain index job %s internal error: %s", job_id, type(error).__name__)
            await self._fail(job, token, Failure("INTERNAL_ERROR", retryable=True))

    async def _run(self, job: BrainIndexJob, token: str) -> None:
        if job.kind == "concepts":
            await self._run_concepts(job, token)
            return
        async with self.sessionmaker() as session:
            analysis = await analysis_input.load(session, self.storage, job.meeting_id)
        if analysis is None:
            raise Failure("TRANSCRIPT_UNAVAILABLE", retryable=False)
        transcript = analysis.transcript
        if analysis.brain_sha256 != job.input_sha256:
            raise Failure("INPUT_CHANGED", retryable=False)  # transcript or notes changed
        chunks = [
            *build_chunks(transcript),
            *note_chunks([(block.id, analysis.note_text(block)) for block in analysis.notes]),
        ]

        vectors = None
        embedding_error = None
        if self.embeddings is not None and chunks:
            try:
                vectors = await leases.with_heartbeat(
                    asyncio.to_thread(self.embeddings.encode, [chunk.content for chunk in chunks]),
                    self._beat(job.id, token),
                    self.settings.summary_heartbeat_seconds,
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
                delete(BrainEvidence).where(BrainEvidence.meeting_id == job.meeting_id)
            )
            await session.execute(delete(BrainChunk).where(BrainChunk.meeting_id == job.meeting_id))
            for index, chunk in enumerate(chunks):
                row = BrainChunk(
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
                        BrainEvidence(
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
                BrainIndexJob,
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
            "brain index job %s completed: %s chunks, embeddings=%s",
            job.id,
            len(chunks),
            vectors is not None,
        )

    async def _run_concepts(self, job: BrainIndexJob, token: str) -> None:
        """Project one Summary extraction into the concept graph (ADR 0019).

        The meeting's previous mentions and occurrences are replaced in one transaction.
        Concepts and relationships are global: they are created once and kept when a meeting
        stops mentioning them (a concept with no mention or tag is simply not shown).
        """
        async with self.sessionmaker() as session:
            analysis = await analysis_input.load(
                session, self.storage, job.meeting_id, expand=False
            )
        if analysis is None:
            raise Failure("TRANSCRIPT_UNAVAILABLE", retryable=False)
        if analysis.summary_sha256 != job.input_sha256:
            raise Failure("INPUT_CHANGED", retryable=False)  # transcript, notes or names changed
        async with self.sessionmaker() as session:
            # One projection per meeting at a time: two workers replacing the same meeting's
            # mentions concurrently could interleave (review finding). Checked again under it.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"concepts:{job.meeting_id}"},
            )
            await lock_concepts(session)
            extractions = (
                (
                    await session.execute(
                        select(SummaryExtraction)
                        .where(SummaryExtraction.meeting_id == job.meeting_id)
                        .order_by(
                            SummaryExtraction.generated_at.desc(), SummaryExtraction.id.desc()
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not extractions or extractions[0].job_id != job.source_summary_job_id:
                # A newer extraction exists (or this one is gone): it is not projected over it.
                raise Failure("STALE_EXTRACTION", retryable=False)
            extraction = extractions[0]
            result = extraction.result or {}

            previous = set(
                (
                    await session.execute(
                        select(BrainConceptMention.concept_id).where(
                            BrainConceptMention.meeting_id == job.meeting_id
                        )
                    )
                ).scalars()
            )
            await session.execute(
                delete(BrainConceptRelationshipOccurrence).where(
                    BrainConceptRelationshipOccurrence.meeting_id == job.meeting_id
                )
            )
            await session.execute(
                delete(BrainConceptMention).where(BrainConceptMention.meeting_id == job.meeting_id)
            )
            await session.execute(delete(BrainFact).where(BrainFact.meeting_id == job.meeting_id))
            session.add_all(project_facts(result, job.meeting_id, extraction.job_id))
            by_key: dict[str, BrainConcept] = {}
            resolved: list[tuple[BrainConcept, dict]] = []
            for entry in result.get("concepts", []):
                concept = await resolve_concept(
                    session,
                    entry["type"],
                    entry["name"],
                    aliases=entry.get("aliases", []),
                    source_sha256=job.input_sha256,
                    attach_aliases=False,
                )
                if concept is None:
                    continue
                by_key.setdefault(canonical_key(entry["name"]), concept)
                resolved.append((concept, entry))
            # Two names of one output can resolve to one concept: it gets one mention.
            mentions: dict[str, BrainConceptMention] = {}
            for concept, entry in resolved:
                await attach(session, concept, entry.get("aliases", []), job.input_sha256)
                mention = mentions.get(concept.id)
                if mention is None:
                    mentions[concept.id] = BrainConceptMention(
                        concept_id=concept.id,
                        meeting_id=job.meeting_id,
                        summary_job_id=extraction.job_id,
                        mention=entry["name"][:200],
                        concept_type=entry["type"],
                        evidence=list(entry.get("evidence", [])),
                    )
                else:
                    seen = {e["segment_id"] for e in mention.evidence}
                    mention.evidence = mention.evidence + [
                        e for e in entry.get("evidence", []) if e["segment_id"] not in seen
                    ]
            session.add_all(mentions.values())
            relationships = 0
            for entry in result.get("relationships", []):
                source = by_key.get(canonical_key(entry["source"]))
                target = by_key.get(canonical_key(entry["target"]))
                if source is None or target is None or source.id == target.id:
                    continue
                relationship = await link_relationship(
                    session, source.id, target.id, entry["type"], "summary"
                )
                session.add(
                    BrainConceptRelationshipOccurrence(
                        relationship_id=relationship.id,
                        meeting_id=job.meeting_id,
                        summary_job_id=extraction.job_id,
                        evidence=entry.get("evidence", []),
                    )
                )
                relationships += 1
            await session.flush()
            await refresh_types(session, previous | set(mentions))
            await prune_aliases(session)
            await prune_orphans(session)  # concepts this meeting no longer mentions, if alone
            done = await leases.fenced_update(
                session,
                BrainIndexJob,
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
        logger.info(
            "concept projection %s completed: %s concepts, %s relationships",
            job.id,
            len(by_key),
            relationships,
        )

    def _beat(self, job_id: str, token: str):
        async def beat() -> None:
            async with self.sessionmaker() as session:
                if not await leases.fenced_update(session, BrainIndexJob, job_id, token):
                    raise leases.LeaseLost
                await session.commit()

        return beat

    async def _fail(self, job: BrainIndexJob, token: str, failure: Failure) -> None:
        async with self.sessionmaker() as session:
            current = await session.get(BrainIndexJob, job.id)
            if current is None or current.lease_token != token:
                return
            retry = failure.retryable and current.attempts < current.max_attempts
            values = {"lease_token": None, "error": failure.code}
            values |= (
                {"status": "queued"} if retry else {"status": "failed", "completed_at": utcnow()}
            )
            if not await leases.fenced_update(session, BrainIndexJob, job.id, token, **values):
                return
            await session.commit()
        logger.warning(
            "brain index job %s %s: %s", job.id, "requeued" if retry else "failed", failure.code
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
                BrainIndexJob,
                lease_seconds=self.settings.summary_lease_seconds,
                republish_after_seconds=self.settings.transcription_reconcile_seconds,
            )
        for job_id in job_ids:
            await self.queue.publish(job_id)


class BrainQueryWorker:
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
                session, BrainQueryRun, run_id, token, running_statuses=QUERY_STATUSES, **values
            ):
                raise leases.LeaseLost
            await session.commit()

    async def process(self, run_id: str) -> None:
        token = str(uuid.uuid4())
        async with self.sessionmaker() as session:
            if not await leases.claim(
                session, BrainQueryRun, run_id, token, running_status="retrieving"
            ):
                return
            run = await session.get(BrainQueryRun, run_id)
        if run is None:
            return
        try:
            await self._run(run, token)
        except leases.LeaseLost:
            logger.warning("brain query %s lost its lease", run_id)
        except Exception as error:
            logger.error("brain query %s internal error: %s", run_id, type(error).__name__)
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

    async def _run(self, run: BrainQueryRun, token: str) -> None:
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
            # Speakers named as people (ADR 0021) show and are quoted by name.
            names = await analysis_input.people_for(
                session, sorted({chunk["meeting_id"] for chunk in retrieved})
            )
        for chunk in retrieved:
            chunk["person"] = names.get(chunk["meeting_id"], {}).get(
                (chunk["track"], chunk["speaker"] or "")
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
            # LLM is not called (brain-global.md).
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
                self.settings.summary_heartbeat_seconds,
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
            logger.warning("brain query %s failed: %s", run.id, error.code)
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
        logger.info("brain query %s %s: %s sources", run.id, status, len(sources))

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            job_ids = await leases.reconcile(
                session,
                BrainQueryRun,
                lease_seconds=self.settings.summary_lease_seconds,
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
            "person",
            "track",
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
    index_queue = RedisStreamQueue(redis, settings.brain_index_queue_name, INDEX_GROUP)
    query_queue = RedisStreamQueue(redis, settings.brain_query_queue_name, QUERY_GROUP)
    index_worker = BrainIndexWorker(sessionmaker, storage, index_queue, settings, embeddings)
    query_worker = BrainQueryWorker(sessionmaker, storage, query_queue, settings, embeddings)
    logger.info("brain worker started")
    try:
        await asyncio.gather(
            consume(index_queue, index_worker, settings, stop, name="brain-index"),
            consume(query_queue, query_worker, settings, stop, name="brain-query"),
        )
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
