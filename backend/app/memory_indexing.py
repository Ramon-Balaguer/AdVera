"""Definitive-transcript chunking for Memory (brain-memoria-global.md; ADR 0002).

A chunk is a run of consecutive segments from the same track and speaker, capped by length
and duration. A segment is never split, so every chunk keeps exact segment ids and
timestamps. Only a valid definitive transcript can be chunked.

The meeting's notes are indexed too (ADR 0020): one chunk per note block, of the track
"notes", with what its @references point to appended so a search finds the note by them.
A note has no time: its chunk and evidence use 0.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass

from app.transcripts import TranscriptDocument, TranscriptSegment

PROJECTION_VERSION = "memory-chunks-v1"
MAX_CHUNK_CHARS = 800
MAX_CHUNK_SECONDS = 60.0


@dataclass(frozen=True)
class Chunk:
    segments: tuple[TranscriptSegment, ...]

    @property
    def content(self) -> str:
        return " ".join(segment.text for segment in self.segments)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()

    @property
    def start(self) -> float:
        return self.segments[0].start

    @property
    def end(self) -> float:
        return max(segment.end for segment in self.segments)

    @property
    def speaker(self) -> str | None:
        return self.segments[0].speaker

    @property
    def track(self) -> str:
        return self.segments[0].track

    @property
    def language(self) -> str | None:
        languages = Counter(segment.language for segment in self.segments if segment.language)
        return languages.most_common(1)[0][0] if languages else None


@dataclass(frozen=True)
class NoteSegment:
    id: str
    start: float = 0.0
    end: float = 0.0


@dataclass(frozen=True)
class NoteChunk:
    """A note block as a Memory chunk: same fields the indexer reads from a Chunk."""

    block_id: str
    content: str
    start: float = 0.0
    end: float = 0.0
    speaker: str | None = None
    track: str = "notes"
    language: str | None = None

    @property
    def segments(self) -> tuple[NoteSegment, ...]:
        return (NoteSegment(self.block_id),)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def note_chunks(blocks: list[tuple[str, str]]) -> list[NoteChunk]:
    """(block id, text with its resolved references) -> chunks of at most MAX_CHUNK_CHARS.

    A long block (a long list, many references) is cut on line boundaries, a line longer than
    that on the limit, so every piece can be embedded whole; all pieces keep the block id.
    """
    chunks = []
    for block_id, text in blocks:
        piece = ""
        for line in text.split("\n"):
            while len(line) > MAX_CHUNK_CHARS:
                if piece.strip():
                    chunks.append(NoteChunk(block_id, piece.strip()))
                    piece = ""
                chunks.append(NoteChunk(block_id, line[:MAX_CHUNK_CHARS]))
                line = line[MAX_CHUNK_CHARS:]
            if piece and len(piece) + 1 + len(line) > MAX_CHUNK_CHARS:
                chunks.append(NoteChunk(block_id, piece.strip()))
                piece = ""
            piece = f"{piece}\n{line}" if piece else line
        if piece.strip():
            chunks.append(NoteChunk(block_id, piece.strip()))
    return chunks


def build_chunks(transcript: TranscriptDocument) -> list[Chunk]:
    if transcript.status != "definitive":
        raise ValueError("only definitive transcripts are indexed")
    chunks: list[Chunk] = []
    current: list[TranscriptSegment] = []
    for segment in transcript.segments:
        if current:
            head = current[0]
            length = sum(len(item.text) + 1 for item in current) + len(segment.text)
            same_turn = segment.track == head.track and segment.speaker == head.speaker
            if (
                not same_turn
                or length > MAX_CHUNK_CHARS
                or segment.end - head.start > MAX_CHUNK_SECONDS
            ):
                chunks.append(Chunk(tuple(current)))
                current = []
        current.append(segment)
    if current:
        chunks.append(Chunk(tuple(current)))
    return chunks
