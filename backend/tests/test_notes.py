"""Meeting notes: citable blocks, @references and the analysis input hash (ADR 0020/0021)."""

from app.analysis_input import combine, people_sha256
from app.brain import build_prompt, validate_output
from app.notes import notes_sha256, references, split_blocks
from tests.test_brain import llm_output, transcript

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
        notes=[("note-001", 'Revisar el pressupost\n→ «Altra», 0:00:12, Marta: "Ho farem"')],
    )
    assert "Ramón (SPEAKER_00)" in user
    assert "Notes taken by a participant" in user and "[note-001] Revisar el pressupost" in user
    assert "→ «Altra», 0:00:12, Marta" in user
    assert "never as decisions, actions" in system
    assert "A fact found only in the notes must still appear" in system


def test_a_note_block_can_be_cited_and_has_no_time():
    notes = split_blocks("El pressupost s'aprova divendres.")
    parsed = llm_output(summary_evidence_ids=["note-001"])
    result, status = validate_output(parsed, transcript(), "es", notes)
    assert result["summary"]["evidence"] == [
        {"segment_id": "note-001", "start": None, "end": None, "speaker": None, "track": "notes"}
    ]
    # Without the notes, the same id is unknown and dropped.
    result, _ = validate_output(parsed, transcript(), "es")
    assert result["summary"]["evidence"] == []
