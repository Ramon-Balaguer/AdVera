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
INSPECTOR_ROWS = 200  # mentions or tag assignments read for one concept
INSPECTOR_RELATIONS = 100


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
    # The meetings in scope, applied to mentions, assignments and relationship occurrences
    # alike, so a filtered graph never counts or draws what happened in other meetings.
    scope = ""
    if meeting_id:
        scope += " AND {col} = :meeting_id"
        params["meeting_id"] = meeting_id
    if tag:
        scope += """ AND {col} IN (
            SELECT a.meeting_id FROM memory_concept_assignments a
            JOIN memory_concepts t ON t.id = a.concept_id
            WHERE t.identity = 'tag' AND t.canonical_key = :tag_key)"""
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
    # Every fragment interpolated below is a constant of this function; values are bound.
    base = f"""
        WITH links AS (
            SELECT concept_id, meeting_id, 1 AS is_mention FROM memory_concept_mentions
            UNION ALL
            SELECT concept_id, meeting_id, 0 FROM memory_concept_assignments
        ), grouped AS (
            SELECT c.id, c.concept_type, c.canonical_name,
                   COUNT(DISTINCT l.meeting_id) AS meetings, SUM(l.is_mention) AS mentions
            FROM memory_concepts c JOIN links l ON l.concept_id = c.id
            WHERE {where}{scope.format(col="l.meeting_id")}
            GROUP BY c.id, c.concept_type, c.canonical_name
        ), drawn AS (
            -- An edge is drawn when both ends are shown and it is manual, or a Brain one with
            -- an occurrence in the meetings in scope.
            SELECT r.id, r.source_concept_id AS source, r.target_concept_id AS target,
                   r.relationship_type, r.source_type,
                   COUNT(o.id) AS occurrences, COUNT(DISTINCT o.meeting_id) AS meetings
            FROM memory_concept_relationships r
            JOIN grouped gs ON gs.id = r.source_concept_id
            JOIN grouped gt ON gt.id = r.target_concept_id
            LEFT JOIN memory_concept_relationship_occurrences o
                   ON o.relationship_id = r.id{scope.format(col="o.meeting_id")}
            GROUP BY r.id
            HAVING r.source_type <> 'brain' OR COUNT(o.id) > 0
        )
    """
    connected = "EXISTS (SELECT 1 FROM drawn d WHERE d.source = g.id OR d.target = g.id)"
    shown = "TRUE" if include_isolated else connected
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
        edge_rows = (
            await session.execute(
                text(
                    base
                    + """SELECT id, source, target, relationship_type, source_type,
                                occurrences, meetings FROM drawn
                         WHERE source = ANY(:ids) AND target = ANY(:ids) ORDER BY id"""
                ),
                {**params, "ids": [n.id for n in nodes]},
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
    alive = (
        await session.execute(
            text(
                """SELECT
                     EXISTS (SELECT 1 FROM memory_concept_mentions WHERE concept_id = :id)
                     OR EXISTS (SELECT 1 FROM memory_concept_assignments WHERE concept_id = :id)"""
            ),
            {"id": concept_id},
        )
    ).scalar_one()
    if not alive:
        # Nobody mentions or tags it any more (its meetings were deleted): not shown anywhere.
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
                   WHERE m.concept_id = :id ORDER BY mt.created_at DESC, m.id
                   LIMIT :limit"""
            ),
            {"id": concept_id, "limit": INSPECTOR_ROWS},
        )
    ).all()
    tag_rows = (
        await session.execute(
            text(
                """SELECT a.meeting_id, mt.title, mt.created_at
                   FROM memory_concept_assignments a JOIN meetings mt ON mt.id = a.meeting_id
                   WHERE a.concept_id = :id ORDER BY mt.created_at DESC LIMIT :limit"""
            ),
            {"id": concept_id, "limit": INSPECTOR_ROWS},
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
                   ORDER BY r.relationship_type, oc.canonical_name LIMIT :limit"""
            ),
            {"id": concept_id, "limit": INSPECTOR_RELATIONS},
        )
    ).all()
    occurrence_rows = (
        await session.execute(
            text(
                """SELECT relationship_id, meeting_id, title, evidence FROM (
                       SELECT o.relationship_id, o.meeting_id, mt.title, o.evidence,
                              ROW_NUMBER() OVER (PARTITION BY o.relationship_id
                                                 ORDER BY mt.created_at DESC, o.id) AS n
                       FROM memory_concept_relationship_occurrences o
                       JOIN meetings mt ON mt.id = o.meeting_id
                       WHERE o.relationship_id = ANY(:ids)) ranked
                   WHERE n <= :per_relation ORDER BY n"""
            ),
            {"ids": [r[0] for r in relation_rows] or [""], "per_relation": INSPECTOR_MEETINGS},
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
        seen = {e.segment_id for e in item.evidence}
        item.evidence += [e for e in evidence(meeting_id, raw) if e.segment_id not in seen]
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

    by_relation: dict[str, list] = {}
    for row in occurrence_rows:
        by_relation.setdefault(row[0], []).append(row)
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
        own = by_relation.get(rid, [])
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
