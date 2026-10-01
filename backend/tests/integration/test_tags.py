"""Manual tags as shared concepts (ADR 0013) against real PostgreSQL."""

import pytest
from sqlalchemy import select

from app.models import (
    MemoryConcept,
    MemoryConceptAssignment,
    MemoryConceptRelationship,
)
from tests.integration.test_import_transcription import create_meeting

pytestmark = pytest.mark.integration


def add(api, meeting_id, label):
    return api.post(f"/api/meetings/{meeting_id}/tags", json={"label": label})


async def concepts(sessionmaker, **where):
    async with sessionmaker() as session:
        rows = (await session.execute(select(MemoryConcept))).scalars().all()
    return [c for c in rows if all(getattr(c, k) == v for k, v in where.items())]


async def test_a_tag_persists_and_is_reused_across_casing_and_spacing(api, sessionmaker):
    meeting = create_meeting(api, "Reunió de seguiment")
    first = add(api, meeting["id"], "Pressupost")
    assert first.status_code == 201
    assert first.json()["label"] == "Pressupost"

    # The same tag in another case, accents or spacing is the same assignment: no duplicate.
    for variant in ("pressupost", "  PRESSUPOST. ", "Pressupost"):
        again = add(api, meeting["id"], variant)
        assert again.status_code == 200
        assert again.json()["assignment_id"] == first.json()["assignment_id"]
    listed = api.get(f"/api/meetings/{meeting['id']}/tags").json()
    assert [t["label"] for t in listed] == ["Pressupost"]
    assert len(await concepts(sessionmaker, concept_type="tag")) == 1

    # It survives a reload of the meeting itself.
    assert api.get(f"/api/meetings/{meeting['id']}").json()["tags"][0]["label"] == "Pressupost"


async def test_the_concept_is_shared_and_removing_a_tag_only_removes_that_assignment(
    api, sessionmaker
):
    first = create_meeting(api, "Primera")
    second = create_meeting(api, "Segunda")
    a = add(api, first["id"], "Lanzamiento").json()
    b = add(api, second["id"], "lanzamiento").json()
    assert a["concept_id"] == b["concept_id"]  # one shared concept

    summary = api.get("/api/meetings/tags").json()
    assert summary == [{"concept_id": a["concept_id"], "label": "Lanzamiento", "meetings": 2}]

    assert api.delete(f"/api/meetings/{first['id']}/tags/{a['assignment_id']}").status_code == 204
    assert api.get(f"/api/meetings/{first['id']}/tags").json() == []
    assert [t["label"] for t in api.get(f"/api/meetings/{second['id']}/tags").json()] == [
        "lanzamiento"
    ]
    assert len(await concepts(sessionmaker, concept_type="tag")) == 1  # the concept stays

    # An assignment of another meeting cannot be deleted through this one.
    wrong = api.delete(f"/api/meetings/{first['id']}/tags/{b['assignment_id']}")
    assert (wrong.status_code, wrong.json()["detail"]) == (404, "TAG_NOT_FOUND")


def test_invalid_and_excessive_tags_are_rejected(api):
    meeting = create_meeting(api, "Límits")
    for bad in ("", "   ", "...", "x" * 61):
        response = add(api, meeting["id"], bad)
        assert (response.status_code, response.json()["detail"]) == (422, "INVALID_TAG"), bad
    for index in range(20):
        assert add(api, meeting["id"], f"etiqueta {index}").status_code == 201
    over = add(api, meeting["id"], "una de más")
    assert (over.status_code, over.json()["detail"]) == (409, "TOO_MANY_TAGS")
    # An existing tag is still idempotent at the limit.
    assert add(api, meeting["id"], "ETIQUETA 3").status_code == 200
    assert api.get("/api/meetings/not-a-meeting/tags").status_code == 404


