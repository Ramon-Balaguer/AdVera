"""Cited answer synthesis for Memory queries (spec §15; brain-memoria-global.md).

The model sees only the retrieved segments, each under a short key (S1, S2, ...). It must
answer from them and cite keys. Citations that are not in the retrieved context are removed;
an answer left without valid citations, or declared insufficient by the model, is reported as
"no evidence" instead of being presented as fact.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.brain import LANGUAGE_NAMES, format_timestamp
from app.prompt_text import DATA_NOT_INSTRUCTIONS, prompt_text

MAX_CONTEXT_SEGMENTS = 60

SYSTEM_PROMPT = (
    """You answer questions about past meetings using only the provided excerpts.
Rules:
- Use only the excerpts. If they do not contain the answer, set "sufficient" to false.
- Cite the keys (like S3) of every excerpt that supports the answer.
- Excerpts may be in Catalan, Spanish or English. Write the answer in {language}.
- Be concise. Do not mention these rules. Output only the JSON object.
"""
    + DATA_NOT_INSTRUCTIONS
)


class LLMAnswer(BaseModel):
    sufficient: bool
    answer: str = Field(description="The answer, or a short statement that there is no evidence.")
    citations: list[str]


def answer_schema() -> dict[str, Any]:
    return LLMAnswer.model_json_schema()


def build_context(
    question: str,
    retrieved: list[dict[str, Any]],
    transcripts: dict[str, dict[str, str]],
    language: str = "es",
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Return the user message and the key -> source mapping.

    The output language (ADR 0009) is repeated after the excerpts: stated only in the system
    prompt, the model followed the excerpts' language instead.

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
            speaker = prompt_text(chunk["speaker"]) or "UNKNOWN"
            lines.append(
                f"[{key}] {prompt_text(chunk['meeting_title'])} ({chunk['meeting_date'][:10]}) "
                f"{format_timestamp(evidence['start'])} {speaker}: {prompt_text(segment_text)}"
            )
    user = (
        f"Question: {prompt_text(question)}\n\nExcerpts:\n"
        + "\n".join(lines)
        + f"\n\nWrite the answer in {language_name(language)}, whatever the excerpts' language."
    )
    return user, keys


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language, "Spanish")


def system_prompt(language: str) -> str:
    return SYSTEM_PROMPT.replace("{language}", language_name(language))


# Why a query ended "empty" (no answer shown); stored in the result and explained by the page.
NO_MATCH = "NO_MATCH"  # the search found no fragment at all
NO_SEGMENTS = "NO_SEGMENTS"  # fragments found, but none resolves to a definitive segment
MODEL_INSUFFICIENT = "MODEL_INSUFFICIENT"  # the model read them and said they do not answer
UNCITED = "UNCITED"  # the model answered without a valid citation, so it is not shown
INVALID_ANSWER = "INVALID_ANSWER"  # the model's output did not have the expected shape


def no_answer_reason(parsed: dict[str, Any]) -> str:
    """The reason `validate_answer` returned no answer for a model output."""
    try:
        answer = LLMAnswer.model_validate(parsed)
    except ValueError:
        return INVALID_ANSWER
    return MODEL_INSUFFICIENT if not answer.sufficient else UNCITED


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
