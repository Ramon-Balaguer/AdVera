"""Brain extraction contract, prompt and validation (spec §11; ADR 0002, 0009).

The Brain reads only the persisted definitive transcript. The model must cite the segment
ids it relies on; unknown ids are discarded and an item left without valid evidence is
dropped, so every stored item resolves to meeting, segment and timestamp (spec §3.2). The
model distinguishes conversation, proposal and decision and never turns a mention into a
decision. Textual fields are written in the job's output language (ADR 0009).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.concepts import canonical_key, display_name
from app.prompt_text import DATA_NOT_INSTRUCTIONS, prompt_text
from app.transcripts import TranscriptDocument

# v2 adds concepts and relationships for the concept graph (ADR 0019); v3 asks for every
# relationship the transcript supports (v2 left most concepts unconnected). A new version
# changes the idempotency key, so every meeting gets a fresh extraction.
PROMPT_VERSION = "brain-extraction-v3"
OUTPUT_RESERVE_TOKENS = 8192

LANGUAGE_NAMES = {"es": "Spanish", "en": "English"}
CATEGORIES = ("topics", "decisions", "actions", "open_questions", "risks")


class LLMItem(BaseModel):
    text: str = Field(description="One concise sentence.")
    evidence_ids: list[str] = Field(description="Ids of the transcript segments that support it.")


class LLMDecision(LLMItem):
    state: Literal["proposed", "decided", "rejected", "superseded", "unknown"]


class LLMAction(LLMItem):
    owner: str | None = Field(default=None, description="Speaker label or name, if stated.")
    due_date: str | None = Field(default=None, description="Due date as stated, if any.")


ConceptType = Literal["topic", "person", "organization", "project", "product", "technology"]
RelationshipType = Literal[
    "related_to",
    "depends_on",
    "part_of",
    "decided_by",
    "assigned_to",
    "constrains",
    "derived_from",
    "verifies",
]
CONCEPT_TYPES = ("topic", "person", "organization", "project", "product", "technology")
# Bounds, so one extraction cannot flood the graph; overflow is counted as dropped.
MAX_CONCEPTS = 30
MAX_RELATIONSHIPS = 40
MAX_ALIASES = 5


class LLMConcept(BaseModel):
    name: str = Field(description="Short canonical name, as it would appear in a list of tags.")
    type: ConceptType
    aliases: list[str] = Field(default_factory=list, description="Other names used in the talk.")
    evidence_ids: list[str] = Field(description="Ids of the segments that mention it.")


class LLMRelationship(BaseModel):
    source: str = Field(description="Exact name of one of the concepts above.")
    target: str = Field(description="Exact name of another of the concepts above.")
    type: RelationshipType
    evidence_ids: list[str] = Field(description="Ids of the segments that state the relation.")


class LLMBrainOutput(BaseModel):
    summary: str
    summary_evidence_ids: list[str]
    topics: list[LLMItem]
    decisions: list[LLMDecision]
    actions: list[LLMAction]
    open_questions: list[LLMItem]
    risks: list[LLMItem]
    concepts: list[LLMConcept] = Field(default_factory=list)
    relationships: list[LLMRelationship] = Field(default_factory=list)


def output_schema() -> dict[str, Any]:
    """The JSON schema sent to the model. `concepts` and `relationships` default to empty so an
    older stored output still validates, but they must be required here: an optional field is
    simply left out by a model constrained to the schema (seen on the first real run)."""
    schema = LLMBrainOutput.model_json_schema()
    required = schema.setdefault("required", [])
    for name in ("concepts", "relationships"):
        if name not in required:
            required.append(name)
    return schema


SYSTEM_PROMPT = (
    """You analyze the definitive transcript of a meeting and extract knowledge.
Rules:
- Use only what is said in the transcript. Never invent facts, owners or dates.
- Distinguish conversation, proposals and decisions. A topic being mentioned is not a decision.
  Use state "decided" only when the participants explicitly agree; "proposed" for suggestions not
  yet agreed; "rejected" when explicitly discarded; "superseded" when replaced by a later decision.
- Actions are concrete tasks someone committed to. Include the owner and due date only if stated.
- Every item must cite the ids of the transcript segments that support it. An id is the text
  inside the square brackets at the start of a line, written without the brackets (for example
  system-00012). Do not cite ids that do not appear in the transcript.
- The transcript may mix languages. Write every textual field (summary and item texts) in
  {language}, but keep names and quoted terms as spoken.
- Concepts are the recurring subjects worth linking across meetings: projects, products,
  technologies, people, organizations and named topics, never generic words. Give each a short
  canonical name (as it would appear in a list of tags, in the language it is usually called),
  its type, the other names used for it in the talk, and the ids of the segments that mention it.
  At most 15 concepts.
- Relationships connect two of your concepts, using their exact names, and cite the segments
  that state the relation. Look for them for every concept: most concepts in a meeting are
  related to at least one other (a part of it, depends on it, decided or assigned by someone,
  constrains it). Include every relation the transcript supports, and none it does not: never
  guess one.
