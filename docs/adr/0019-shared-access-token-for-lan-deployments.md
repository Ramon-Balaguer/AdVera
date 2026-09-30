# ADR 0019: Shared access token for LAN deployments

## Status

Accepted (2026-09-30); amends ADR 0015 (human review requested).

## Context

ADR 0015 deferred authentication on the premise that AdVera is "only reachable from a trusted machine or network". The independent QA/Security review found that the default deployment contradicted it: the API and every datastore were published on all interfaces, so any host on the LAN could start recordings through the Capture Agent and download the audio, read every transcript, delete meetings, or point the LLM URL at a server it controls. The operator uses AdVera from other machines on the LAN, so binding everything to localhost is not an option for the API and frontend.

## Decision

- **One shared token, no users.** `API_TOKEN` gates every `/api/*` and `/ws/*` request except `GET /api/health` and `/api/session`. The Compose deployment refuses to start without it. Left unset, the API stays open exactly as ADR 0015 describes, for a single trusted machine.
- **Browsers exchange the token once** (`POST /api/session`) for an HttpOnly, `SameSite=Strict` cookie whose value is an HMAC derived from the token, never the token. The cookie covers REST calls, WebSocket handshakes and `<audio>` elements, which cannot send headers, and blocks cross-site requests. A wrong token is answered after a one second delay.
- **Non-browser clients** (the Capture Agent) send `Authorization: Bearer <token>`. The agent's token setting is the same value. `CAPTURE_AGENT_TOKEN` remains only as a legacy agent-socket check when `API_TOKEN` is unset.
- **The agent asks the person at its machine before every remote recording start.** A dialog that is not answered within 30 s, cannot be shown, or fails counts as a refusal. Unattended machines opt in with `consent = "always"` in the agent configuration or `--allow-remote-recording` for one console run.
- **Datastores are published on `127.0.0.1` only.** PostgreSQL keeps its default credentials and Redis has no password, so neither is reachable from the LAN.
- **The LLM base URL is checked when written** (and when models are discovered): link-local, unspecified, multicast and reserved addresses, cloud-metadata names and AdVera's own service names are rejected. LAN and loopback addresses stay allowed because Ollama commonly runs there. Redirects are not followed.

## Consequences

- Anyone with the token has full access; there are no users, roles, audit or per-meeting ownership. `created_by` stays `NULL` (ADR 0015).
- The token travels in clear over plain HTTP on the LAN. Use HTTPS (a reverse proxy) when the network is not trusted; the cookie should then also be marked `Secure`, which needs the proxy to terminate TLS.
- Hostname checks resolve DNS once, when the setting is written; a name that later resolves elsewhere is not caught.
- Rotating the token means editing `docker/.env` and restarting; existing browser sessions stop working.

## Validation and rollback

Unit tests cover the middleware (REST, WebSocket, bearer, cookie, wrong token), the destination rules and the agent consent flow. Rollback: unset `API_TOKEN` (and remove the requirement from Compose) to return to ADR 0015's open API.

## Related records

- [ADR 0015: Authentication deferred](0015-authentication-deferred-single-user.md)
- [Rebuild QA and security hardening](../features/rebuild-qa-security-hardening.md)
