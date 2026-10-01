"""Read-only concept graph (spec §20; concept-graph.md; ADR 0019).

GET /api/memory/concept-graph       nodes and edges, with filters and a size bound
GET /api/memory/concepts/{id}       what the inspector shows: meetings, cited segments, relations

Concepts are global; a meeting reaches one by a mention (transcript evidence) or by a manual tag
(no evidence). A concept nobody mentions or tags any more is not shown. Nothing here writes.

`include_isolated=false` leaves out concepts with no relationship that would be drawn (under the
same meeting filter), so the view does not fill up with loose nodes as meetings accumulate; the
response says how many were left out.
"""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.concepts import canonical_key
from app.database import get_session
from app.transcripts import parse_definitive

router = APIRouter(tags=["memory"])
Session = Annotated[AsyncSession, Depends(get_session)]

GRAPH_DEFAULT_LIMIT = 200
GRAPH_MAX_LIMIT = 500
INSPECTOR_MEETINGS = 10
INSPECTOR_EVIDENCE = 5


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    meetings: int
    mentions: int
    is_tag: bool


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    source_type: str
    occurrences: int
    meetings: int


class ConceptGraphResponse(BaseModel):
    state: Literal["empty", "partial", "ready"]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    truncated: bool
    hidden_isolated: int = 0


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/api/memory/concept-graph", response_model=ConceptGraphResponse)
async def concept_graph(
    session: Session,
    type: Annotated[str | None, Query(max_length=30)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    meeting_id: Annotated[str | None, Query(max_length=36)] = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=GRAPH_MAX_LIMIT)] = GRAPH_DEFAULT_LIMIT,
    include_isolated: bool = True,
) -> ConceptGraphResponse:
    clauses = ["1 = 1"]
    params: dict[str, object] = {"limit": limit}
    links_filter = ""
    if meeting_id:
        links_filter += " AND l.meeting_id = :meeting_id"
        params["meeting_id"] = meeting_id
    if tag:
        # Only meetings that carry this tag (resolved before anything is counted).
        links_filter += """ AND l.meeting_id IN (
            SELECT a.meeting_id FROM memory_concept_assignments a
            JOIN memory_concepts t ON t.id = a.concept_id
            WHERE t.concept_type = 'tag' AND t.canonical_key = :tag_key)"""
        params["tag_key"] = canonical_key(tag)
    if type:
        clauses.append("c.concept_type = :type")
        params["type"] = type
    key = canonical_key(q or "")
    if key:
        clauses.append(
            """(c.canonical_key LIKE :q ESCAPE '\\' OR EXISTS (
                SELECT 1 FROM memory_concept_aliases al
                WHERE al.concept_id = c.id AND al.normalized_alias LIKE :q ESCAPE '\\'))"""
        )
        params["q"] = _like(key)
    where = " AND ".join(clauses)
    # A relationship is drawn when it is manual, or a Brain one with an occurrence left.
    occurrence_meeting = " AND o.meeting_id = :meeting_id" if meeting_id else ""
    connected = f"""EXISTS (
        SELECT 1 FROM memory_concept_relationships r
        WHERE (r.source_concept_id = g.id OR r.target_concept_id = g.id)
          AND (r.source_type <> 'brain' OR EXISTS (
                SELECT 1 FROM memory_concept_relationship_occurrences o
                WHERE o.relationship_id = r.id{occurrence_meeting})))"""
    shown = "1 = 1" if include_isolated else connected
    base = f"""
        WITH links AS (
            SELECT concept_id, meeting_id, 1 AS is_mention FROM memory_concept_mentions
            UNION ALL
            SELECT concept_id, meeting_id, 0 FROM memory_concept_assignments
        ), grouped AS (
            SELECT c.id, c.concept_type, c.canonical_name,
                   COUNT(DISTINCT l.meeting_id) AS meetings, SUM(l.is_mention) AS mentions
            FROM memory_concepts c JOIN links l ON l.concept_id = c.id
            WHERE {where}{links_filter}
            GROUP BY c.id, c.concept_type, c.canonical_name
        )
    """
    all_total, total = (
        await session.execute(
            text(base + f"SELECT COUNT(*), COUNT(*) FILTER (WHERE {shown}) FROM grouped g"), params
        )
    ).one()
    rows = (
        await session.execute(
            text(
                base
                + f"""SELECT id, concept_type, canonical_name, meetings, mentions FROM grouped g
                     WHERE {shown}
                     ORDER BY meetings DESC, mentions DESC, canonical_name, id LIMIT :limit"""
            ),
            params,
        )
    ).all()
    nodes = [
        GraphNode(
            id=r[0],
            type=r[1],
            label=r[2],
            meetings=r[3],
            mentions=int(r[4] or 0),
            is_tag=r[1] == "tag",
        )
        for r in rows
    ]
    edges: list[GraphEdge] = []
    if nodes:
        ids = [n.id for n in nodes]
        edge_params: dict[str, object] = {"ids": ids}
        if meeting_id:
            edge_params["meeting_id"] = meeting_id
        edge_rows = (
            await session.execute(
                text(
                    f"""SELECT r.id, r.source_concept_id, r.target_concept_id, r.relationship_type,
                               r.source_type, COUNT(o.id), COUNT(DISTINCT o.meeting_id)
                        FROM memory_concept_relationships r
                        LEFT JOIN memory_concept_relationship_occurrences o
                               ON o.relationship_id = r.id{occurrence_meeting}
                        WHERE r.source_concept_id = ANY(:ids) AND r.target_concept_id = ANY(:ids)
                        GROUP BY r.id ORDER BY r.id"""
                ),
                edge_params,
            )
        ).all()
        edges = [
            GraphEdge(
                id=r[0],
                source=r[1],
                target=r[2],
                type=r[3],
                source_type=r[4],
                occurrences=r[5],
                meetings=r[6],
            )
            for r in edge_rows
            # A Brain relationship with no occurrence left (filtered out) is not drawn;
            # manual relationships (a tag related to a concept) have none by design.
            if r[4] != "brain" or r[5] > 0
        ]

    pending = (
        await session.execute(
            text(
                """SELECT
                     (SELECT COUNT(*) FROM memory_index_jobs
                        WHERE kind = 'concepts' AND status IN ('queued', 'running'))
                   + (SELECT COUNT(*) FROM brain_jobs WHERE status IN ('queued', 'running'))"""
            )
        )
    ).scalar_one()
    state: Literal["empty", "partial", "ready"] = (
        "partial" if pending else ("ready" if all_total else "empty")
    )
    return ConceptGraphResponse(
        state=state,
        nodes=nodes,
        edges=edges,
        total_nodes=total,
        truncated=total > len(nodes),
        hidden_isolated=all_total - total,
    )


