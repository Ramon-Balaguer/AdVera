"""Brain extraction contract, prompt and validation (spec §11; ADR 0002, 0009).

The Brain reads only the persisted definitive transcript. The model must cite the segment
ids it relies on; unknown ids are discarded and an item left without valid evidence is
dropped, so every stored item resolves to meeting, segment and timestamp (spec §3.2). The
model distinguishes conversation, proposal and decision and never turns a mention into a
decision. Textual fields are written in the job's output language (ADR 0009).
"""

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.concepts import canonical_key, display_name
from app.prompt_text import DATA_NOT_INSTRUCTIONS, prompt_text
from app.transcripts import TranscriptDocument

# v2 adds concepts and relationships for the concept graph (ADR 0019); v3 asks for every
# relationship the transcript supports (v2 left most concepts unconnected); v4 names concepts in
# the output language with the spoken name as an alias, and forbids generic words ("projecte"
# and "documentación" were two nodes; "proyecto" was a hub); v5 bounds every list, citations
# above all: on a 73-minute podcast the model cited segment after segment (866 in a row for
# one concept) until the context ran out. A new version changes the idempotency key, so every
# meeting gets a fresh extraction. v6 adds the participants' notes (cited by block, with their
# @references expanded) and the speakers' names (ADR 0020, ADR 0021); v7 makes the notes part
# of what must be extracted (on a real run v6 read them and left them out); v8 moves what the
# notes reference out of the notes into a section marked as other meetings (a real run took a
# referenced meeting's Catalan summary, with its speakers, for this meeting) and insists on the
# output language and on this meeting's people as owners; v9 scales the number of concepts and
# relationships with the length of the meeting (a fixed 15 left a 73-minute podcast sparse);
# v10 adds a second pass that looks only for relationships between the concepts already found
# (the first pass gave mostly related_to and left many concepts unconnected).
PROMPT_VERSION = "brain-extraction-v10"
OUTPUT_RESERVE_TOKENS = 8192

LANGUAGE_NAMES = {"es": "Spanish", "en": "English", "ca": "Catalan"}
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
MAX_CONCEPTS = 40
MAX_RELATIONSHIPS = 60
MAX_ALIASES = 5
MAX_CITATIONS = 5  # per item: a few representative segments, not every mention
MAX_ITEMS = 20  # per category of facts (topics, decisions, actions, questions, risks)


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


class LLMRelationsOutput(BaseModel):
    """What the second pass returns: relationships only."""

    relationships: list[LLMRelationship] = Field(default_factory=list)


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


# (longest meeting in minutes, concepts, relationships): a long meeting talks about more things,
# and a fixed small number made the graph of a 73-minute podcast sparse. The schema sent to the
# model and the validation use the same numbers, so a runaway answer is still bounded.
GRAPH_SIZES = ((15, 15, 20), (45, 25, 35), (float("inf"), MAX_CONCEPTS, MAX_RELATIONSHIPS))


def graph_limits(duration_seconds: float) -> tuple[int, int]:
    """How many concepts and relationships to ask for, and to keep, for a meeting this long."""
    minutes = max(0.0, duration_seconds) / 60
    for longest, concepts, relationships in GRAPH_SIZES:
        if minutes <= longest:
            return concepts, relationships
    return GRAPH_SIZES[-1][1], GRAPH_SIZES[-1][2]


def transcript_seconds(transcript: TranscriptDocument) -> float:
    return max((segment.end for segment in transcript.segments), default=0.0)


def output_schema(duration_seconds: float = 0.0) -> dict[str, Any]:
    """The JSON schema sent to the model. `concepts` and `relationships` default to empty so an
    older stored output still validates, but they must be required here: an optional field is
    simply left out by a model constrained to the schema (seen on the first real run)."""
    schema = LLMBrainOutput.model_json_schema()
    required = schema.setdefault("required", [])
    for name in ("concepts", "relationships"):
        if name not in required:
            required.append(name)
    # Bounds the model cannot pass: Ollama turns the schema into the grammar it samples with.
    # Validation applies the same bounds, so an older or unconstrained output is cut, not
    # rejected (stored outputs keep validating).
    max_concepts, max_relationships = graph_limits(duration_seconds)
    limits = {
        "evidence_ids": MAX_CITATIONS,
        "summary_evidence_ids": MAX_CITATIONS,
        "aliases": MAX_ALIASES,
        "concepts": max_concepts,
        "relationships": max_relationships,
        **{name: MAX_ITEMS for name in CATEGORIES},
    }
    for node in [schema, *schema.get("$defs", {}).values()]:
        for name, field in node.get("properties", {}).items():
            if name in limits and field.get("type") == "array":
                field["maxItems"] = limits[name]
    return schema


