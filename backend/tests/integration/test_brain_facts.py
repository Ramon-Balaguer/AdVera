"""Facts projected into the Brain from the Summary, against real PostgreSQL (ADR 0024)."""

import pytest
from sqlalchemy import select

from app.brain_backfill import _reproject
from app.models import BrainFact
from tests.integration.test_concept_graph import (
    concept,
    extraction,
    project,
    run_projection,
)
from tests.integration.test_summary_pipeline import llm_configured  # noqa: F401

pytestmark = pytest.mark.integration


def with_facts(output):
    output.parsed["decisions"] = [
        {"text": "Migrar a Redis", "evidence_ids": ["system-00000"], "state": "decided"}
    ]
    output.parsed["actions"] = [
        {"text": "Preparar el informe", "evidence_ids": ["system-00001"], "owner": "Marta"}
    ]
    output.parsed["open_questions"] = [{"text": "¿Quién paga?", "evidence_ids": ["system-00000"]}]
    return output


async def facts_of(sessionmaker, meeting_id):
    async with sessionmaker() as session:
        return (
            (await session.execute(select(BrainFact).where(BrainFact.meeting_id == meeting_id)))
            .scalars()
            .all()
        )


async def test_the_projection_writes_the_facts_with_their_evidence(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        with_facts(extraction(concepts=[concept("Redis")])),
        title="Con hechos",
    )
    assert (
        await run_projection(sessionmaker, storage, settings, meeting["id"])
    ).status == "completed"

    facts = {f.kind: f for f in await facts_of(sessionmaker, meeting["id"])}
    assert set(facts) == {"decision", "action", "question"}
    assert facts["decision"].state == "decided" and facts["decision"].text == "Migrar a Redis"
    assert facts["action"].owner == "Marta"
    assert (
        facts["decision"].evidence and facts["decision"].evidence[0]["segment_id"] == "system-00000"
    )


async def test_projecting_again_replaces_the_facts_instead_of_duplicating_them(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        with_facts(extraction(concepts=[concept("Redis")])),
        title="Dos veces",
    )
    await run_projection(sessionmaker, storage, settings, meeting["id"])
    before = {f.text for f in await facts_of(sessionmaker, meeting["id"])}

    async with sessionmaker() as session:
        job = await _reproject(session, meeting["id"], settings)
        await session.commit()
    assert job is not None
    await run_projection(sessionmaker, storage, settings, meeting["id"])

    after = await facts_of(sessionmaker, meeting["id"])
    assert len(after) == 3 and {f.text for f in after} == before


async def test_deleting_the_meeting_deletes_its_facts(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    meeting, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        with_facts(extraction(concepts=[concept("Redis")])),
        title="A borrar",
    )
    await run_projection(sessionmaker, storage, settings, meeting["id"])
    assert await facts_of(sessionmaker, meeting["id"])

    assert api.delete(f"/api/meetings/{meeting['id']}").status_code in (200, 204)
    assert await facts_of(sessionmaker, meeting["id"]) == []
