"""Meeting notes: citable blocks, @references and the analysis input hash (ADR 0020/0021)."""

from app.analysis_input import combine, people_sha256
from app.notes import notes_sha256, references, split_blocks
from app.summary import build_prompt, validate_output
from tests.test_summary import llm_output, transcript

OTHER = "11111111-2222-4333-8444-555555555555"


def test_notes_are_split_in_blocks_with_stable_ids_and_headings_joined():
    markdown = (
        "# Pressupost\n\nLa Marta revisa el pressupost.\n\n"
        "- tasca u\n- tasca dos\n\n\n## Sol\n## Títol buit\n"
    )
    blocks = split_blocks(markdown)
    assert [b.id for b in blocks] == ["note-001", "note-002", "note-003"]
    assert blocks[0].markdown == "# Pressupost\nLa Marta revisa el pressupost."
    assert blocks[1].markdown == "- tasca u\n- tasca dos"
    assert blocks[2].markdown == "## Sol\n## Títol buit"  # headings with nothing after stay
    assert [b.id for b in split_blocks(markdown)] == [b.id for b in blocks]  # same text, same ids
    assert split_blocks("  \n\n ") == []
    assert all(b.track == "notes" and b.start is None for b in blocks)


def test_references_to_a_meeting_or_a_segment_are_read_from_markdown_links():
    text = (
        f"Veure [@Meet de Guillem](/meetings/{OTHER}) i "
        f"[@Meet de Guillem · 12:30](/meetings/{OTHER}?segment=system-00014)."
    )
    found = references(text)
    assert [(r.label, r.meeting_id, r.segment_id) for r in found] == [
        ("Meet de Guillem", OTHER, None),
        ("Meet de Guillem · 12:30", OTHER, "system-00014"),
    ]
    (block,) = split_blocks(text)
    assert block.text == "Veure @Meet de Guillem i @Meet de Guillem · 12:30."
    # Anything that is not exactly an app link to a meeting is not a reference.
    assert references("[@x](https://example.com/meetings/abc) [@y](/meetings/not-an-id)") == []


def test_without_notes_or_names_the_analysis_reads_exactly_the_transcript():
    assert notes_sha256("") is None and notes_sha256("  \n") is None
    assert combine("t" * 64, None, None) == "t" * 64  # every earlier job stays valid
    with_notes = combine("t" * 64, notes_sha256("Nota"), None)
    with_names = combine("t" * 64, None, people_sha256({("system", "SPEAKER_00"): "Ramón"}))
    assert len({with_notes, with_names, "t" * 64}) == 3


def test_the_prompt_names_speakers_and_appends_the_notes_with_their_references():
    system, user = build_prompt(
        transcript(),
        "es",
        people={("system", "SPEAKER_00"): "Ramón"},
        notes=[("note-001", "Revisar el pressupost")],
        context=[("note-001", '→ «Altra», 0:00:12, Marta: "Ho farem"')],
    )
    assert "Ramón (SPEAKER_00)" in user
    assert "Notes taken by a participant" in user and "[note-001] Revisar el pressupost" in user
    other = user.split("Context from other meetings", 1)
    assert len(other) == 2 and "[note-001] → «Altra», 0:00:12, Marta" in other[1]
    assert "never take decisions, actions" in system and "translating when needed" in system
    assert "A fact found only in the notes must still appear" in system


def test_a_note_block_can_be_cited_and_has_no_time():
    notes = split_blocks("El pressupost s'aprova divendres.")
    parsed = llm_output(summary_evidence_ids=["note-001"])
    result, status = validate_output(parsed, transcript(), "es", notes)
    assert result["summary"]["evidence"] == [
        {
            "segment_id": "note-001",
            "start": None,
            "end": None,
            "speaker": None,
            "track": "notes",
            "text": "El pressupost s'aprova divendres.",  # kept: ids shift when notes change
        }
    ]
    # Without the notes, the same id is unknown and dropped.
    result, _ = validate_output(parsed, transcript(), "es")
    assert result["summary"]["evidence"] == []


def test_blocks_split_exactly_as_the_frontend_does():
    # The same cases are checked against frontend/src/features/notes/blocks.ts (Playwright),
    # so a cited note-00N is the same block on both sides.
    import json
    from pathlib import Path

    fixture = Path(__file__).parents[2] / "frontend" / "tests" / "fixtures" / "note-blocks.json"
    for case in json.loads(fixture.read_text(encoding="utf-8")):
        blocks = split_blocks(case["markdown"])
        assert [b.markdown for b in blocks] == case["blocks"], case["name"]


def test_a_long_note_block_is_indexed_in_pieces_that_keep_its_id():
    from app.brain_indexing import MAX_CHUNK_CHARS, note_chunks

    long_list = "\n".join(f"- punt {i} " + "x" * 60 for i in range(40))
    chunks = note_chunks([("note-001", long_list), ("note-002", "y" * (MAX_CHUNK_CHARS * 2 + 5))])
    assert all(len(c.content) <= MAX_CHUNK_CHARS for c in chunks)
    assert {c.block_id for c in chunks} == {"note-001", "note-002"}
    assert "".join(c.content for c in chunks if c.block_id == "note-002") == "y" * (
        MAX_CHUNK_CHARS * 2 + 5
    )
    assert sum(c.content.count("- punt") for c in chunks if c.block_id == "note-001") == 40
