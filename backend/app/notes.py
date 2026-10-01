"""Meeting notes: a Markdown annex to the transcript, cited by block (ADR 0020).

The notes are split into blocks (paragraphs, lists; a heading joins what follows it), each
with an id stable for the same text: `note-001`, `note-002`… A block behaves like a transcript
segment of the track "notes" without a time, so Brain and Memory can cite it.

An @reference is a plain Markdown link the editor writes:
  [@Meet de Guillem](/meetings/<id>)                       the whole meeting
  [@Meet de Guillem · 12:30](/meetings/<id>?segment=<id>)  one of its segments
"""

import hashlib
import re
from dataclasses import dataclass

MAX_NOTES_CHARS = 50_000
NOTE_TRACK = "notes"
REFERENCE = re.compile(
    r"\[@(?P<label>[^\]\n]{1,200})\]"
    r"\(/meetings/(?P<meeting>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:\?segment=(?P<segment>[A-Za-z0-9_-]{1,50}))?\)"
)
_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]")
_BLANK = re.compile(r"\n[ \t\f\v]*\n")
_SPACE = " \t\f\v\n"


@dataclass(frozen=True)
class NoteReference:
    label: str
    meeting_id: str
    segment_id: str | None


@dataclass(frozen=True)
class NoteBlock:
    """One citable block. The fields of a transcript segment that evidence needs are here too:
    a note has no time and no speaker."""

    id: str
    markdown: str
    references: tuple[NoteReference, ...]
    start: float | None = None
    end: float | None = None
    speaker: str | None = None
    track: str = NOTE_TRACK
    language: str | None = None

    @property
    def text(self) -> str:
        """The block as read: references shown as "@label"."""
        return REFERENCE.sub(lambda m: f"@{m['label']}", self.markdown)


def references(markdown: str) -> list[NoteReference]:
    return [
        NoteReference(m["label"].strip(), m["meeting"], m["segment"])
        for m in REFERENCE.finditer(markdown or "")
    ]


def split_blocks(markdown: str) -> list[NoteBlock]:
    """Blocks separated by blank lines; a heading alone joins the block after it."""
    # Only ASCII spaces and "\n" separate blocks, exactly as in frontend/.../blocks.ts.
    paragraphs = [p.strip(_SPACE) for p in _BLANK.split((markdown or "").replace("\r", ""))]
    paragraphs = [p for p in paragraphs if p]
    merged: list[str] = []
    pending = ""
    for paragraph in paragraphs:
        lines = paragraph.split("\n")
        if all(_HEADING.match(line) for line in lines):
            pending = f"{pending}\n{paragraph}".strip(_SPACE)
            continue
        merged.append(f"{pending}\n{paragraph}".strip(_SPACE) if pending else paragraph)
        pending = ""
    if pending:
        merged.append(pending)
    return [
        NoteBlock(id=f"note-{index:03d}", markdown=text, references=tuple(references(text)))
        for index, text in enumerate(merged, start=1)
    ]


def notes_sha256(markdown: str | None) -> str | None:
    """Hash of what the analysis reads; None when there are no notes."""
    text = (markdown or "").strip()
    return hashlib.sha256(text.encode()).hexdigest() if text else None
