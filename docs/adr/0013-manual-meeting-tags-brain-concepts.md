# 0013 Manual Meeting Tags as Brain Concepts

## Status

Accepted (2026-09-26)

## Context

Manual tags are user-authored metadata. They cannot be represented as transcript-derived `BrainConceptMention` rows because those rows require a brain index job and transcript evidence.

## Decision

Persist each meeting-to-tag relationship in `brain_concept_assignments`. Tags use `BrainConcept.concept_type="tag"` and the existing canonicalization rules. A unique canonical key reuses tags across meetings, while a unique meeting/concept pair makes assignment idempotent. The graph combines manual assignments with transcript-derived mentions and exposes tag meeting references without transcript evidence. Matching an existing non-tag concept may create a best-effort `related_to` relationship with `source_type="manual_user"`.

Removing an assignment never removes the shared concept or another meeting's assignment. The actor id remains nullable until authentication provides a stable principal.

## Consequences

Manual tags are visible in the concept graph but have empty `evidence_ids`; they must not be treated as transcript evidence. Relationship resolution is non-blocking and exact-match only in the first increment.

## Validation and rollback

Validate canonicalization, idempotency, cross-meeting reuse, deletion isolation, suggestions, graph filtering, and meeting-delete cascade through API tests. Rollback removes the tag endpoints and assignment table; existing shared concepts are not deleted automatically.

## Related records
- [Meeting free-text tags and brain concepts](../features/meeting-free-text-tags-brain-concepts.md)