class InspectorEvidence(BaseModel):
    segment_id: str
    start: float
    text: str | None


class InspectorMeeting(BaseModel):
    meeting_id: str
    title: str
    created_at: str
    mention: str | None
    evidence: list[InspectorEvidence]
    tagged: bool


class InspectorRelation(BaseModel):
    id: str
    direction: Literal["outgoing", "incoming"]
    type: str
    source_type: str
    other_id: str
    other_label: str
    other_type: str
    meetings: list[str]
    evidence: list[InspectorEvidence]


class ConceptDetail(BaseModel):
    id: str
    type: str
    label: str
    is_tag: bool
    aliases: list[str]
    meetings: list[InspectorMeeting]
    relations: list[InspectorRelation]


def _segment_texts(storage, meeting_ids: list[str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for meeting_id in meeting_ids:
        try:
            document = parse_definitive(storage.read_transcript(meeting_id))
        except (OSError, ValueError):
            document = None
        if document is not None:
            result[meeting_id] = {s.id: s.text for s in document.segments}
    return result


@router.get("/api/memory/concepts/{concept_id}", response_model=ConceptDetail)
async def concept_detail(concept_id: str, session: Session, request: Request) -> ConceptDetail:
    concept = (
        await session.execute(
            text("SELECT id, concept_type, canonical_name FROM memory_concepts WHERE id = :id"),
            {"id": concept_id},
        )
    ).one_or_none()
    if concept is None:
        raise HTTPException(status_code=404, detail="CONCEPT_NOT_FOUND")
    aliases = [
        r[0]
        for r in (
            await session.execute(
                text(
                    "SELECT alias FROM memory_concept_aliases WHERE concept_id = :id ORDER BY alias"
                ),
                {"id": concept_id},
            )
        ).all()
    ]
    mention_rows = (
        await session.execute(
            text(
                """SELECT m.meeting_id, mt.title, mt.created_at, m.mention, m.evidence
                   FROM memory_concept_mentions m JOIN meetings mt ON mt.id = m.meeting_id
                   WHERE m.concept_id = :id ORDER BY mt.created_at DESC, m.id"""
            ),
            {"id": concept_id},
        )
    ).all()
    tag_rows = (
        await session.execute(
            text(
                """SELECT a.meeting_id, mt.title, mt.created_at
                   FROM memory_concept_assignments a JOIN meetings mt ON mt.id = a.meeting_id
                   WHERE a.concept_id = :id ORDER BY mt.created_at DESC"""
            ),
            {"id": concept_id},
        )
    ).all()
    relation_rows = (
        await session.execute(
            text(
                """SELECT r.id, r.source_concept_id, r.target_concept_id, r.relationship_type,
                          r.source_type, oc.id, oc.canonical_name, oc.concept_type
                   FROM memory_concept_relationships r
                   JOIN memory_concepts oc
                     ON oc.id = CASE WHEN r.source_concept_id = :id
                                     THEN r.target_concept_id ELSE r.source_concept_id END
                   WHERE r.source_concept_id = :id OR r.target_concept_id = :id
                   ORDER BY r.relationship_type, oc.canonical_name"""
            ),
            {"id": concept_id},
        )
    ).all()
    occurrence_rows = (
        await session.execute(
            text(
                """SELECT o.relationship_id, o.meeting_id, mt.title, o.evidence
                   FROM memory_concept_relationship_occurrences o
                   JOIN meetings mt ON mt.id = o.meeting_id
                   WHERE o.relationship_id = ANY(:ids) ORDER BY mt.created_at DESC"""
            ),
            {"ids": [r[0] for r in relation_rows] or [""]},
        )
    ).all()

    shown = list(dict.fromkeys([r[0] for r in mention_rows] + [r[0] for r in tag_rows]))
    shown = shown[:INSPECTOR_MEETINGS]
    texts = await asyncio.to_thread(_segment_texts, request.app.state.storage, shown)

    def evidence(meeting_id: str, raw: list) -> list[InspectorEvidence]:
        return [
            InspectorEvidence(
                segment_id=e["segment_id"],
                start=e["start"],
                text=texts.get(meeting_id, {}).get(e["segment_id"]),
            )
            for e in (raw or [])[:INSPECTOR_EVIDENCE]
        ]

    meetings: dict[str, InspectorMeeting] = {}
    for meeting_id, title, created, mention, raw in mention_rows:
        if meeting_id not in shown:
            continue
        item = meetings.setdefault(
            meeting_id,
            InspectorMeeting(
                meeting_id=meeting_id,
                title=title,
                created_at=created.isoformat(),
                mention=mention,
                evidence=[],
                tagged=False,
            ),
        )
        item.evidence += evidence(meeting_id, raw)
    for meeting_id, title, created in tag_rows:
        if meeting_id not in shown:
            continue
        item = meetings.setdefault(
            meeting_id,
            InspectorMeeting(
                meeting_id=meeting_id,
                title=title,
                created_at=created.isoformat(),
                mention=None,
                evidence=[],
                tagged=True,
            ),
        )
        item.tagged = True

    relations: list[InspectorRelation] = []
    for (
        rid,
        source,
        _target,
        rtype,
        source_type,
        other_id,
        other_label,
        other_type,
    ) in relation_rows:
        own = [o for o in occurrence_rows if o[0] == rid]
        relations.append(
            InspectorRelation(
                id=rid,
                direction="outgoing" if source == concept_id else "incoming",
                type=rtype,
                source_type=source_type,
                other_id=other_id,
                other_label=other_label,
                other_type=other_type,
                meetings=list(dict.fromkeys(o[2] for o in own)),
                evidence=[e for o in own[:3] for e in evidence_for_relation(o, texts)],
            )
        )
    return ConceptDetail(
        id=concept[0],
        type=concept[1],
        label=concept[2],
        is_tag=concept[1] == "tag",
        aliases=aliases,
        meetings=list(meetings.values()),
        relations=relations,
    )


def evidence_for_relation(
    occurrence: tuple, texts: dict[str, dict[str, str]]
) -> list[InspectorEvidence]:
    """Evidence of one relationship occurrence; its text is only read for the shown meetings."""
    _rid, meeting_id, _title, raw = occurrence
    return [
        InspectorEvidence(
            segment_id=e["segment_id"],
            start=e["start"],
            text=texts.get(meeting_id, {}).get(e["segment_id"]),
        )
        for e in (raw or [])[:INSPECTOR_EVIDENCE]
    ]
