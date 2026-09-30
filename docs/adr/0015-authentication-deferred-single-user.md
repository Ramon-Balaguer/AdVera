# ADR 0015: Authentication deferred; single-user API without login

## Status

Accepted (2026-09-30); amended by ADR 0019 (shared token for LAN use).

See [ADR 0019](0019-shared-access-token-for-lan-deployments.md): LAN deployments require a shared access token.

## Context

The specification lists authentication, password hashing and authenticated WebSockets as security requirements "from the beginning" (`meeting_manager_project_spec.md` §21). The as-built system never implemented them, and the baseline records the missing principal as the largest remaining gap. When the rebuild started, the product owner decided that authentication is not part of the current scope. Because this deviates from the specification, it is recorded here rather than left implicit.

## Decision

The rebuild ships without authentication until a later decision supersedes this one.

- The API and WebSockets serve a single trusted local user with no login, sessions or credentials.
- `meetings.created_by` and `memory_concept_assignments.source_user_id` stay nullable and are written as `NULL`, as in the as-built data model (spec §9, ADR 0013).
- No `users` or session tables are created.
- The other §21 controls that do not depend on a principal still apply: upload validation, size and duration limits, secrets through the environment, and no audio, transcript or sensitive content in logs.

## Consequences

- AdVera must only be reachable from a trusted machine or network. Exposing it beyond that requires superseding this ADR first.
- Ownership, audit and multi-user use cannot be expressed in the data model.
- Adding authentication later means touching every router and WebSocket, and backfilling or leaving `NULL` actors on existing rows.

## Validation and rollback

No authentication tests exist while this decision holds. A future ADR that introduces authentication supersedes this one and must define how pre-existing `NULL` actors are treated.

## Related records

- [ADR 0013: Manual meeting tags as memory concepts](0013-manual-meeting-tags-memory-concepts.md)
- [Rebuild bootstrap and governance](../features/rebuild-bootstrap-and-governance.md)
