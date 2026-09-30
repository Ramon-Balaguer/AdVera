"""Brain extraction contract, prompt and validation (spec §11; ADR 0002, 0009).

The Brain reads only the persisted definitive transcript. The model must cite the segment
ids it relies on; unknown ids are discarded and an item left without valid evidence is
dropped, so every stored item resolves to meeting, segment and timestamp (spec §3.2). The
model distinguishes conversation, proposal and decision and never turns a mention into a
decision. Textual fields are written in the job's output language (ADR 0009).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.prompt_text import DATA_NOT_INSTRUCTIONS, prompt_text
from app.transcripts import TranscriptDocument

PROMPT_VERSION = "brain-extraction-v1"
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


class LLMBrainOutput(BaseModel):
    summary: str
    summary_evidence_ids: list[str]
    topics: list[LLMItem]
    decisions: list[LLMDecision]
    actions: list[LLMAction]
    open_questions: list[LLMItem]
    risks: list[LLMItem]


def output_schema() -> dict[str, Any]:
    return LLMBrainOutput.model_json_schema()


SYSTEM_PROMPT = (
    """You analyze the definitive transcript of a meeting and extract knowledge.
Rules:
- Use only what is said in the transcript. Never invent facts, owners or dates.
- Distinguish conversation, proposals and decisions. A topic being mentioned is not a decision.
  Use state "decided" only when the participants explicitly agree; "proposed" for suggestions not
  yet agreed; "rejected" when explicitly discarded; "superseded" when replaced by a later decision.
- Actions are concrete tasks someone committed to. Include the owner and due date only if stated.
- Every item must cite the ids of the transcript segments that support it, exactly as written
  between square brackets. Do not cite ids that do not appear in the transcript.
- The transcript may mix languages. Write every textual field (summary and item texts) in
  {language}, but keep names and quoted terms as spoken.
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
        unique = [segment_id for segment_id in dict.fromkeys(ids) if segment_id in segments]
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
    result["dropped_items"] = dropped
    empty = not result["summary"]["text"] and not any(result[c] for c in CATEGORIES)
    return result, "empty" if empty else "completed"
