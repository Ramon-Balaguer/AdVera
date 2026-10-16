# Feature: Meeting bot (Vexa) for Google Meet and Teams
Status: in progress
Last updated: 2026-10-16

## Objective

Capture a remote Google Meet or Microsoft Teams call from anywhere. A self-hosted Vexa bot, "AdVera Notekeeper", joins the call and hands back its audio, the names of who spoke and the chat. AdVera then transcribes and analyses the call like any other meeting.

## Scope

- A fourth capture source next to the browser microphone, the desktop agent and the import ([ADR 0026](../adr/0026-vexa-self-hosted-capture-source.md)).
- The call's chat as a citable annex ([ADR 0027](../adr/0027-meeting-chat-as-citable-annex.md)).
- An optional Compose profile `bot` with Vexa Lite. Vexa uses AdVera's PostgreSQL server (its own `vexa` database) and needs no Whisper unless speaker names are wanted (profile `bot-names`).

Out of scope: Zoom and Jitsi, live transcripts during the call, and Vexa's own agent and workspace features.

## Acceptance criteria

- With Vexa configured, a meeting with no audio offers "Send AdVera Notekeeper to Google Meet or Teams". It accepts `https://meet.google.com/xxx-xxxx-xxx`, `https://teams.microsoft.com/meet/<id>?p=<passcode>` (also `teams.live.com` and the government clouds) and Teams `meetup-join` links. Anything else is `INVALID_MEET_URL`.
- While the bot is live, the page shows its state (on its way, joining, waiting for admission, in the call, leaving, processing) and "Remove bot". No other source can start, and the meeting is not shown as an interrupted recording.
- When the bot leaves, the meeting gets one `system` track and goes `processing`, then `ready` with AdVera's transcript. `started_at`, `ended_at` and `duration` come from the call.
- The chat appears in the Chat tab, and Summary and Brain can cite it.
- With speaker names on, the diarized speakers are named after the people Vexa heard, without replacing names the user gave.
- A lost webhook only delays ingestion: the worker polls. The ingestion runs once (lease).
- The passcode of a Teams link is never stored. The API key and the webhook secret are never returned.

## Implementation state

- **Backend:** `backend/app/meeting_bot.py` holds the Vexa client, URL parsing, lifecycle, webhook, ingestion and speaker matching.
- **Database:** migration `0011_meeting_bot_chat`.
- **Analysis input:** chat blocks in `analysis_input.py`, Summary and Brain.
- **Workers:** the poll and the speaker names run in the transcription worker. The settings are `vexa_*` in the runtime settings.
- **Frontend:** `useMeetingBot.ts`, `CaptureControls.tsx`, `MeetingChat.tsx`, `MeetingBotSettings.tsx` and the en/es/ca texts.
- **Deployment:** `bot` and `bot-names` profiles in `docker/compose.dev.yml` and `docker/compose.images-nvidia.yml`, plus the CUDA Whisper in `compose.nvidia.yml`.

What Vexa 0.12.27 does not do yet:
- It keeps no Meet or Teams chat (only Jitsi).
- It cannot write in the chat, so the consent notice is `unsupported` and the page asks the user to announce the recording.
- It cannot name speakers without its own transcription.

AdVera reads chat and sends the notice anyway, so both work as soon as Vexa supports them.

## Decisions

- **Vexa over Attendee, ScreenApp and Meeting BaaS:** it is Apache-2.0 and self-hosted, uses local Whisper, joins Meet and Teams, and has a chat model ([ADR 0026](../adr/0026-vexa-self-hosted-capture-source.md)).
- **Transcription off by default:** AdVera transcribes the recording, so Vexa's Whisper is only needed for names. The operator chose not to run a second Whisper by default (2026-10-16).
- **Shared PostgreSQL:** Vexa uses a separate database and role on AdVera's PostgreSQL server (pgvector 0.8.6 on PostgreSQL 16). The operator chose this (2026-10-16). Vexa is tested upstream on PostgreSQL 17.
- **Key provisioning:** Vexa Lite mints its API keys and cannot adopt a chosen one. The one-shot `vexa-key-init` service mints AdVera's key through Vexa's admin API, which only listens inside the Vexa container, so the service shares Vexa's network namespace. It stores the key with the Vexa URL in AdVera's runtime settings, so nothing is configured by hand.
- **Operator webhook:** Compose wires Vexa's operator callback (`VEXA_SYSTEM_WEBHOOK_URL`, private HTTP allowed) to `http://api:8000/api/integrations/vexa/webhook`. A user webhook would be refused as a private address.

