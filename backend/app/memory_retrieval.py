"""Hybrid retrieval in PostgreSQL (postgresql-native-hybrid-memory-search.md; spec §14).

Both modalities run in SQL with every filter applied before ranking: full-text search on the
chunk text (`simple` configuration, multilingual) and pgvector cosine distance on the BGE-M3
embedding (HNSW). Each returns a bounded candidate list; the two lists are fused with
Reciprocal Rank Fusion, 1 / (60 + rank) per modality. The worker never loads the corpus.
When embeddings are unavailable, text-only retrieval still works.

Full text requires every term (`websearch_to_tsquery`): it is the precise keyword
complement to vector search (ADR 0001). OR-ing the terms was tried and rejected: `simple`
keeps stopwords, so long chunks matched "de", "la" or "per" and outranked relevant ones.
After fusion, chunks with the same content, speaker and start time (one recording imported
several times) are collapsed late, keeping the best-ranked one, so repeated identical content
cannot fill every context slot.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RRF_K = 60
CANDIDATES = 50
TSQUERY = "websearch_to_tsquery('simple', :query)"


@dataclass(frozen=True)
class Filters:
    meeting_ids: tuple[str, ...] = ()
    language: str | None = None
    speaker: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Filters":
        def parse(value):
            return datetime.fromisoformat(value) if value else None

        return cls(
            meeting_ids=tuple(data.get("meeting_ids") or ()),
            language=data.get("language") or None,
            speaker=data.get("speaker") or None,
            date_from=parse(data.get("date_from")),
            date_to=parse(data.get("date_to")),
        )


def _where(filters: Filters) -> tuple[str, dict[str, Any]]:
    clauses, params = [], {}
    if filters.meeting_ids:
        clauses.append("c.meeting_id = ANY(:meeting_ids)")
        params["meeting_ids"] = list(filters.meeting_ids)
    if filters.language:
        clauses.append("c.language = :language")
        params["language"] = filters.language
    if filters.speaker:
        clauses.append("c.speaker = :speaker")
        params["speaker"] = filters.speaker
    if filters.date_from:
        clauses.append("m.created_at >= :date_from")
        params["date_from"] = filters.date_from
    if filters.date_to:
        clauses.append("m.created_at <= :date_to")
        params["date_to"] = filters.date_to
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def fuse(*rankings: list[str], k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


async def retrieve(
    session: AsyncSession,
    query: str,
    query_vector: list[float] | None,
    filters: Filters,
    top_k: int,
) -> list[dict[str, Any]]:
    where, params = _where(filters)
    base = f"FROM memory_chunks c JOIN meetings m ON m.id = c.meeting_id WHERE TRUE{where}"
    text_ids = (
        (
            await session.execute(
                text(
                    f"""SELECT c.id {base}
                AND to_tsvector('simple', c.content) @@ {TSQUERY}
                ORDER BY ts_rank_cd(to_tsvector('simple', c.content), {TSQUERY}) DESC, c.id
                LIMIT :limit"""
                ),
                params | {"query": query, "limit": CANDIDATES},
            )
        )
        .scalars()
        .all()
    )
    vector_ids: list[str] = []
    if query_vector is not None:
        literal = "[" + ",".join(f"{value:.7f}" for value in query_vector) + "]"
        vector_ids = (
            (
                await session.execute(
                    text(
                        f"""SELECT c.id {base} AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> CAST(:vector AS vector), c.id LIMIT :limit"""
                    ),
                    params | {"vector": literal, "limit": CANDIDATES},
                )
            )
            .scalars()
            .all()
        )
    fused = fuse(list(text_ids), list(vector_ids))
    if not fused:
        return []
    rows = (
        (
            await session.execute(
                text(
                    """SELECT c.id, c.meeting_id, m.title, m.created_at, c.content, c.content_hash,
                          c.start_time, c.end_time, c.language, c.speaker, c.track,
                          c.source_segment_ids
                   FROM memory_chunks c JOIN meetings m ON m.id = c.meeting_id
                   WHERE c.id = ANY(:ids)"""
                ),
                {"ids": [chunk_id for chunk_id, _score in fused]},
            )
        )
        .mappings()
        .all()
    )
    by_id = {row["id"]: row for row in rows}
    ranked: list[tuple[str, float]] = []
    seen_hashes: set[tuple] = set()
    for chunk_id, score in fused:
        row = by_id.get(chunk_id)
        # Identical content is only a duplicate when it also comes from the same speaker at the
        # same time (the same recording imported twice). "Sí, ho tinc." said by two people, or
        # in two weekly meetings, is different evidence and stays.
        key = (row["content_hash"], row["speaker"], round(row["start_time"], 1)) if row else None
        if row is None or key in seen_hashes:
            continue
        seen_hashes.add(key)
        ranked.append((chunk_id, score))
        if len(ranked) == top_k:
            break
    ids = [chunk_id for chunk_id, _score in ranked]
    evidence_rows = (
        (
            await session.execute(
                text(
                    """SELECT chunk_id, segment_id, start_time, end_time FROM memory_evidence
                   WHERE chunk_id = ANY(:ids) ORDER BY start_time"""
                ),
                {"ids": ids},
            )
        )
        .mappings()
        .all()
    )
    evidence: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        evidence.setdefault(row["chunk_id"], []).append(
            {"segment_id": row["segment_id"], "start": row["start_time"], "end": row["end_time"]}
        )
    results = []
    text_set, vector_set = set(text_ids), set(vector_ids)
    for chunk_id, score in ranked:
        row = by_id[chunk_id]
        results.append(
            {
                "chunk_id": chunk_id,
                "meeting_id": row["meeting_id"],
                "meeting_title": row["title"],
                "meeting_date": row["created_at"].isoformat(),
                "content": row["content"],
                "start": row["start_time"],
                "end": row["end_time"],
                "language": row["language"],
                "speaker": row["speaker"],
                "track": row["track"],
                "score": round(score, 6),
                "matched": [
                    name
                    for name, found in (
                        ("text", chunk_id in text_set),
                        ("vector", chunk_id in vector_set),
                    )
                    if found
                ],
                "evidence": evidence.get(chunk_id, []),
            }
        )
    return results
