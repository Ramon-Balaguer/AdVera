# Feature: Rebuild tags at meeting creation and search by several tags
Status: complete
Last updated: 2026-10-01

## Objective

Let the user tag a meeting when creating it, with the tags already used offered while typing, and search Brain across all the tags they choose. Tags name projects, companies, people or concepts; they are plain words, as in ADR 0013, and appear in the concept graph as tag nodes (`rebuild-concept-graph-and-tags.md`).

## Scope

In scope:
- `POST /api/meetings` accepts `tags` (at most 20; each validated like `POST /api/meetings/{id}/tags`: not empty, at most 60 characters, `422 INVALID_TAG` before anything is created). Repeated spellings of one tag are assigned once; existing tags are reused. The response carries the meeting's tags.
- Brain search filter `tags` (at most 20): meetings with any of the chosen tags, resolved before ranking. The single `tag` filter is still accepted and joins the list.
- A tag picker (`frontend/src/features/tags/TagPicker.tsx`): chips, suggestions of existing tags while typing (accents, case and spacing ignored; prefix matches and the most used first; arrows, Enter, Esc, Backspace), and Enter to create a new tag where new tags are allowed. Used in the new meeting form (new tags allowed) and in the Brain question form (existing tags only).

Out of scope: a type for tags (the operator chose plain words), matching all tags at once, several tags in the graph filter.

## Acceptance criteria

1. A meeting can be created with tags; an existing tag typed in another spelling is reused, never duplicated.
2. Typing offers the existing tags that match.
3. Brain can be searched with several tags and returns meetings carrying any of them.
4. An invalid tag at creation creates no meeting.

## Implementation state

Implemented, tested and deployed.

## Decisions

- Several tags match any of them, not all (operator decision, 2026-10-01).
- Tags have no type (operator decision, 2026-10-01).
- Tag assignment is one function (`assign_tag`) shared by creation and the tag endpoint, so the rules, the limit and the related-to link of ADR 0013 are the same.

## Files changed

- `backend/app/{tags_api,meetings,meeting_contracts,brain_retrieval,brain_api}.py`
- `backend/tests/integration/{test_tags,test_brain_pipeline}.py`
- `frontend/src/features/tags/TagPicker.tsx` (new), `frontend/src/features/meetings/MeetingsPage.tsx`, `frontend/src/features/brain/BrainPage.tsx`, `frontend/src/{api.ts,styles.css}`
- `frontend/tests/e2e/tags-graph.spec.ts`

## Validation

- Integration: creation with tags (reuse across spellings, repeats once, counts), invalid or too many tags create nothing; Brain search with several tags (any of them, unknown tags ignored).
- E2E (mocked): creating a meeting with an existing tag found without accents, a new tag with Enter, keyboard choice of a suggestion, no duplicate in another spelling, removing a chip; the Brain picker sends `tags` and refuses a tag that does not exist.

## Risks

- None known.

## Next action

None.