SYSTEM_PROMPT = (
    """You analyze the definitive transcript of a meeting and extract knowledge.
Rules:
- Use only what is said in the transcript. Never invent facts, owners or dates.
- Distinguish conversation, proposals and decisions. A topic being mentioned is not a decision.
  Use state "decided" only when the participants explicitly agree; "proposed" for suggestions not
  yet agreed; "rejected" when explicitly discarded; "superseded" when replaced by a later decision.
- Actions are concrete tasks someone committed to. Include the owner and due date only if stated.
- Every item must cite the ids of the transcript segments that support it: at most five, the
  clearest ones, never a list of every segment where it comes up. An id is the text
  inside the square brackets at the start of a line, written without the brackets (for example
  system-00012). Do not cite ids that do not appear in the transcript.
- The transcript, the notes and the context may be in other languages. Write every textual
  field (summary, item texts, owners' roles) in {language}, translating when needed; only
  names and quoted terms stay as written.
- Concepts are the recurring subjects worth linking across meetings: projects, products,
  technologies, people, organizations and named topics. Never make a concept of a generic word
  on its own (project, client, meeting, team, plan, version, document): name the specific
  subject instead ("database migration", not "project"), or leave it out. Give each a short
  canonical name as it would appear in a list of tags, written in {language}: translate common
  nouns ("documentació" becomes the {language} word for documentation), but keep proper names
  of people, organizations and products exactly as they are. Add as aliases the other names
  used for it in the talk, including the name as spoken when it differs from the canonical
  name. Also give its type and the ids of the segments that mention it. At most {concepts}
  concepts: the longer the meeting, the more subjects it covers, so name them all up to that
  number rather than only the first few.
- Relationships connect two of your concepts, using their exact names, and cite the segments
  that state the relation. Look for them for every concept: most concepts in a meeting are
  related to at least one other (a part of it, depends on it, decided or assigned by someone,
  constrains it). Include every relation the transcript supports, and none it does not: never
  guess one.
- Speakers may be shown with a person's name before their label, as "Ramón (SPEAKER_00)":
  always use that name, never the label, for owners and people. An owner is a person of this
  meeting.
- The meeting may come with notes a participant took, each block with its own id (note-001).
  The notes are part of this meeting's record, as much as what was said: extract what they
  state (facts for the summary and topics, decisions, actions, questions, risks, concepts) and
  cite the note id. A fact found only in the notes must still appear.
- "Context from other meetings" is what the notes refer to in OTHER meetings. It is not part
  of this meeting: never summarize it as this meeting, never take decisions, actions,
  questions, risks or owners from it, and its speaker labels and people are not this
  meeting's. Use it only to understand the notes and to name concepts and relationships, and
  cite the note id that refers to it.
- Return empty lists when a category has nothing. Output only the JSON object.
"""
    + DATA_NOT_INSTRUCTIONS
)


RELATIONS_PROMPT = (
    """You are given the transcript of a meeting and the list of concepts already extracted
from it. Find the relationships between those concepts that the meeting states.
Rules:
- Use only the concepts of the list, with their exact names, as source and target. Never
  invent a concept.
- Include a relationship only if the transcript (or the notes) states it, and cite the ids of
  the segments that state it: at most five, the clearest ones. An id is the text inside the
  square brackets at the start of a line, written without the brackets. Never guess one.
- Concepts marked "no relationship yet" were found alone: look for what each of them is
  connected to, but leave it alone if nothing is stated.
- Do not repeat the relationships already found.
- Prefer the most specific type, and use related_to only when none of the others fits:
  depends_on: "the launch depends on the security review";
  part_of: "the migration is part of the Atlas project";
  decided_by: "the budget was decided by the board";
  assigned_to: "the documentation is assigned to Marta";
  constrains: "the 8 GB memory limit constrains the choice of model";
  derived_from: "the new model derives from the previous one";
  verifies: "the performance tests verify the new version";
  related_to: two concepts that are clearly discussed together without any of the above.
- Speakers may be shown with a person's name before their label: concepts that are people
  are the people of this meeting.
- "Context from other meetings" is not part of this meeting: use it only to understand.
- Return an empty list if the meeting states no further relationship. Output only the JSON
  object.
"""
    + DATA_NOT_INSTRUCTIONS
)


