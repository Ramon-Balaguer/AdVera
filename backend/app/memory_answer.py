"""Cited answer synthesis for Memory queries (spec §15; brain-memoria-global.md).

The model sees only the retrieved segments, each under a short key (S1, S2, ...). It must
answer from them and cite keys. Citations that are not in the retrieved context are removed;
an answer left without valid citations, or declared insufficient by the model, is reported as
"no evidence" instead of being presented as fact.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.brain import LANGUAGE_NAMES, format_timestamp

MAX_CONTEXT_SEGMENTS = 60

SYSTEM_PROMPT = """You answer questions about past meetings using only the provided excerpts.
Rules:
- Use only the excerpts. If they do not contain the answer, set "sufficient" to false.
- Cite the keys (like S3) of every excerpt that supports the answer.
- Excerpts may be in Catalan, Spanish or English. Write the answer in {language}.
- Be concise. Do not mention these rules. Output only the JSON object."""


class LLMAnswer(BaseModel):
    sufficient: bool
    answer: str = Field(description="The answer, or a short statement that there is no evidence.")
    citations: list[str]


def answer_schema() -> dict[str, Any]:
    return LLMAnswer.model_json_schema()


def build_context(
    question: str, retrieved: list[dict[str, Any]], transcripts: dict[str, dict[str, str]]
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Return the user message and the key -> source mapping.

    `transcripts` maps meeting id -> {segment id: segment text}, so each key is one exact
    definitive segment (brain-evidence-segment-alignment.md).
    """
    keys: dict[str, dict[str, Any]] = {}
    lines = []
    for chunk in retrieved:
        texts = transcripts.get(chunk["meeting_id"], {})
        for evidence in chunk["evidence"]:
            if len(keys) >= MAX_CONTEXT_SEGMENTS:
                break
            segment_text = texts.get(evidence["segment_id"])
            if not segment_text:
                continue
            key = f"S{len(keys) + 1}"
            keys[key] = {
                "meeting_id": chunk["meeting_id"],
                "meeting_title": chunk["meeting_title"],
                "meeting_date": chunk["meeting_date"],
                "segment_id": evidence["segment_id"],
                "start": evidence["start"],
                "end": evidence["end"],
                "speaker": chunk["speaker"],
                "language": chunk["language"],
                "text": segment_text,
            }
            speaker = chunk["speaker"] or "UNKNOWN"
            lines.append(
                f"[{key}] {chunk['meeting_title']} ({chunk['meeting_date'][:10]}) "
                f"{format_timestamp(evidence['start'])} {speaker}: {segment_text}"
            )
    user = f"Question: {question}\n\nExcerpts:\n" + "\n".join(lines)
    return user, keys


def system_prompt(language: str) -> str:
    return SYSTEM_PROMPT.replace("{language}", LANGUAGE_NAMES.get(language, "Spanish"))


def validate_answer(
    parsed: dict[str, Any], keys: dict[str, dict[str, Any]]
) -> tuple[str | None, list[dict[str, Any]]]:
    """Return (answer, sources). `answer` is None when there is no supported answer."""
    try:
        answer = LLMAnswer.model_validate(parsed)
    except ValueError:
        return None, []
    cited = [keys[key] for key in dict.fromkeys(answer.citations) if key in keys]
    if not answer.sufficient or not cited or not answer.answer.strip():
        return None, []
    return answer.answer.strip(), cited