def test_suggestions_are_existing_tags_not_yet_on_the_meeting_most_used_first(api):
    mine = create_meeting(api, "Mia")
    others = [create_meeting(api, f"Otra {i}") for i in range(3)]
    for meeting in others:
        add(api, meeting["id"], "Presupuesto")
    add(api, others[0]["id"], "Preproducción")
    add(api, others[0]["id"], "Seguridad")
    add(api, mine["id"], "Seguridad")  # already on this meeting: never suggested

    suggested = api.get(f"/api/meetings/{mine['id']}/tags/suggestions", params={"q": "pre"}).json()
    assert [s["label"] for s in suggested] == ["Presupuesto", "Preproducción"]
    assert suggested[0]["meetings"] == 3
    # Accents and case do not matter, and a fragment inside the word matches too.
    assert [
        s["label"]
        for s in api.get(
            f"/api/meetings/{mine['id']}/tags/suggestions", params={"q": "PRODUCCION"}
        ).json()
    ] == ["Preproducción"]
    # No text: the most used ones.
    assert (
        api.get(f"/api/meetings/{mine['id']}/tags/suggestions").json()[0]["label"] == "Presupuesto"
    )
    # LIKE wildcards in the text are literal.
    assert api.get(f"/api/meetings/{mine['id']}/tags/suggestions", params={"q": "%"}).json() == []


async def test_a_tag_named_like_an_existing_concept_is_related_to_it(api, sessionmaker):
    from app.concepts import resolve_concept

    meeting = create_meeting(api, "Con concepto")
    async with sessionmaker() as session:
        kafka = await resolve_concept(session, "technology", "Kafka")
        await session.commit()
    tag = add(api, meeting["id"], "KAFKA").json()

    async with sessionmaker() as session:
        relations = (await session.execute(select(MemoryConceptRelationship))).scalars().all()
    assert [
        (r.source_concept_id, r.target_concept_id, r.relationship_type, r.source_type)
        for r in relations
    ] == [(tag["concept_id"], kafka.id, "related_to", "manual_user")]
    # Adding the same tag to another meeting does not create the relationship twice.
    other = create_meeting(api, "Otra")
    add(api, other["id"], "kafka")
    async with sessionmaker() as session:
        assert len((await session.execute(select(MemoryConceptRelationship))).scalars().all()) == 1


async def test_deleting_the_meeting_removes_its_assignments_but_keeps_the_tag(api, sessionmaker):
    meeting = create_meeting(api, "Para borrar")
    keep = create_meeting(api, "Se queda")
    add(api, meeting["id"], "compartida")
    add(api, keep["id"], "compartida")
    assert api.delete(f"/api/meetings/{meeting['id']}").status_code == 204

    async with sessionmaker() as session:
        rows = (await session.execute(select(MemoryConceptAssignment))).scalars().all()
    assert [r.meeting_id for r in rows] == [keep["id"]]
    assert len(await concepts(sessionmaker, concept_type="tag")) == 1


def test_the_meeting_list_carries_each_meetings_tags(api):
    tagged = create_meeting(api, "Con etiquetas")
    create_meeting(api, "Sin etiquetas")
    add(api, tagged["id"], "uno")
    add(api, tagged["id"], "dos")
    by_title = {
        m["title"]: [t["label"] for t in m["tags"]] for m in api.get("/api/meetings").json()
    }
    assert by_title == {"Con etiquetas": ["uno", "dos"], "Sin etiquetas": []}


def test_the_literal_tags_route_is_not_taken_for_a_meeting_id(api):
    response = api.get("/api/meetings/tags")
    assert response.status_code == 200 and response.json() == []


def test_a_meeting_can_be_created_with_tags(api):
    earlier = api.post("/api/meetings", json={"title": "Antes"}).json()
    api.post(f"/api/meetings/{earlier['id']}/tags", json={"label": "Trèvol"})

    response = api.post(
        "/api/meetings",
        json={"title": "Nueva", "tags": ["trevol", "Cliente X", " cliente  x ", "Ramón"]},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    # Repeated spellings are one tag; an existing tag is reused, not duplicated.
    assert sorted(t["label"] for t in created["tags"]) == ["Cliente X", "Ramón", "trevol"]
    summaries = {t["label"]: t["meetings"] for t in api.get("/api/meetings/tags").json()}
    assert summaries["Trèvol"] == 2
    assert api.get(f"/api/meetings/{created['id']}").json()["tags"] == created["tags"]


def test_an_invalid_tag_at_creation_creates_nothing(api):
    before = len(api.get("/api/meetings").json())
    bad = api.post("/api/meetings", json={"title": "Nueva", "tags": ["ok", "x" * 61]})
    assert bad.status_code == 422 and bad.json()["detail"] == "INVALID_TAG"
    too_many = api.post(
        "/api/meetings", json={"title": "Nueva", "tags": [f"t{i}" for i in range(21)]}
    )
    assert too_many.status_code == 422
    assert len(api.get("/api/meetings").json()) == before