- Return empty lists when a category has nothing. Output only the JSON object.
"""
    + DATA_NOT_INSTRUCTIONS
)


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def build_prompt(transcript: TranscriptDocument, language: str) -> tuple[str, str]:
    system = SYSTEM_PROMPT.replace("{language}", LANGUAGE_NAMES.get(language, "Spanish"))
    lines = [
        f"[{segment.id}] {format_timestamp(segment.start)} "
        f"{prompt_text(segment.speaker) or 'UNKNOWN'} ({prompt_text(segment.language) or '?'}): "
        f"{prompt_text(segment.text)}"
        for segment in transcript.segments
    ]
    user = "Meeting transcript:\n" + "\n".join(lines)
    return system, user


class BrainValidationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def evidence_for(ids: list[str], segments: dict[str, Any]) -> list[dict[str, Any]]:
    """Evidence entries for the cited ids that exist in the transcript (unknown ids dropped)."""
    # Models often copy the id with its square brackets, as in the transcript lines
    # ("[system-00007]"): the same segment, so the brackets are not part of the id.
    cleaned = [str(segment_id).strip().strip("[]").strip() for segment_id in ids]
    unique = [segment_id for segment_id in dict.fromkeys(cleaned) if segment_id in segments]
    return [
        {
            "segment_id": segment_id,
            "start": segments[segment_id].start,
            "end": segments[segment_id].end,
            "speaker": segments[segment_id].speaker,
            "track": segments[segment_id].track,
        }
        for segment_id in unique
    ]


def validate_graph(
    output: "LLMBrainOutput", segments: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Concepts and relationships that can be traced to the transcript, and how many were dropped.

    A concept without a valid citation is dropped; concepts with the same normalized name are
    one, whatever type each was given (the first type is kept; evidence and aliases merged).
    A relationship must cite the transcript and both of its ends must be concepts of this same
    extraction, found by normalized name; anything else is dropped rather than inventing a
    concept for it.
    """
    dropped = 0
    concepts: dict[str, dict[str, Any]] = {}
    for item in output.concepts:
        key = canonical_key(item.name)
        cited = evidence_for(item.evidence_ids, segments)
        if not key or not cited or len(concepts) >= MAX_CONCEPTS and key not in concepts:
            dropped += 1
            continue
        entry = concepts.setdefault(
            key,
            {"name": display_name(item.name), "type": item.type, "aliases": [], "evidence": []},
        )
        seen = {e["segment_id"] for e in entry["evidence"]}
        entry["evidence"] += [e for e in cited if e["segment_id"] not in seen]
        for alias in item.aliases[:MAX_ALIASES]:
            alias_key = canonical_key(alias)
            if (
                alias_key
                and alias_key != key
                and alias_key not in {canonical_key(a) for a in entry["aliases"]}
            ):
                entry["aliases"].append(display_name(alias))
    by_key = concepts
    relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rel in output.relationships:
        source = by_key.get(canonical_key(rel.source))
        target = by_key.get(canonical_key(rel.target))
        cited = evidence_for(rel.evidence_ids, segments)
        if (
            source is None
            or target is None
            or source is target
            or not cited
            or len(relationships) >= MAX_RELATIONSHIPS
        ):
            dropped += 1
            continue
        relationships.setdefault(
            (canonical_key(source["name"]), canonical_key(target["name"]), rel.type),
            {
                "source": source["name"],
                "target": target["name"],
                "type": rel.type,
                "evidence": cited,
            },
        )
    return list(concepts.values()), list(relationships.values()), dropped


def validate_output(
    parsed: dict[str, Any], transcript: TranscriptDocument, language: str
) -> tuple[dict[str, Any], str]:
    """Return the stored result document and its status (`completed` or `empty`)."""
    try:
        output = LLMBrainOutput.model_validate(parsed)
    except ValueError:
        raise BrainValidationError("BRAIN_SCHEMA_INVALID") from None
    segments = {segment.id: segment for segment in transcript.segments}
    dropped = 0

    def evidence(ids: list[str]) -> list[dict[str, Any]]:
        return evidence_for(ids, segments)

    summary_text = output.summary.strip()
    summary_evidence = evidence(output.summary_evidence_ids)
    if summary_text and not summary_evidence:
        summary_text = ""  # a summary without a traceable source is never stored (spec §3.2)
        dropped += 1
    result: dict[str, Any] = {
        "language": language,
        "summary": {"text": summary_text, "evidence": summary_evidence},
    }
    for category in CATEGORIES:
        kept = []
        for item in getattr(output, category):
            text = item.text.strip()
            cited = evidence(item.evidence_ids)
            if not text or not cited:
                dropped += 1  # no traceable source: never stored (spec §3.2)
                continue
            entry: dict[str, Any] = {"text": text, "evidence": cited}
            if isinstance(item, LLMDecision):
                entry["state"] = item.state
            if isinstance(item, LLMAction):
                entry["owner"] = item.owner
                entry["due_date"] = item.due_date
            kept.append(entry)
        result[category] = kept
    result["concepts"], result["relationships"], graph_dropped = validate_graph(output, segments)
    dropped += graph_dropped
    result["dropped_items"] = dropped
    empty = (
        not result["summary"]["text"]
        and not any(result[c] for c in CATEGORIES)
        and not result["concepts"]
    )
    return result, "empty" if empty else "completed"
