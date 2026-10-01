"""What the text analysis of a meeting reads, and the hash that identifies it (ADR 0020/0021).

Brain, the concept projection and Memory used to be checked against the definitive
transcript's `segments_sha256` alone. They now read the notes (with their @references
expanded) and the speakers' names too:

  brain_sha256   transcript + notes + speaker names   (Brain and its concept projection)
  memory_sha256  transcript + notes                    (Memory chunks; names are resolved
                                                         when results are read)

Without notes and names both are exactly `segments_sha256`, so every job and extraction made
before stays valid. What an @reference points to is resolved when the analysis runs; the hash
covers the references themselves (they are part of the notes text).
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrainExtraction, Meeting, MeetingNotes, MeetingSpeaker, MemoryConcept
from app.notes import NoteBlock, notes_sha256, split_blocks
from app.storage import MeetingStorage
from app.transcripts import TranscriptDocument, parse_definitive

MAX_REFERENCES = 30
MAX_REFERENCED_CHARS = 600

People = dict[tuple[str, str], str]  # (track, speaker label) -> person name


@dataclass
class AnalysisInput:
    transcript: TranscriptDocument
    notes: list[NoteBlock] = field(default_factory=list)
    # Block id -> what its @references point to, one line each (resolved when loaded).
    expansions: dict[str, list[str]] = field(default_factory=dict)
    people: People = field(default_factory=dict)
    brain_sha256: str = ""
    memory_sha256: str = ""

    def note_text(self, block: NoteBlock) -> str:
        """The block as indexed and as given to the models: its text and what it references."""
        return "\n".join([block.text, *self.expansions.get(block.id, [])])


def combine(transcript_sha: str, notes_sha: str | None, people_sha: str | None = None) -> str:
    if not notes_sha and not people_sha:
        return transcript_sha
    raw = f"{transcript_sha}|notes:{notes_sha or ''}|people:{people_sha or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def people_sha256(people: People) -> str | None:
    if not people:
        return None
    rows = sorted([track, label, name] for (track, label), name in people.items())
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


async def people_for(session: AsyncSession, meeting_ids: list[str]) -> dict[str, People]:
    """Person names of each meeting's speakers."""
    rows = (
        await session.execute(
            select(
                MeetingSpeaker.meeting_id,
                MeetingSpeaker.track,
                MeetingSpeaker.speaker_label,
                MemoryConcept.canonical_name,
            )
            .join(MemoryConcept, MemoryConcept.id == MeetingSpeaker.concept_id)
            .where(MeetingSpeaker.meeting_id.in_(meeting_ids or [""]))
        )
    ).all()
    result: dict[str, People] = {meeting_id: {} for meeting_id in meeting_ids}
    for meeting_id, track, label, name in rows:
        result.setdefault(meeting_id, {})[(track, label)] = name
    return result


async def notes_markdown(session: AsyncSession, meeting_id: str) -> str:
    notes = await session.get(MeetingNotes, meeting_id)
    return notes.content if notes else ""


async def _read(storage: MeetingStorage, meeting_id: str) -> TranscriptDocument | None:
    try:
        return parse_definitive(await asyncio.to_thread(storage.read_transcript, meeting_id))
    except (OSError, ValueError):
        return None


async def load(
    session: AsyncSession, storage: MeetingStorage, meeting_id: str, *, expand: bool = True
) -> AnalysisInput | None:
    """Everything the analysis of a meeting reads; None without a definitive transcript."""
    transcript = await _read(storage, meeting_id)
    if transcript is None:
        return None
    markdown = await notes_markdown(session, meeting_id)
    people = (await people_for(session, [meeting_id]))[meeting_id]
    notes = split_blocks(markdown)
    notes_sha = notes_sha256(markdown)
    result = AnalysisInput(
        transcript=transcript,
        notes=notes,
        people=people,
        brain_sha256=combine(transcript.segments_sha256, notes_sha, people_sha256(people)),
        memory_sha256=combine(transcript.segments_sha256, notes_sha),
    )
    if expand:
        result.expansions = await _expand(session, storage, meeting_id, notes)
    return result


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}"


async def _expand(
    session: AsyncSession, storage: MeetingStorage, meeting_id: str, notes: list[NoteBlock]
) -> dict[str, list[str]]:
    """Resolve each @reference to what it points to: a segment's words, or a meeting's summary.

    A reference to a deleted meeting, to itself or beyond MAX_REFERENCES resolves to nothing.
    """
    wanted = [
        (block.id, reference)
        for block in notes
        for reference in block.references
        if reference.meeting_id != meeting_id
    ][:MAX_REFERENCES]
    if not wanted:
        return {}
    targets = sorted({reference.meeting_id for _block, reference in wanted})
    titles = dict(
        (
            await session.execute(select(Meeting.id, Meeting.title).where(Meeting.id.in_(targets)))
        ).all()
    )
    people = await people_for(session, list(titles))
    transcripts = {
        target: await _read(storage, target)
        for target in titles
        if any(r.meeting_id == target and r.segment_id for _b, r in wanted)
    }
    summaries: dict[str, str] = {}
    for target in titles:
        latest = (
            await session.execute(
                select(BrainExtraction.result)
                .where(BrainExtraction.meeting_id == target)
                .order_by(BrainExtraction.generated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        summary = ((latest or {}).get("summary") or {}).get("text") or ""
        if summary:
            summaries[target] = summary
    expansions: dict[str, list[str]] = {}
    for block_id, reference in wanted:
        title = titles.get(reference.meeting_id)
        if title is None:
            continue  # the referenced meeting was deleted
        if reference.segment_id:
            document = transcripts.get(reference.meeting_id)
            segment = next(
                (
                    s
                    for s in (document.segments if document else [])
                    if s.id == reference.segment_id
                ),
                None,
            )
            if segment is None:
                continue
            speaker = people[reference.meeting_id].get((segment.track, segment.speaker or ""))
            words = _clip(segment.text, MAX_REFERENCED_CHARS)
            line = (
                f"→ «{_clip(title, 120)}», {_clock(segment.start)}, "
                f'{speaker or segment.speaker or "?"}: "{words}"'
            )
        else:
            summary = summaries.get(reference.meeting_id)
            line = f"→ «{_clip(title, 120)}»" + (
                f": {_clip(summary, MAX_REFERENCED_CHARS)}" if summary else ""
            )
        expansions.setdefault(block_id, []).append(line)
    return expansions
