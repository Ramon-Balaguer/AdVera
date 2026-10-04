# Meeting Free-Text Tags and Brain Concepts
Status: partial
Last updated: 2026-09-30

## Product Brief

### Problem

Users cannot manually classify a meeting with reusable free-text tags or connect those classifications to the global brain graph.

### Target user

Users who review meetings and need to group and retrieve recurring topics, projects, people, or themes.

### Desired outcome

Users can add and remove free-text tags on a meeting, receive existing-tag suggestions while typing, and see each tag represented as a brain concept linked to its assigned meetings and related concepts.

### Smallest useful increment

Implement the complete lifecycle for a manually assigned meeting tag: suggest existing tags, add and persist a tag, reload it, remove the meeting assignment, and project the tag as a brain concept linked to the meeting.

### In scope

- Free-text tag entry and removal on a meeting.
- Existing-tag suggestions while the user types.
- Canonical normalization and case-insensitive reuse of tags.
- Persistent meeting-to-tag assignment.
- Tag concepts in the brain graph with assigned meeting references.
- Best-effort relationships from tag concepts to existing brain concepts when the resolver has sufficient evidence.
- Loading, empty, validation, conflict, and failure states.

### Out of scope

- Automatic tagging from provisional transcripts.
- Global tag deletion from the brain graph.
- Bulk tag management across meetings.
- New permissions or sharing rules beyond the existing meeting and brain boundaries.

### User acceptance criteria

1. A user can type a tag on a meeting and see matching existing tags before submitting.
2. Adding a new tag makes it visible on the meeting and it remains visible after reload.
3. Reusing a tag with different casing or surrounding whitespace does not create a duplicate concept.
4. Removing a tag removes only that meeting assignment; the concept and assignments on other meetings remain intact.
5. The brain graph exposes the tag as a concept node with the assigned meeting id and attempts relationships to compatible existing concepts.
6. Empty, invalid, duplicate, unavailable, and conflicting operations produce an actionable UI state without corrupting meeting or brain data.

### States and failure behavior

- Empty: no tags assigned and no suggestions available.
- Loading: meeting tags and suggestions are being fetched or updated.
- Ready: tags and suggestions are available.
- Validation error: blank, oversized, or otherwise invalid input is rejected locally.
- Conflict: a concurrent assignment resolves to the canonical existing tag.
- Failure: the UI preserves the current tags and reports that the operation could not be completed.

### Data and provenance constraints

- Tags are user-authored metadata, not transcript-derived intelligence.
- Definitive transcript data remains the source of truth for transcript intelligence; provisional transcript data must not create concepts or relationships.
- Preserve canonical labels, meeting references, provenance, input hashes, and model metadata for any automated relationship resolution.
- Never store chain-of-thought.
- Do not expose meeting content or secrets in logs or tests.

### Dependencies and constraints

- Existing meeting API and meeting detail workflow.
- Existing brain concept resolver, graph projection, persistence, and retrieval APIs.
- Existing SQLAlchemy/Alembic, FastAPI, React, and pytest patterns.
- Architecture/Data review is required because persistence and API contracts change.

### Assumptions

- A tag is scoped to the existing meeting access boundary.
- Removing a meeting assignment does not delete a shared concept or other meeting assignments.
- Existing concept normalization can be reused for canonical tag identity.

### Open questions

- What per-user or per-tenant permissions should apply if multi-user access is introduced?
- What exact maximum tag length and maximum tags per meeting should the product enforce?
- Which confidence/evidence threshold should permit an automatic relationship from a tag to another concept?
- What should happen to tag assignments when a meeting is deleted?

### Recommended next agent

Orchestrator, followed by Architecture/Data and coordinated Backend and Frontend implementation, then QA/Security review.

## Implementation record

- Status: Implemented; pending production migration validation and authenticated actor support.
- Acceptance check before implementation: adding, reloading, and removing one tag must preserve canonical concept identity and meeting references.
- Decisions: Manual assignments are separate from transcript-derived mentions; tags use `concept_type=tag`; assignment deletion does not delete shared concepts.
- Files changed: feature record, ADR, models, contracts, tag service, migration, meeting API, brain graph API.
- Validation: 11 focused meeting API tests, 29 backend brain/job tests, frontend production build, and diagnostics for touched files pass. Disposable SQLite migration validation is blocked by the pre-existing SQLite-incompatible `0006_brain_evidence_links` migration.
- Risks: the current self-hosted API has no authentication dependency, so `source_user_id` remains nullable and access control follows the existing API boundary; run Alembic against PostgreSQL before deployment.
- Next action: apply `0013_manual_meeting_tags` on the deployment database and add actor scoping when AdVera exposes a user principal.