## Files changed

- `backend/app/meeting_bot.py`, `backend/migrations/versions/0011_meeting_bot_chat.py`, `backend/app/models.py`, `backend/app/meeting_contracts.py`
- `backend/app/analysis_input.py`, `backend/app/summary.py`, `backend/app/summary_worker.py`, `backend/app/brain_worker.py`, `backend/app/brain_indexing.py`, `backend/app/brain_answer.py`, `backend/app/brain_retrieval.py`
- `backend/app/audio.py`, `backend/app/meetings.py`, `backend/app/people_api.py`, `backend/app/transcription_worker.py`, `backend/app/leases.py`
- `backend/app/config.py`, `backend/app/runtime_settings.py`, `backend/app/settings_api.py`, `backend/app/main.py`
- `frontend/src/features/meeting/{useMeetingBot.ts,CaptureControls.tsx,MeetingChat.tsx,MeetingPage.tsx,SummaryPanel.tsx}`, `frontend/src/features/settings/{MeetingBotSettings.tsx,SettingsPage.tsx,settingsApi.ts}`, `frontend/src/api.ts`, `frontend/src/i18n/{en,es,ca}.ts`
- `docker/compose.dev.yml`, `docker/compose.nvidia.yml`, `docker/compose.images-nvidia.yml`

## Validation

- `backend/tests/test_meeting_bot.py` (43 tests) covers:
  - URLs for Meet, Teams numeric links, Teams `meetup-join` links and the rejected cases;
  - webhook HMAC, the replay window and the legacy bearer;
  - the Vexa client against `backend/tests/fixtures/vexa`;
  - overlap matching;
  - write-only settings.
- `backend/tests/integration/test_meeting_bot.py` runs on PostgreSQL and Redis with a fake Vexa:
  - **Google Meet:** send, busy guards, admission, consent, leave, signed webhook, ffmpeg ingestion, chat, worker, speaker names and the analysis input.
  - **Teams:** passcode not stored, worker poll without a webhook, recording not ready yet.
  - **Edge cases:** user names kept, a failed bot releasing the meeting, error codes.
- `frontend/tests/e2e/meeting-bot.spec.ts` (Playwright, mocked API) covers Meet and Teams, an invalid link, a failed bot, Vexa not configured with an empty chat, and Settings.
- `frontend/tests/e2e-live/meeting-bot-live.spec.ts` runs against a real stack and real Meet and Teams calls, only with `LIVE_CONSENT=yes` (`npm run test:e2e:live`). A person must admit the bot and talk.

## Risks

- **Google or Microsoft can break it.** A change to their web clients can break joining. The image is pinned by digest: upgrade on purpose and run the live test.
- **Admission.** The host must admit the bot. Domain-restricted meetings need a Google account for the bot.
- **Overlapping voices.** With overlapping voices, about 4 to 7 % of the segments stay `SPEAKER_xx`. They can be fixed with `PUT /speakers`.
- **Consent.** The recording notice cannot be posted by Vexa 0.12: the user must announce it.
- **Dev defaults.** The Compose defaults for the Vexa admin token, the webhook secret and the storage keys are for development. Change them, and keep the Vexa port on loopback.

## Next action

- Run the live E2E against real Google Meet and Teams calls with the participants' consent.
- Confirm that Vexa's schema works on PostgreSQL 16, and record the result.
