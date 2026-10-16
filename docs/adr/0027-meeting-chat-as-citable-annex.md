# ADR 0027: The meeting chat is a citable annex

## Status

Proposed (2026-10-16); a new capability the documentation does not cover. Awaits human review.

## Context

In a video call, part of the meeting happens in the chat: links, figures, a "yes" from someone who is muted. The meeting bot (ADR 0026) can bring that chat back. The notes already showed how text that is not speech becomes part of a meeting without being mixed into the transcript (ADR 0020).

## Decision

- **Storage.** The chat is stored per meeting in `meeting_chat_messages`, one row per message with sender, text, send time and `offset_s` (seconds from the start of the call). It is replaced as a whole when the bot's call is ingested.
- **Source.** Messages are read from every place Vexa may keep them: chat segments of the transcript (`source: "chat"`), `GET /bots/.../chat` and `data.chat_messages`. Repeats and the bot's own lines are dropped.
- **Blocks.** Each message is a citable block, like a note block: id `chat-001`…, track `chat`, speaker = sender, time = `offset_s`.
- **Summary.** Summary reads the chat in its own section ("Messages written in the meeting's chat"). Citations keep the message words, as for notes.
- **Brain.** Brain indexes one chunk per message, of the track `chat`.
- **Hashes.** The chat is part of the analysis input (`backend/app/analysis_input.py`): `summary_sha256` and `brain_sha256` include it only when it exists. Every hash made for a meeting without chat stays valid, and the prompt version does not change.
- **API and page.** `GET /api/meetings/{id}/chat` serves the chat. The meeting page has a Chat tab, and a chat citation in Summary opens it on that message.

## Consequences

- Only calls the bot attended have a chat. With Vexa 0.12, which keeps no Meet or Teams chat, the tab is empty and says why.
- Chat text is participant data, like notes. It goes with the meeting when the meeting is deleted.

## Validation and rollback

The integration test checks the stored chat, its block ids and that it enters the analysis input. Playwright covers the Chat tab. Rollback: remove the tab and the annex; the table can stay.

## Related records

- [Meeting bot (Vexa)](../features/meeting-bot-vexa.md)
- [ADR 0026: Vexa as a self-hosted capture source](0026-vexa-self-hosted-capture-source.md)
- [ADR 0020: Meeting notes and @references as a citable annex](0020-meeting-notes-and-references-as-citable-annex.md)
