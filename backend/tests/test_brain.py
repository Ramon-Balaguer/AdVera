"""Brain contract, prompt and validation. No LLM, network or database."""

from datetime import UTC, datetime

import pytest

from app.brain import BrainValidationError, build_prompt, output_schema, validate_output
from app.brain_jobs import idempotency_key
from app.transcripts import TranscriptDocument, TranscriptProvenance, TranscriptSegment


def transcript() -> TranscriptDocument:
    segments = [
        TranscriptSegment(
            id="system-00000",
            start=0.0,
            end=4.0,
            text="Proposem usar Kafka.",
            track="system",
            language="ca",
            speaker="SPEAKER_00",
        ),
        TranscriptSegment(
            id="system-00001",
            start=4.5,
            end=8.0,
            text="De acuerdo, lo decidimos.",
            track="system",
            language="es",
            speaker="SPEAKER_01",
        ),
        TranscriptSegment(
            id="system-00002",
            start=8.5,
            end=12.0,
            text="Emma will write the doc.",
            track="system",
            language="en",
            speaker="SPEAKER_02",
        ),
    ]
    return TranscriptDocument(
        meeting_id="m",
        generated_at=datetime.now(UTC),
        segments_sha256="h",
        primary_language=["ca", "es", "en"],
        provenance=TranscriptProvenance(job_id="j", input_sha256="i", tracks=[]),
        segments=segments,
    )


def llm_output(**overrides):
    base = {
        "summary": "Se decide usar Kafka.",
        "summary_evidence_ids": ["system-00001"],
        "topics": [{"text": "Mensajería", "evidence_ids": ["system-00000"]}],
        "decisions": [
            {
                "text": "Usar Kafka",
                "evidence_ids": ["system-00000", "system-00001"],
                "state": "decided",
            }
        ],
        "actions": [
            {
                "text": "Escribir el documento",
                "evidence_ids": ["system-00002"],
                "owner": "Emma",
                "due_date": None,
            }
        ],
        "open_questions": [],
        "risks": [],
    }
    return base | overrides


def test_prompt_lists_every_segment_with_id_speaker_and_language_and_the_output_language():
    system, user = build_prompt(transcript(), "en")
    assert "in\n  English" in system or "in English" in system.replace("\n  ", " ")
    assert "[system-00001] 0:00:04 SPEAKER_01 (es): De acuerdo, lo decidimos." in user
    assert "A topic being mentioned is not a decision" in system


def test_valid_output_resolves_evidence_to_timestamps():
    result, status = validate_output(llm_output(), transcript(), "es")
    assert status == "completed"
    decision = result["decisions"][0]
    assert decision["state"] == "decided"
    assert [e["segment_id"] for e in decision["evidence"]] == ["system-00000", "system-00001"]
    assert (
        decision["evidence"][1]["start"] == 4.5
        and decision["evidence"][1]["speaker"] == "SPEAKER_01"
    )
    assert result["actions"][0]["owner"] == "Emma"
    assert result["summary"]["evidence"][0]["segment_id"] == "system-00001"
    assert result["language"] == "es" and result["dropped_items"] == 0


def test_unknown_citations_are_removed_and_uncited_items_dropped():
    output = llm_output(
        risks=[
            {"text": "Invented risk", "evidence_ids": ["system-99999"]},
            {"text": "Partly real", "evidence_ids": ["nope", "system-00002", "system-00002"]},
        ]
    )
    result, _ = validate_output(output, transcript(), "es")
    assert [r["text"] for r in result["risks"]] == ["Partly real"]
    assert [e["segment_id"] for e in result["risks"][0]["evidence"]] == ["system-00002"]
    assert result["dropped_items"] == 1


def test_nothing_found_is_empty_not_completed():
    output = llm_output(summary="", summary_evidence_ids=[], topics=[], decisions=[], actions=[])
    assert validate_output(output, transcript(), "es")[1] == "empty"


def test_schema_violations_are_rejected():
    with pytest.raises(BrainValidationError):
        validate_output({"summary": "x"}, transcript(), "es")
    bad_state = llm_output(
        decisions=[{"text": "x", "evidence_ids": ["system-00000"], "state": "maybe"}]
    )
    with pytest.raises(BrainValidationError):
        validate_output(bad_state, transcript(), "es")


def test_schema_is_a_json_schema_with_every_category():
    schema = output_schema()
    assert set(schema["required"]) >= {"summary", "decisions", "actions", "topics", "risks"}


def test_output_language_makes_a_distinct_job():
    es = idempotency_key("m", "h", "ollama", "model", "v1", "es")
    en = idempotency_key("m", "h", "ollama", "model", "v1", "en")
    assert es != en
