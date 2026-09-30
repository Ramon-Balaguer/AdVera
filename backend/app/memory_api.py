"""Memory API (spec §15, §20; brain-query-results-websocket.md).

POST /api/memory/query        create a durable query run (HTTP 202)
GET  /api/memory/query/{id}   durable state and result (recovery contract)
WS   /ws/query/{id}           state transitions until a terminal state, then close
GET  /api/memory/overview     honest index state: empty, indexing, partial or ready
"""

import asyncio
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import memory_jobs, runtime_settings
from app.config import Settings, get_settings
from app.database import get_session
from app.models import MemoryChunk, MemoryIndexJob, MemoryQueryRun, utcnow

router = APIRouter(tags=["memory"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
TERMINAL = ("completed", "empty", "failed")
WS_POLL_SECONDS = 0.5
WS_MAX_SECONDS = 900


class QueryFilters(BaseModel):
    meeting_ids: list[str] = Field(default_factory=list, max_length=100)
    language: str | None = Field(default=None, max_length=10)
    speaker: str | None = Field(default=None, max_length=50)
    tag: str | None = Field(default=None, max_length=100)
    date_from: datetime | None = None
    date_to: datetime | None = None


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    filters: QueryFilters = Field(default_factory=QueryFilters)
    top_k: int = Field(default=8, ge=1, le=20)


class QueryResponse(BaseModel):
    query_id: str
    query: str
    status: Literal["queued", "retrieving", "synthesizing", "completed", "empty", "failed"]
    error: str | None
    filters: dict[str, Any]
    result: dict[str, Any] | None
    model: str
    created_at: datetime
    completed_at: datetime | None


def _response(run: MemoryQueryRun) -> QueryResponse:
    return QueryResponse(
        query_id=run.id,
        query=run.query,
        status=run.status,
        error=run.error,
        filters=run.filters or {},
        result=run.result,
        model=run.model,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.post("/api/memory/query", response_model=QueryResponse, status_code=202)
async def create_query(
    body: QueryRequest, request: Request, session: Session, settings: AppSettings
) -> QueryResponse:
    runtime = runtime_settings.load(settings)
    if not runtime.llm_configured:
        raise HTTPException(status_code=409, detail="LLM_NOT_CONFIGURED")
    filters = body.filters.model_dump(mode="json", exclude_none=True)
    run = await memory_jobs.create_query_run(
        session,
        query=body.query.strip(),
        filters=filters,
        top_k=body.top_k,
        runtime=runtime,
        settings=settings,
    )
    await session.commit()
    if not await memory_jobs.publish(request.app.state.memory_query_queue, run.id, "query"):
        # redis.md §4: never leave a query silently queued when Redis is down.
        run.status = "failed"
        run.error = "QUEUE_UNAVAILABLE"
        run.completed_at = utcnow()
        await session.commit()
    return _response(run)


@router.get("/api/memory/query/{query_id}", response_model=QueryResponse)
async def get_query(query_id: str, session: Session) -> QueryResponse:
    run = await session.get(MemoryQueryRun, query_id)
    if run is None:
        raise HTTPException(status_code=404, detail="QUERY_NOT_FOUND")
    return _response(run)


@router.websocket("/ws/query/{query_id}")
async def query_updates(websocket: WebSocket, query_id: str) -> None:
    """Emit each state change; the persisted run stays the source of truth."""
    await websocket.accept()
    sessionmaker = websocket.app.state.sessionmaker
    last: str | None = None
    elapsed = 0.0
    try:
        while elapsed < WS_MAX_SECONDS:
            async with sessionmaker() as session:
                run = await session.get(MemoryQueryRun, query_id)
                payload = _response(run).model_dump(mode="json") if run else None
            if payload is None:
                await websocket.send_json({"type": "query.error", "code": "QUERY_NOT_FOUND"})
                break
            if payload["status"] != last:
                last = payload["status"]
                await websocket.send_json({"type": "query.state", **payload})
            if last in TERMINAL:
                break
            await asyncio.sleep(WS_POLL_SECONDS)
            elapsed += WS_POLL_SECONDS
        else:
            await websocket.send_json({"type": "query.error", "code": "QUERY_TIMEOUT"})
    except (WebSocketDisconnect, RuntimeError):
        return
    await websocket.close()


class OverviewResponse(BaseModel):
    state: Literal["empty", "indexing", "partial", "ready"]
    meetings_indexed: int
    chunks: int
    embedded_chunks: int
    jobs_pending: int
    jobs_failed: int
    llm_configured: bool


@router.get("/api/memory/overview", response_model=OverviewResponse)
async def overview(session: Session, settings: AppSettings) -> OverviewResponse:
    chunks = (await session.execute(select(func.count(MemoryChunk.id)))).scalar_one()
    embedded = (
        await session.execute(
            select(func.count(MemoryChunk.id)).where(MemoryChunk.embedding.is_not(None))
        )
    ).scalar_one()
    meetings = (
        await session.execute(select(func.count(func.distinct(MemoryChunk.meeting_id))))
    ).scalar_one()
    pending = (
        await session.execute(
            select(func.count(MemoryIndexJob.id)).where(
                MemoryIndexJob.status.in_(("queued", "running"))
            )
        )
    ).scalar_one()
    failed = (
        await session.execute(
            select(func.count(MemoryIndexJob.id)).where(MemoryIndexJob.status == "failed")
        )
    ).scalar_one()
    if chunks == 0:
        state = "indexing" if pending else "empty"
    elif pending:
        state = "indexing"
    elif embedded < chunks or failed:
        state = "partial"
    else:
        state = "ready"
    return OverviewResponse(
        state=state,
        meetings_indexed=meetings,
        chunks=chunks,
        embedded_chunks=embedded,
        jobs_pending=pending,
        jobs_failed=failed,
        llm_configured=runtime_settings.load(settings).llm_configured,
    )
