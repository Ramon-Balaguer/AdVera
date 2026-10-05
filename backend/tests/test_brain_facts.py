"""The facts of a Summary as Brain rows (ADR 0024). No database."""

from app.brain_worker import project_facts


def evidence(segment="system-00001"):
    return [{"segment_id": segment, "start": 3.0, "track": "system", "text": "cita"}]


def test_each_category_becomes_its_kind_in_the_order_of_the_summary():
    result = {
        "decisions": [{"text": "Migrar a Redis", "state": "decided", "evidence": evidence()}],
        "actions": [
            {
                "text": "Preparar el informe",
                "owner": "Marta",
                "due_date": "viernes",
                "evidence": [],
            },
            {"text": "Revisar costes", "evidence": evidence("system-00002")},
        ],
        "risks": [{"text": "Falta de GPU", "evidence": evidence()}],
        "open_questions": [{"text": "¿Quién paga?", "evidence": evidence()}],
        "topics": [{"text": "Almacenamiento", "evidence": evidence()}],
    }
    facts = project_facts(result, "m1", "j1")

    assert [(f.kind, f.position, f.text) for f in facts] == [
        ("decision", 0, "Migrar a Redis"),
        ("action", 0, "Preparar el informe"),
        ("action", 1, "Revisar costes"),
        ("risk", 0, "Falta de GPU"),
        ("question", 0, "¿Quién paga?"),
        ("topic", 0, "Almacenamiento"),
    ]
    decision, first_action, second_action = facts[0], facts[1], facts[2]
    assert (
        decision.state == "decided"
        and decision.meeting_id == "m1"
        and decision.summary_job_id == "j1"
    )
    assert (first_action.owner, first_action.due_date) == ("Marta", "viernes")
    assert (second_action.owner, second_action.due_date) == (None, None)
    assert decision.evidence[0]["segment_id"] == "system-00001"


def test_only_decisions_keep_a_state_and_odd_items_are_skipped():
    result = {
        "actions": [{"text": "Hacer algo", "state": "decided"}, {"text": "  "}, {"text": None}, {}],
        "topics": None,
    }
    [fact] = project_facts(result, "m1", "j1")
    assert fact.kind == "action" and fact.state is None and fact.evidence == []


def test_a_summary_without_facts_projects_nothing():
    assert project_facts({}, "m1", "j1") == []