def build_relations_prompt(
    transcript: TranscriptDocument,
    concepts: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    people: dict[tuple[str, str], str] | None = None,
    notes: list[tuple[str, str]] | None = None,
    context: list[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """The second pass: the same meeting plus the concepts found and the relationships so far."""
    linked = {r["source"] for r in relationships} | {r["target"] for r in relationships}
    concept_lines = [
        f"- {prompt_text(c['name'])} ({c['type']})"
        + ("" if c["name"] in linked else " - no relationship yet")
        for c in concepts
    ]
    found = [
        f"- {prompt_text(r['source'])} -[{r['type']}]-> {prompt_text(r['target'])}"
        for r in relationships
    ]
    user = (
        meeting_text(transcript, people=people, notes=notes, context=context)
        + "\n\nConcepts:\n"
        + "\n".join(concept_lines)
        + "\n\nRelationships already found:\n"
        + ("\n".join(found) if found else "(none)")
    )
    return RELATIONS_PROMPT, user


def relations_schema(duration_seconds: float = 0.0) -> dict[str, Any]:
    """The schema of the second pass, bounded like the first (citations and count)."""
    schema = LLMRelationsOutput.model_json_schema()
    schema.setdefault("required", ["relationships"])
    _, max_relationships = graph_limits(duration_seconds)
    limits = {"evidence_ids": MAX_CITATIONS, "relationships": max_relationships}
    for node in [schema, *schema.get("$defs", {}).values()]:
        for name, field in node.get("properties", {}).items():
            if name in limits and field.get("type") == "array":
                field["maxItems"] = limits[name]
    return schema


def merge_relations(
    result: dict[str, Any],
    parsed: dict[str, Any],
    transcript: TranscriptDocument,
    notes: Sequence[Any] = (),
) -> int:
    """Add the relationships of the second pass to a validated result; return how many were
    added. They are validated like the first pass's: known ends, a citation, no repeats, and
    the same size limit. A malformed answer raises BrainValidationError."""
    try:
        output = LLMRelationsOutput.model_validate(parsed)
    except ValueError:
        raise BrainValidationError("BRAIN_SCHEMA_INVALID") from None
    segments: dict[str, Any] = {segment.id: segment for segment in transcript.segments}
    segments.update({block.id: block for block in notes})
    concepts = {canonical_key(c["name"]): c for c in result["concepts"]}
    _, limit = graph_limits(transcript_seconds(transcript))
    before = len(result["relationships"])
    result["dropped_items"] += add_relationships(
        result["relationships"], output.relationships, concepts, segments, limit
    )
    return len(result["relationships"]) - before


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def build_prompt(
    transcript: TranscriptDocument,
    language: str,
    *,
    people: dict[tuple[str, str], str] | None = None,
    notes: list[tuple[str, str]] | None = None,
    context: list[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """`people` names speakers by (track, label); `notes` are (block id, block text) in order;
    `context` is (block id, what that block refers to in another meeting)."""
    max_concepts, _ = graph_limits(transcript_seconds(transcript))
    system = SYSTEM_PROMPT.replace("{language}", LANGUAGE_NAMES.get(language, "English")).replace(
        "{concepts}", str(max_concepts)
    )
    return system, meeting_text(transcript, people=people, notes=notes, context=context)


def meeting_text(
    transcript: TranscriptDocument,
    *,
    people: dict[tuple[str, str], str] | None = None,
    notes: list[tuple[str, str]] | None = None,
    context: list[tuple[str, str]] | None = None,
) -> str:
    """The transcript, the notes and the context of other meetings, as the models read them."""
    people = people or {}

    def who(segment) -> str:
        label = prompt_text(segment.speaker) or "UNKNOWN"
        name = people.get((segment.track, segment.speaker or ""))
        return f"{prompt_text(name)} ({label})" if name else label

    lines = [
        f"[{segment.id}] {format_timestamp(segment.start)} "
        f"{who(segment)} ({prompt_text(segment.language) or '?'}): "
        f"{prompt_text(segment.text)}"
        for segment in transcript.segments
    ]
    user = "Meeting transcript:\n" + "\n".join(lines)
    if notes:
        user += (
            "\n\nNotes taken by a participant during the meeting:\n"
            + "\n".join(f"[{block_id}] {note_prompt_text(text)}" for block_id, text in notes)
            + "\n\nInclude what these notes state, citing their ids, as well as the transcript."
        )
    if context:
        user += (
            "\n\nContext from other meetings, referred to by the notes (NOT this meeting):\n"
            + "\n".join(f"[{block_id}] {note_prompt_text(line)}" for block_id, line in context)
        )
    return user


def note_prompt_text(text: str) -> str:
    """A note block for the prompt: each line made safe, line breaks kept (lists, references)."""
    return "\n  ".join(prompt_text(line) for line in text.splitlines() if line.strip())


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
    unique = unique[:MAX_CITATIONS]
    return [
        {
            "segment_id": segment_id,
            "start": segments[segment_id].start,
            "end": segments[segment_id].end,
            "speaker": segments[segment_id].speaker,
            "track": segments[segment_id].track,
            # A note's ids shift when the notes are edited: keep the words that were cited.
            **(
                {"text": segments[segment_id].text} if segments[segment_id].track == "notes" else {}
            ),
        }
        for segment_id in unique
    ]


def validate_graph(
    output: "LLMBrainOutput", segments: dict[str, Any], duration_seconds: float = 0.0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Concepts and relationships that can be traced to the transcript, and how many were dropped.

    A concept without a valid citation is dropped; concepts with the same normalized name are
    one, whatever type each was given (the first type is kept; evidence and aliases merged).
    A relationship must cite the transcript and both of its ends must be concepts of this same
    extraction, found by normalized name; anything else is dropped rather than inventing a
    concept for it.
    """
    dropped = 0
    max_concepts, max_relationships = graph_limits(duration_seconds)
    concepts: dict[str, dict[str, Any]] = {}
    for item in output.concepts:
        key = canonical_key(item.name)
        cited = evidence_for(item.evidence_ids, segments)
        if not key or not cited or len(concepts) >= max_concepts and key not in concepts:
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
    # An alias that is another concept's name would make that concept resolve to this one
    # (and drop their relationship as a self-loop): such an alias is ambiguous, so it goes.
    for entry in concepts.values():
        entry["aliases"] = [a for a in entry["aliases"] if canonical_key(a) not in concepts]
    relationships: list[dict[str, Any]] = []
    dropped += add_relationships(
        relationships, output.relationships, concepts, segments, max_relationships
    )
    return list(concepts.values()), relationships, dropped


def add_relationships(
    kept: list[dict[str, Any]],
    candidates: Sequence["LLMRelationship"],
    concepts: dict[str, dict[str, Any]],
    segments: dict[str, Any],
    limit: int,
) -> int:
    """Add the candidates that can be traced to the transcript to `kept`; return how many were
    dropped. Both ends must be concepts of this extraction (found by normalized name), the
    relationship must cite the transcript, and a repeated one is the same relationship (not
    dropped, just not added twice)."""
    seen = {(canonical_key(r["source"]), canonical_key(r["target"]), r["type"]) for r in kept}
    dropped = 0
    for rel in candidates:
        source = concepts.get(canonical_key(rel.source))
        target = concepts.get(canonical_key(rel.target))
        cited = evidence_for(rel.evidence_ids, segments)
        if source is None or target is None or source is target or not cited or len(kept) >= limit:
            dropped += 1
            continue
        key = (canonical_key(source["name"]), canonical_key(target["name"]), rel.type)
        if key in seen:
            continue
        seen.add(key)
        kept.append(
            {
                "source": source["name"],
                "target": target["name"],
                "type": rel.type,
                "evidence": cited,
            }
        )
    return dropped


def validate_output(
    parsed: dict[str, Any],
    transcript: TranscriptDocument,
    language: str,
    notes: Sequence[Any] = (),
) -> tuple[dict[str, Any], str]:
    """Return the stored result document and its status (`completed` or `empty`).

    `notes` are the meeting's note blocks: citable like segments, with no time (ADR 0020).
    """
    try:
        output = LLMBrainOutput.model_validate(parsed)
    except ValueError:
        raise BrainValidationError("BRAIN_SCHEMA_INVALID") from None
    segments: dict[str, Any] = {segment.id: segment for segment in transcript.segments}
    segments.update({block.id: block for block in notes})
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
    result["concepts"], result["relationships"], graph_dropped = validate_graph(
        output, segments, transcript_seconds(transcript)
    )
    dropped += graph_dropped
    result["dropped_items"] = dropped
    empty = (
        not result["summary"]["text"]
        and not any(result[c] for c in CATEGORIES)
        and not result["concepts"]
    )
    return result, "empty" if empty else "completed"
