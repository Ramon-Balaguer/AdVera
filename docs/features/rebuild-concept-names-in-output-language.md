# Feature: Rebuild concept names in the output language
Status: in progress
Last updated: 2026-10-01

## Objective

Join the same concept said in Spanish and in Catalan ("documentación", "documentació") and stop generic words ("proyecto", "projecte") from becoming the most shared nodes of the concept graph, as the operator asked after the second real backfill (`rebuild-concept-graph-and-tags.md`).

## Scope

In scope: Brain prompt `brain-extraction-v4`. Concept names are written in the output language chosen in Settings (ADR 0009, `llm_output_language`); common nouns are translated, proper names of people, organizations and products are kept as they are, and the name as spoken goes into the aliases. A generic word on its own is never a concept. A re-extraction of the existing meetings, except the operator's real "test" meeting.

Out of scope: similarity merging, a fixed list of forbidden words, translating names already stored.

## Acceptance criteria

1. The prompt asks for concept names in the Settings output language, with the spoken name as an alias.
2. The prompt forbids concepts made of a generic word alone.
3. After the re-extraction, Spanish and Catalan spellings of one subject are one node, and "proyecto"/"projecte" are not nodes.

## Implementation state

Prompt v4 implemented and unit-tested. Real re-extraction (64 of 65 meetings; "Podcast urisabat cuanto fractur" failed three times with `LLM_INVALID_JSON` and keeps its v3 extraction): 77 concepts, 72 relationships drawn, 13 without relationships, 50 shared by more than one meeting (v3: 81, 66, 15, 40). The model follows the rules only partly: some meetings now name "documentación" with "documentació" as an alias, others still say "documentació", and generic names ("cliente", "client", "document") remain. Because an exact name wins over another concept's alias, "documentació" and "documentación" are still two nodes.

## Decisions

The output language already governs every textual Brain field (ADR 0009); concept names now follow it too ([ADR 0019](../adr/0019-brain-concept-extraction-and-graph-projection.md), revised). Identity is unchanged: exact normalized name or alias, never similarity.

## Files changed

- `backend/app/brain.py`, `backend/tests/test_brain.py`
- `docs/adr/0019-brain-concept-extraction-and-graph-projection.md`

## Validation

- `pytest tests/test_brain.py`: the prompt version and the new rules are present.

## Risks

- The model may still translate a proper name, or keep a generic word; measured after the re-extraction.
- Changing the output language in Settings makes later meetings name concepts in the new language, so they join older ones only through aliases.

## Next action

Re-extract with `python -m app.memory_backfill --concepts --exclude-title test` and measure nodes, Spanish/Catalan duplicates and generic nodes.
