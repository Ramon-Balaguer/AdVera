"""GET /api/brain/facts and GET /api/meetings/{id}/brain against real PostgreSQL (ADR 0024)."""

import pytest

from tests.integration.test_concept_graph import (
    concept,
    extraction,
    project,
    relation,
    run_projection,
)
from tests.integration.test_import_transcription import create_meeting
from tests.integration.test_summary_pipeline import llm_configured  # noqa: F401

pytestmark = pytest.mark.integration


def output(decision, state, action, owner, question=None):
    result = extraction(
        concepts=[concept("Redis"), concept("Presupuesto", type="topic")],
        relationships=[relation("Redis", "Presupuesto", "constrains")],
    )
    result.parsed["decisions"] = [
        {"text": decision, "evidence_ids": ["system-00000"], "state": state}
    ]
    result.parsed["actions"] = [
        {"text": action, "evidence_ids": ["system-00001"], "owner": owner, "due_date": "viernes"}
    ]
    result.parsed["open_questions"] = (
        [{"text": question, "evidence_ids": ["system-00000"]}] if question else []
    )
    return result


@pytest.fixture
async def two_meetings(
    api,
    recording_queue,
    sessionmaker,
    storage,
    settings,
    tmp_path,
    llm_configured,  # noqa: F811
):
    first, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        output("Migrar a Redis", "decided", "Preparar el informe", "Marta", "¿Quién paga?"),
        title="Primera",
    )
    second, *_ = await project(
        api,
        sessionmaker,
        storage,
        settings,
        tmp_path,
        output("Aplazar el presupuesto", "proposed", "Revisar costes", "Ramón"),
        title="Segunda",
    )
    for meeting in (first, second):
        await run_projection(sessionmaker, storage, settings, meeting["id"])
    api.post(f"/api/meetings/{first['id']}/tags", json={"label": "Cliente"})
    return first, second


def facts(api, **params):
    response = api.get("/api/brain/facts", params=params)
    assert response.status_code == 200
    return response.json()


async def test_facts_are_listed_across_meetings_with_counts_and_citations(api, two_meetings):
    body = facts(api)

    assert body["total"] == 5
    assert body["counts"] == {"decision": 2, "action": 2, "risk": 0, "question": 1, "topic": 0}
    newest = body["facts"][0]
    assert newest["meeting_title"] in ("Primera", "Segunda")
    decision = next(f for f in body["facts"] if f["text"] == "Migrar a Redis")
    assert (
        decision["state"] == "decided" and decision["evidence"][0]["segment_id"] == "system-00000"
    )
    assert decision["meeting_id"] == two_meetings[0]["id"]


async def test_facts_can_be_filtered_by_kind_state_owner_text_meeting_and_tag(api, two_meetings):
    first, second = two_meetings

    assert [f["text"] for f in facts(api, kind="decision", state="decided")["facts"]] == [
        "Migrar a Redis"
    ]
    assert [f["text"] for f in facts(api, kind="action", owner="ram")["facts"]] == [
        "Revisar costes"
    ]
    assert [f["text"] for f in facts(api, q="PRESUPUESTO")["facts"]] == ["Aplazar el presupuesto"]
    assert {f["meeting_id"] for f in facts(api, meeting_id=second["id"])["facts"]} == {second["id"]}
    # Any of the tags: only the first meeting carries "Cliente"; an unknown tag adds nothing.
    tagged = facts(api, tag=["Cliente", "otra"])
    assert {f["meeting_id"] for f in tagged["facts"]} == {first["id"]} and tagged["total"] == 3
    # The counts ignore the kind, so the tabs can show every number at once.
    assert facts(api, kind="question")["counts"]["decision"] == 2


async def test_facts_respect_the_date_range_and_the_page(api, two_meetings):
    assert facts(api, date_from="2999-01-01T00:00:00Z")["total"] == 0
    assert facts(api, date_to="2000-01-01T00:00:00Z")["total"] == 0
    page = facts(api, limit=2, offset=0)
    rest = facts(api, limit=2, offset=4)
    assert page["total"] == 5 and len(page["facts"]) == 2 and len(rest["facts"]) == 1
    assert api.get("/api/brain/facts", params={"limit": 0}).status_code == 422
    assert api.get("/api/brain/facts", params={"kind": "other"}).status_code == 422


async def test_a_meeting_shows_how_it_connects_to_the_rest_of_the_brain(api, two_meetings):
    first, second = two_meetings
    api.post(f"/api/meetings/{second['id']}/tags", json={"label": "Cliente"})
    body = api.get(f"/api/meetings/{first['id']}/brain").json()

    assert body["title"] == "Primera"
    assert "facts" not in body  # the summary already lists them; this only counts them
    assert body["fact_counts"] == {"decision": 1, "action": 1, "risk": 0, "question": 1, "topic": 0}
    concepts = {c["name"]: c for c in body["concepts"]}
    assert set(concepts) == {"Redis", "Presupuesto"}
    # Both concepts are also in the second meeting; the ones found elsewhere come first.
    assert all(c["other_meetings"] == 1 and c["mentions"] >= 1 for c in concepts.values())
    assert all(c["first_seen"] for c in concepts.values())
    assert [(r["source"], r["target"], r["type"]) for r in body["relationships"]] == [
        ("Redis", "Presupuesto", "constrains")
    ]
    [tag] = body["tags"]
    assert (tag["label"], tag["other_meetings"]) == ("Cliente", 1) and tag["id"]
    assert body["people"] == []
    assert body["projection"]["state"] == "completed" and body["projection"]["up_to_date"] is True
    assert body["index"]["state"] in ("queued", "none", "completed")
    assert body["index"]["chunks"] >= 0 and body["index"]["embedded"] <= body["index"]["chunks"]


async def test_a_concept_found_only_in_one_meeting_has_no_other_meetings(
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
        extraction(concepts=[concept("Unico")]),
        title="Sola",
    )
    await run_projection(sessionmaker, storage, settings, meeting["id"])
    [only] = api.get(f"/api/meetings/{meeting['id']}/brain").json()["concepts"]
    assert only["other_meetings"] == 0 and only["first_seen"]


async def test_a_meeting_without_summary_has_an_empty_brain_and_an_unknown_one_is_404(api):
    meeting = create_meeting(api, "Vacía")
    body = api.get(f"/api/meetings/{meeting['id']}/brain").json()

    assert body["projection"] == {
        "state": "none",
        "error": None,
        "completed_at": None,
        "up_to_date": None,
    }
    assert body["index"]["state"] == "none" and body["index"]["chunks"] == 0
    assert set(body["fact_counts"].values()) == {0}
    assert body["concepts"] == [] and body["relationships"] == []
    assert api.get("/api/meetings/nope/brain").status_code == 404
