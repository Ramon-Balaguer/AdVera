# ADR 0026: Vexa as a self-hosted capture source for Google Meet and Teams

## Status

Proposed (2026-10-16); a new capture source the documentation does not cover. Awaits human review.

## Context

A meeting gets audio from the browser microphone, the desktop agent (`microphone` and `system` tracks, ADR 0010) or an imported file (ADR 0012). Remote calls are captured only if someone runs the agent on a machine in the call. A bot that joins the call as a participant captures it from anywhere, and it also knows who is speaking and can read the chat.

Four options were compared: Vexa, Attendee, ScreenApp and Meeting BaaS. Vexa was chosen for three reasons:
- It is Apache-2.0 and runs as a separate service, so it fits AdVera's licence (Elastic License 2.0; the brief said AGPL, but the licence is ELv2, see [rebuild-licence-elv2](../features/rebuild-licence-elv2.md)). Nothing of Vexa is vendored.
- It can be self-hosted with Whisper (the audio never leaves the network).
- It joins Google Meet and Microsoft Teams.

## Decision

- **A post-call source.** `POST /api/meetings/{id}/bot` sends a Vexa bot (default name "AdVera Notekeeper") to a Google Meet or Teams URL. While the bot is live, the meeting is `recording` and owned by the bot, like an agent recording. The browser microphone, the agent, an import, a second bot and deletion are all refused with `MEETING_BUSY` / `BOT_ALREADY_ACTIVE`.
- **The audio is the `system` track.** When the bot leaves, AdVera downloads its recording, converts it with the import's ffmpeg path (`media_import.convert_to_system_track`) and calls `queue_meeting_transcription`. AdVera's transcript stays the meeting's (ADR 0002), and only the extracted audio is kept (ADR 0016). Audio already stored is never replaced (`MEETING_ALREADY_RECORDED`).
- **Vexa does not transcribe by default** (`transcribe_enabled: false`). Then it needs no speech-to-text, and AdVera's PostgreSQL server holds its database (a separate `vexa` database and role).
  - In Vexa 0.12 the names of who spoke come only from Vexa's own transcript segments. With `vexa_speaker_names` on, Vexa transcribes with its own OpenAI-compatible Whisper (Compose profile `bot-names`).
  - After AdVera's transcription, each diarized label of the `system` track gets the Vexa name with the most time overlap. The names are stored as people (ADR 0021), only for speakers that have no name yet. Labels with no overlap stay `SPEAKER_xx`.
- **Lifecycle.** The bot status follows Vexa: `requested`, `joining`, `awaiting_admission`, `needs_help`, `active` and `stopping`. Then come AdVera's own steps: `ended`, `ingesting`, and finally `completed` or `failed`. A bot that fails without audio gives the meeting back (`scheduled`).
  - Vexa's signed webhook (`X-Webhook-Signature` = HMAC-SHA256 of `timestamp.body`, compared with `hmac.compare_digest`, with a 300 s replay window) only makes AdVera ask Vexa. It never changes state by itself.
  - The transcription worker polls live sessions as a fallback.
  - Ingestion is claimed `ended -> ingesting` under a lease (`app/leases.py`), so it runs once. A recording Vexa is still finalizing is retried.
- **The end of the call closes the recording.** AdVera learns the call ended because the bot leaves. Removing the bot or the host ending the call is immediate. When everyone hangs up, Vexa only sees remote silence, so AdVera sends `automatic_leave.max_time_left_alone` = `vexa_leave_alone_seconds` (default 120 s; Vexa's own default is 10 minutes). After that silence the bot leaves as `completed(left_alone)`, and the webhook or the poll ingests the call. A shorter wait closes sooner, but a silence that long during a live call ends the recording too.
- **Consent.** When the bot is admitted, AdVera tries to say in the call's chat that the meeting is recorded. Vexa 0.12 cannot write in the chat, so the session records `consent_notice = unsupported` and the page asks the user to tell the participants.
- **Pinned and optional.** Compose profile `bot` runs `vexaai/vexa-lite` pinned by tag and digest, plus versitygw storage. Without the profile and a configured URL, the feature is hidden.
- **Errors:** `INVALID_MEET_URL` 400, `BOT_ALREADY_ACTIVE` 409, `MEETING_ALREADY_RECORDED` 409, `MEETING_BUSY` 409, `BOT_PROVIDER_UNAVAILABLE` 502, `BOT_PROVIDER_NOT_CONFIGURED` 503.

## Consequences

- **Google can break it.** Vexa automates Google's and Microsoft's web clients, so a UI change there can break joining. The image is pinned, and an upgrade is deliberate.
- **Admission.** The host must admit the bot. A meeting restricted to a domain needs a Google account for the bot.
- **Unnamed segments.** With overlapping voices, a few segments (around 4 to 7 %) stay unnamed. They can be named with `PUT /speakers`.
- **No Meet or Teams chat yet.** Vexa 0.12 keeps no chat for Meet and Teams (only Jitsi). AdVera reads it from every place Vexa may put it, so it arrives when Vexa provides it (ADR 0027).
- **Passcodes are not stored.** A Teams passcode is sent to Vexa but never stored in AdVera.

## Validation and rollback

- **Unit tests** (`backend/tests/test_meeting_bot.py`): URL validation, webhook signatures, the Vexa client against fixtures, overlap matching and settings.
- **Integration tests** (`backend/tests/integration/test_meeting_bot.py`): Google Meet and Teams flows on PostgreSQL and Redis with ffmpeg and the worker.
- **Playwright with a mocked API** (`frontend/tests/e2e/meeting-bot.spec.ts`).
- **An opt-in live test against real calls** (`frontend/tests/e2e-live`, `LIVE_CONSENT=yes`).
- **Rollback:** leave the URL empty or remove the profile; migration 0011 only adds tables.

## Related records

- [Meeting bot (Vexa)](../features/meeting-bot-vexa.md)
- [ADR 0027: The meeting chat is a citable annex](0027-meeting-chat-as-citable-annex.md)
- [ADR 0002: Definitive transcript is the source of truth](0002-definitive-transcript-source-of-truth.md)
- [ADR 0012: External media import](0012-external-media-import.md)
- [ADR 0021: Speakers named as people](0021-speakers-named-as-people.md)
