"""Meeting bot: a self-hosted Vexa joins a Google Meet or Teams call and hands back its audio,
the names of who spoke and the chat (ADR 0026, ADR 0027).

The bot is a post-call source. While it is in the call the meeting is `recording` and owned by
the bot, like a desktop agent recording: no other source can start. When the bot leaves, its
recording is downloaded, converted to `system.pcm` exactly like an imported file and queued for
the definitive transcription (ADR 0002: AdVera's transcript is the meeting's). The speakers
Vexa named are matched to AdVera's diarized labels by time overlap once that transcript
exists, and the chat is kept as a citable annex.

  GET    /api/meeting-bot/capabilities        configured and reachable?
  POST   /api/meetings/{id}/bot               send the bot {meet_url}
  GET    /api/meetings/{id}/bot               latest bot session of the meeting
  DELETE /api/meetings/{id}/bot               make the bot leave
  GET    /api/meetings/{id}/chat              the call's chat
  POST   /api/integrations/vexa/webhook       signed Vexa events (only a hint to check Vexa)

The webhook is never trusted for state: it only makes AdVera ask Vexa now. The transcription
worker polls live sessions as a fallback, so a lost webhook only delays ingestion. Ingestion
runs under a lease (app.leases), so two processes never ingest one call twice. Meeting URLs,
passcodes, API keys and recordings are never logged.
"""

import bisect
import contextlib
import hashlib
import hmac
import json
import logging
import re
import time
import urllib.parse
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import leases, runtime_settings
from app.concepts import canonical_key, display_name
from app.config import Settings, get_settings
from app.database import get_session
from app.job_queue import JobQueue
from app.media_import import MediaImportError, convert_to_system_track, imports_in_progress
from app.meeting_contracts import (
    BotCapabilitiesResponse,
    BotSessionResponse,
    BotStartRequest,
    ChatMessageResponse,
)
from app.models import (
    BOT_TERMINAL_STATUSES,
    Meeting,
    MeetingBotSession,
    MeetingChatMessage,
    utcnow,
)
from app.runtime_settings import RuntimeSettings
from app.storage import MeetingStorage
from app.transcription_jobs import active_job, publish, queue_meeting_transcription
from app.transcripts import TranscriptDocument

logger = logging.getLogger("advera.meeting_bot")

router = APIRouter(tags=["meeting-bot"])
Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]

PLATFORMS = ("google_meet", "teams")
# The bot's lifecycle in Vexa (docs.vexa.ai/api/meetings), then AdVera's own steps.
PROVIDER_LIVE = ("requested", "joining", "awaiting_admission", "needs_help", "active", "stopping")
LIVE_STATUSES = (*PROVIDER_LIVE, "ended", "ingesting")
CONSENT_MESSAGE = {
    "en": "{name} is recording and transcribing this meeting for AdVera.",
    "es": "{name} está grabando y transcribiendo esta reunión para AdVera.",
    "ca": "{name} està enregistrant i transcrivint aquesta reunió per a AdVera.",
}
RECORDING_PREFIX = ".bot-recording-"
MAX_WEBHOOK_BYTES = 1024 * 1024
MAX_CHAT_MESSAGES = 2000
MAX_CHAT_TEXT = 4000
MAX_TIMELINE = 20_000

GOOGLE_MEET_CODE = re.compile(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$")
TEAMS_HOSTS = {
    "teams.microsoft.com": None,  # Vexa's default cloud
    "teams.live.com": "teams.live.com",
    "gov.teams.microsoft.us": "gov.teams.microsoft.us",
    "dod.teams.microsoft.us": "dod.teams.microsoft.us",
}
TEAMS_NUMERIC = re.compile(r"^/(?:v2/)?meet/(\d{10,15})/?$")
TEAMS_THREAD = re.compile(r"^/l/meetup-join/(19:meeting_[A-Za-z0-9_\-]{8,200}@thread\.v2)(?:/|$)")
PASSCODE = re.compile(r"^[A-Za-z0-9]{1,50}$")


class BotError(Exception):
    """A failure with a stable code and HTTP status; never carries provider text or URLs."""

    def __init__(self, code: str, status_code: int = 502, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


# ----- meeting URLs ----------------------------------------------------------------------
@dataclass(frozen=True)
class MeetingTarget:
    platform: str
    native_meeting_id: str
    display_url: str  # what is stored and shown: never the passcode
    passcode: str | None = None
    teams_base_host: str | None = None


def parse_meeting_url(url: str) -> MeetingTarget:
    """A Google Meet or Teams join URL -> what Vexa needs to join it (INVALID_MEET_URL if not).

    Google Meet: https://meet.google.com/abc-defg-hij
    Teams:       https://teams.microsoft.com/meet/<10-15 digits>?p=<passcode>
                 (also teams.live.com and the government clouds)
                 https://teams.microsoft.com/l/meetup-join/19:meeting_…@thread.v2/…
    """
    url = (url or "").strip()
    if not url or len(url) > 2000:
        raise BotError("INVALID_MEET_URL", 400)
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise BotError("INVALID_MEET_URL", 400)
    if host == "meet.google.com":
        code = parsed.path.strip("/").split("/")[0].lower()
        if not GOOGLE_MEET_CODE.match(code) or parsed.path.strip("/").count("/"):
            raise BotError("INVALID_MEET_URL", 400)
        return MeetingTarget("google_meet", code, f"https://meet.google.com/{code}")
    if host in TEAMS_HOSTS:
        path = urllib.parse.unquote(parsed.path)
        numeric = TEAMS_NUMERIC.match(path)
        if numeric:
            passcodes = urllib.parse.parse_qs(parsed.query).get("p") or []
            passcode = passcodes[0] if passcodes else None
            if passcode is not None and not PASSCODE.match(passcode):
                raise BotError("INVALID_MEET_URL", 400)
            meeting_id = numeric.group(1)
            return MeetingTarget(
                "teams",
                meeting_id,
                f"https://{host}/meet/{meeting_id}",
                passcode=passcode,
                teams_base_host=TEAMS_HOSTS[host],
            )
        thread = TEAMS_THREAD.match(path)
        if thread:
            thread_id = thread.group(1)
            quoted = urllib.parse.quote(thread_id, safe="")
            return MeetingTarget(
                "teams",
                thread_id,
                f"https://{host}/l/meetup-join/{quoted}/0",
                teams_base_host=TEAMS_HOSTS[host],
            )
    raise BotError("INVALID_MEET_URL", 400)


# ----- Vexa REST client ------------------------------------------------------------------
class VexaClient:
    """The few Vexa endpoints AdVera uses (docs.vexa.ai/api/meetings, v0.12)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key},
            timeout=timeout or self.timeout,
            transport=self.transport,
            follow_redirects=False,  # never carry the key to another host
        )

    async def _request(
        self, method: str, path: str, *, timeout: float | None = None, **kwargs: Any
    ) -> httpx.Response:
        try:
            async with self._client(timeout) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            route = path.split("/")[1]
            logger.warning("vexa %s %s failed: %s", method, route, type(error).__name__)
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502, retryable=True) from None
        if 300 <= response.status_code < 400:
            # A redirect is never followed (it would carry the key elsewhere) nor trusted.
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502, retryable=True)
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise BotError("BOT_PROVIDER_INVALID_RESPONSE", 502, retryable=True) from None

    @staticmethod
    def _bot_path(platform: str, native_meeting_id: str, suffix: str = "") -> str:
        native = urllib.parse.quote(native_meeting_id, safe="")
        return f"/bots/{platform}/{native}{suffix}"

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/health", timeout=5)
        except BotError:
            return False
        return response.status_code == 200

    async def start_bot(
        self,
        target: MeetingTarget,
        bot_name: str,
        language: str | None = None,
        *,
        transcribe: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "platform": target.platform,
            "native_meeting_id": target.native_meeting_id,
            "bot_name": bot_name,
            "recording_enabled": True,
            # The recording is what AdVera transcribes (ADR 0002). Vexa's own transcription is
            # only useful for its speaker names, and needs a speech-to-text service of its own:
            # it is off unless the operator asks for names (ADR 0026).
            "transcribe_enabled": transcribe,
        }
        if language:
            body["language"] = language
        if target.passcode:
            body["passcode"] = target.passcode
        if target.teams_base_host:
            body["teams_base_host"] = target.teams_base_host
        response = await self._request("POST", "/bots", json=body)
        if response.status_code == 409:
            raise BotError("BOT_ALREADY_ACTIVE", 409)
        if response.status_code in (400, 422):
            raise BotError("INVALID_MEET_URL", 400)
        if response.status_code >= 400:
            logger.warning("vexa refused the bot: HTTP %s", response.status_code)
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502)
        data = self._json(response)
        return data if isinstance(data, dict) else {}

    async def stop_bot(self, platform: str, native_meeting_id: str) -> None:
        response = await self._request("DELETE", self._bot_path(platform, native_meeting_id))
        # 404: the bot is already gone; 409: Vexa is already stopping it.
        if response.status_code >= 400 and response.status_code not in (404, 409):
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502, retryable=True)

    async def meeting(self, vexa_meeting_id: str) -> dict[str, Any] | None:
        response = await self._request(
            "GET", f"/meetings/{urllib.parse.quote(vexa_meeting_id, safe='')}"
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502, retryable=True)
        data = self._json(response)
        return data if isinstance(data, dict) else None

    async def transcript(self, bot: MeetingBotSession) -> dict[str, Any]:
        path = (
            f"/transcripts/by-id/{urllib.parse.quote(bot.vexa_meeting_id, safe='')}"
            if bot.vexa_meeting_id
            else f"/transcripts/{bot.platform}/"
            + urllib.parse.quote(bot.native_meeting_id, safe="")
        )
        response = await self._request("GET", path)
        if response.status_code == 404:
            return {}
        if response.status_code >= 400:
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502, retryable=True)
        data = self._json(response)
        return data if isinstance(data, dict) else {}

    async def chat(self, platform: str, native_meeting_id: str) -> list[dict[str, Any]]:
        """The call's chat as Vexa keeps it. Vexa 0.12 answers an empty list (chat is not
        persisted on Meet and Teams yet); a missing route is the same: no chat."""
        response = await self._request("GET", self._bot_path(platform, native_meeting_id, "/chat"))
        if response.status_code >= 400:
            return []
        data = self._json(response)
        if isinstance(data, dict):
            data = data.get("messages") or data.get("chat_messages") or []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def send_chat(self, platform: str, native_meeting_id: str, text: str) -> bool:
        """Write in the call's chat; False when Vexa cannot (not implemented in 0.12)."""
        try:
            response = await self._request(
                "POST", self._bot_path(platform, native_meeting_id, "/chat"), json={"text": text}
            )
        except BotError:
            return False
        return response.status_code < 400

    async def recordings(self, vexa_meeting_id: str | None) -> list[dict[str, Any]]:
        response = await self._request("GET", "/recordings")
        if response.status_code >= 400:
            raise BotError("BOT_PROVIDER_UNAVAILABLE", 502, retryable=True)
        data = self._json(response)
        items = data.get("recordings", []) if isinstance(data, dict) else data
        items = [item for item in items or [] if isinstance(item, dict)]
        if vexa_meeting_id:
            items = [item for item in items if str(item.get("meeting_id")) == vexa_meeting_id]
        return items

    async def audio_path(self, recording: dict[str, Any]) -> str | None:
        """The byte route of a recording's audio. `/master` finalizes it and names the route;
        the media file id is never derived from the recording id (they are unrelated)."""
        recording_id = urllib.parse.quote(str(recording.get("id")), safe="")
        response = await self._request("GET", f"/recordings/{recording_id}/master?type=audio")
        if response.status_code < 400:
            master = self._json(response)
            raw_url = master.get("raw_url") if isinstance(master, dict) else None
            if isinstance(raw_url, str) and raw_url.startswith("/recordings/"):
                return raw_url
        media = next(
            (
                item
                for item in recording.get("media_files") or []
                if isinstance(item, dict) and item.get("type", "audio") == "audio"
            ),
            None,
        )
        if media is None or media.get("id") is None:
            return None
        media_id = urllib.parse.quote(str(media["id"]), safe="")
        return f"/recordings/{recording_id}/media/{media_id}/raw?type=audio"

    async def download(self, path: str, destination: Path, max_bytes: int) -> int:
        written = 0
        try:
            async with self._client(timeout=max(self.timeout, 600)) as client:
                async with client.stream("GET", path) as response:
                    if response.status_code >= 400:
                        raise BotError("RECORDING_DOWNLOAD_FAILED", 502, retryable=True)
                    with destination.open("wb") as target:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            written += len(chunk)
                            if written > max_bytes:
                                raise BotError("RECORDING_TOO_LARGE", 413)
                            target.write(chunk)
        except httpx.HTTPError:
            raise BotError("RECORDING_DOWNLOAD_FAILED", 502, retryable=True) from None
        if written == 0:
            raise BotError("RECORDING_EMPTY", 502, retryable=True)
        return written


def build_client(runtime: RuntimeSettings, settings: Settings) -> VexaClient:
    return VexaClient(
        runtime.vexa_base_url, runtime.vexa_api_key, timeout=settings.vexa_timeout_seconds
    )


@dataclass
class BotContext:
    """What the bot needs, in the API and in the transcription worker alike."""

    sessionmaker: async_sessionmaker[AsyncSession]
    storage: MeetingStorage
    settings: Settings
    queue: JobQueue
    client_factory: Callable[[RuntimeSettings, Settings], VexaClient] = build_client

    def runtime(self) -> RuntimeSettings:
        return runtime_settings.load(self.settings)

    def client(self) -> VexaClient:
        runtime = self.runtime()
        if not runtime.vexa_configured:
            raise BotError("BOT_PROVIDER_NOT_CONFIGURED", 503)
        return self.client_factory(runtime, self.settings)


def context(request: Request) -> BotContext:
    return request.app.state.meeting_bot


Context = Annotated[BotContext, Depends(context)]


# ----- pure helpers ----------------------------------------------------------------------
def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) < 1e12 else None  # no NaN / inf


def speaker_timeline(
    segments: list[dict[str, Any]], started_at: datetime | None, bot_name: str
) -> list[list[Any]]:
    """[[start, end, name], ...] in seconds from the call start: who Vexa heard, and when.

    Chat lines, unnamed segments, drafts and the bot itself are left out. Wall-clock times are
    preferred when both they and the call start are known; otherwise Vexa's relative times.
    """
    bot_key = canonical_key(bot_name)
    timeline: list[list[Any]] = []
    for segment in segments:
        if not isinstance(segment, dict) or segment.get("source") == "chat":
            continue
        if segment.get("completed") is False:
            continue
        name = display_name(str(segment.get("speaker") or ""))[:200]
        if not name or not canonical_key(name) or canonical_key(name) == bot_key:
            continue
        start, end = _number(segment.get("start")), _number(segment.get("end"))
        absolute_start = parse_time(segment.get("absolute_start_time"))
        absolute_end = parse_time(segment.get("absolute_end_time"))
        if started_at and absolute_start and absolute_end:
            start = (absolute_start - started_at).total_seconds()
            end = (absolute_end - started_at).total_seconds()
        if start is None or end is None or end <= start or end < 0:
            continue
        timeline.append([round(max(0.0, start), 3), round(end, 3), name])
        if len(timeline) >= MAX_TIMELINE:
            break
    return sorted(timeline, key=lambda item: item[0])


def match_speakers(
    segments: list[tuple[str, float, float]], timeline: list[list[Any]]
) -> dict[str, str]:
    """Diarized label -> the provider's name that overlaps it the longest.

    `segments` are (label, start, end) of AdVera's transcript; `timeline` is [start, end,
    name]. A label that never overlaps a named interval stays unnamed (overlapping voices
    leave a few segments like that, ADR 0026). Two labels may get the same name: diarization
    can split one voice.
    """
    overlap: dict[str, dict[str, float]] = {}
    ordered = sorted((float(s), float(e), str(n)) for s, e, n in timeline)
    starts = [item[0] for item in ordered]
    for label, start, end in segments:
        if not label or end <= start:
            continue
        # Intervals that start before this segment ends; scan back while they can overlap.
        index = bisect.bisect_left(starts, end)
        for interval_start, interval_end, name in ordered[:index][::-1]:
            if interval_end <= start and start - interval_start > 3600:
                break
            shared = min(end, interval_end) - max(start, interval_start)
            if shared > 0:
                key = canonical_key(name)
                bucket = overlap.setdefault(label, {})
                bucket[key] = bucket.get(key, 0.0) + shared
    names = {canonical_key(n): n for _s, _e, n in ordered}
    result: dict[str, str] = {}
    for label, scores in overlap.items():
        best = max(scores.items(), key=lambda item: (item[1], item[0]))
        result[label] = names[best[0]]
    return result


def chat_messages(
    sources: list[list[dict[str, Any]]], started_at: datetime | None, bot_name: str
) -> list[dict[str, Any]]:
    """Normalized chat from every place Vexa may keep it, without repeats or the bot's own lines."""
    bot_key = canonical_key(bot_name)
    seen: set[tuple[str, str, str]] = set()
    messages: list[dict[str, Any]] = []
    for items in sources:
        for item in items:
            if not isinstance(item, dict):
                continue
            sender = display_name(
                str(item.get("sender") or item.get("speaker") or item.get("author") or "")
            )[:200]
            text = str(item.get("text") or item.get("message") or item.get("m") or "").strip()
            if not text or (sender and canonical_key(sender) == bot_key):
                continue
            sent_at = parse_time(
                item.get("sent_at")
                or item.get("timestamp")
                or item.get("absolute_start_time")
                or item.get("ts")
            )
            offset = (sent_at - started_at).total_seconds() if sent_at and started_at else None
            if offset is None and item.get("source") == "chat":
                offset = _number(item.get("start"))
            key = (canonical_key(sender), text, sent_at.isoformat() if sent_at else "")
            if key in seen:
                continue
            seen.add(key)
            messages.append(
                {
                    "sender": sender or "?",
                    "text": text[:MAX_CHAT_TEXT],
                    "sent_at": sent_at,
                    "offset_s": round(max(0.0, offset), 3) if offset is not None else None,
                }
            )
    messages.sort(key=lambda m: (m["offset_s"] is None, m["offset_s"] or 0.0))
    return messages[:MAX_CHAT_MESSAGES]


def verify_signature(
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    authorization: str | None,
    *,
    now: float | None = None,
    tolerance: int = 300,
) -> bool:
    """Vexa's webhook.v1 scheme: `sha256=HMAC(secret, "<timestamp>." + body)` within the replay
    window. The legacy `Authorization: Bearer <secret>` is accepted too (the webhook only makes
    AdVera ask Vexa, so a replay cannot change any state)."""
    if not secret:
        return False
    if signature and timestamp:
        try:
            sent = int(timestamp)
        except ValueError:
            return False
        if abs((now if now is not None else time.time()) - sent) > tolerance:
            return False
        expected = hmac.new(
            secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature.strip(), f"sha256={expected}")
    if authorization:
        return hmac.compare_digest(authorization.strip(), f"Bearer {secret}")
    return False


# ----- lifecycle -------------------------------------------------------------------------
async def live_session(session: AsyncSession, meeting_id: str) -> MeetingBotSession | None:
    return (
        await session.execute(
            select(MeetingBotSession)
            .where(
                MeetingBotSession.meeting_id == meeting_id,
                MeetingBotSession.status.not_in(BOT_TERMINAL_STATUSES),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_session(session: AsyncSession, meeting_id: str) -> MeetingBotSession | None:
    return (
        await session.execute(
            select(MeetingBotSession)
            .where(MeetingBotSession.meeting_id == meeting_id)
            .order_by(MeetingBotSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _release_meeting(db: AsyncSession, storage: MeetingStorage, meeting_id: str) -> None:
    """A bot that ended without audio gives the meeting back: another source may record it."""
    meeting = await db.get(Meeting, meeting_id)
    if meeting is not None and meeting.status == "recording":
        if not storage.non_empty_tracks(meeting_id):
            meeting.status = "scheduled"
            meeting.started_at = None
            meeting.ended_at = None


async def _fail(db: AsyncSession, ctx: BotContext, bot: MeetingBotSession, code: str) -> None:
    bot.status = "failed"
    bot.error = code[:50]
    bot.lease_token = None
    bot.completed_at = utcnow()
    await _release_meeting(db, ctx.storage, bot.meeting_id)
    logger.warning("meeting bot %s failed: %s", bot.id, code)


async def refresh(db: AsyncSession, ctx: BotContext, bot: MeetingBotSession) -> None:
    """Ask Vexa where the bot is and follow it. The caller commits."""
    if bot.status not in PROVIDER_LIVE:
        return
    client = ctx.client()
    info: dict[str, Any] | None = None
    if bot.vexa_meeting_id:
        info = await client.meeting(bot.vexa_meeting_id)
    if info is None:
        info = await client.transcript(bot)
    bot.checked_at = utcnow()
    status = str((info or {}).get("status") or "")
    if not status:
        return  # Vexa does not know it yet: the next check decides
    bot.provider_status = status[:30]
    if info and info.get("id") is not None and not bot.vexa_meeting_id:
        bot.vexa_meeting_id = str(info["id"])[:50]
    if status in PROVIDER_LIVE:
        if bot.status == "stopping" and status != "stopping":
            return  # asked to leave: never shown as back in the call
        bot.status = status
        if status == "active" and bot.joined_at is None:
            bot.joined_at = utcnow()
        if status == "active" and bot.consent_notice == "pending":
            text = CONSENT_MESSAGE.get(ctx.runtime().llm_output_language, CONSENT_MESSAGE["en"])
            sent = await client.send_chat(
                bot.platform, bot.native_meeting_id, text.format(name=bot.bot_name)
            )
            bot.consent_notice = "sent" if sent else "unsupported"
    elif status == "completed":
        bot.status = "ended"  # waiting for ingestion
        bot.left_at = bot.left_at or utcnow()
    elif status == "failed":
        bot.left_at = bot.left_at or utcnow()
        await _fail(db, ctx, bot, "BOT_FAILED")


async def ingest(ctx: BotContext, bot_id: str) -> bool:
    """Download the call's recording, keep its chat and queue the definitive transcription.

    Runs under a lease: only the process that claims `ended -> ingesting` works on it. A
    recording Vexa is still finalizing puts the session back to `ended` for the next check.
    """
    token = str(uuid.uuid4())
    async with ctx.sessionmaker() as db:
        if not await leases.claim(
            db,
            MeetingBotSession,
            bot_id,
            token,
            running_status="ingesting",
            queued_status="ended",
        ):
            return False
    try:
        job = await leases.with_heartbeat(
            _ingest(ctx, bot_id, token),
            _beat(ctx, bot_id, token),
            max(5.0, ctx.settings.vexa_ingest_lease_seconds / 4),
        )
    except BotError as error:
        async with ctx.sessionmaker() as db:
            bot = await db.get(MeetingBotSession, bot_id)
            if bot is None or bot.lease_token != token:
                return False
            if error.retryable and bot.attempts < bot.max_attempts:
                bot.status = "ended"
                bot.lease_token = None
                bot.error = error.code[:50]
            else:
                await _fail(db, ctx, bot, error.code)
            await db.commit()
        return False
    except leases.LeaseLost:
        return False
    if job is not None and job.status == "queued":
        await publish(ctx.queue, job.id)
    return True


def _beat(ctx: BotContext, bot_id: str, token: str):
    async def beat() -> None:
        async with ctx.sessionmaker() as db:
            if not await leases.fenced_update(
                db, MeetingBotSession, bot_id, token, running_statuses=("ingesting",)
            ):
                raise leases.LeaseLost
            await db.commit()

    return beat


async def _ingest(ctx: BotContext, bot_id: str, token: str):
    client = ctx.client()
    async with ctx.sessionmaker() as db:
        bot = await db.get(MeetingBotSession, bot_id)
        assert bot is not None
        snapshot = (
            bot.meeting_id,
            bot.platform,
            bot.native_meeting_id,
            bot.vexa_meeting_id,
            bot.bot_name,
        )
        transcript = await client.transcript(bot)
    meeting_id, platform, native, vexa_id, bot_name = snapshot
    started_at = parse_time(transcript.get("start_time"))
    ended_at = parse_time(transcript.get("end_time"))
    segments = [s for s in transcript.get("segments") or [] if isinstance(s, dict)]

    # 1. Audio, unless an earlier attempt already converted it (the lease was lost after).
    if "system" not in ctx.storage.non_empty_tracks(meeting_id):
        if ctx.storage.non_empty_tracks(meeting_id):
            raise BotError("MEETING_ALREADY_RECORDED", 409)
        await _download_audio(ctx, client, transcript, vexa_id, meeting_id)

    # 2. Chat, from wherever this Vexa version keeps it.
    detail = (await client.meeting(vexa_id) if vexa_id else None) or {}
    data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
    messages = chat_messages(
        [
            [s for s in segments if s.get("source") == "chat"],
            await client.chat(platform, native),
            [m for m in (data.get("chat_messages") or []) if isinstance(m, dict)],
        ],
        started_at,
        bot_name,
    )
    timeline = speaker_timeline(segments, started_at, bot_name)

    # 3. Meeting times and the definitive transcription, in one fenced write.
    async with ctx.sessionmaker() as db:
        if not await leases.fenced_update(
            db,
            MeetingBotSession,
            bot_id,
            token,
            running_statuses=("ingesting",),
            speaker_timeline=timeline,
        ):
            raise leases.LeaseLost
        await db.execute(
            delete(MeetingChatMessage).where(MeetingChatMessage.meeting_id == meeting_id)
        )
        for position, message in enumerate(messages, start=1):
            db.add(MeetingChatMessage(meeting_id=meeting_id, position=position, **message))
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            raise BotError("MEETING_NOT_FOUND", 404)
        if started_at:
            meeting.started_at = started_at
        meeting.ended_at = ended_at or utcnow()
        meeting.duration = ctx.storage.track_duration(meeting_id, "system")
        job = await queue_meeting_transcription(db, ctx.storage, ctx.settings, meeting)
    async with ctx.sessionmaker() as db:
        if not await leases.fenced_update(
            db,
            MeetingBotSession,
            bot_id,
            token,
            running_statuses=("ingesting",),
            status="completed",
            lease_token=None,
            error=None,
            completed_at=utcnow(),
        ):
            raise leases.LeaseLost
        await db.commit()
    logger.info(
        "meeting %s bot recording ingested: %s chat messages, %s named intervals; job %s",
        meeting_id,
        len(messages),
        len(timeline),
        job.id,
    )
    return job


async def _download_audio(
    ctx: BotContext,
    client: VexaClient,
    transcript: dict[str, Any],
    vexa_id: str | None,
    meeting_id: str,
) -> None:
    recordings = [r for r in transcript.get("recordings") or [] if isinstance(r, dict)]
    if not recordings:
        recordings = await client.recordings(vexa_id)
    ready = [r for r in recordings if r.get("status", "completed") == "completed"]
    if not ready:
        if recordings:
            raise BotError("RECORDING_NOT_READY", 202, retryable=True)
        raise BotError("NO_RECORDING", 422, retryable=True)
    path = await client.audio_path(ready[-1])
    if path is None:
        raise BotError("NO_RECORDING", 422)
    directory = ctx.storage.meeting_dir(meeting_id)
    directory.mkdir(parents=True, exist_ok=True)
    for previous in directory.glob(f"{RECORDING_PREFIX}*"):
        previous.unlink()  # leftovers of an interrupted download
    destination = directory / f"{RECORDING_PREFIX}{uuid.uuid4().hex}.media"
    try:
        await client.download(path, destination, ctx.settings.vexa_recording_max_bytes)
        await convert_to_system_track(
            destination,
            ctx.storage,
            meeting_id,
            ctx.settings.ffmpeg_binary,
            ctx.settings.media_import_timeout_seconds,
            ctx.settings.media_import_max_seconds,
        )
    except MediaImportError as error:
        raise BotError(error.code, error.status_code) from None
    finally:
        # Like an import, only the extracted audio is kept (ADR 0016).
        destination.unlink(missing_ok=True)


# Sessions being checked in this process, so a webhook and the poller do not overlap.
_checking: set[str] = set()


async def check(ctx: BotContext, bot_id: str) -> None:
    """Refresh one session from Vexa and ingest it once the bot has left."""
    if bot_id in _checking:
        return
    _checking.add(bot_id)
    try:
        async with ctx.sessionmaker() as db:
            bot = await db.get(MeetingBotSession, bot_id)
            if bot is None:
                return
            try:
                await refresh(db, ctx, bot)
            except BotError as error:
                logger.info("meeting bot %s check deferred: %s", bot_id, error.code)
            await db.commit()
            ended = bot.status == "ended"
        if ended:
            await ingest(ctx, bot_id)
    finally:
        _checking.discard(bot_id)


async def poll(ctx: BotContext) -> None:
    """Fallback for lost webhooks: follow every live session, recover stale ingestions."""
    if not ctx.runtime().vexa_configured:
        return
    cutoff = utcnow() - timedelta(seconds=ctx.settings.vexa_ingest_lease_seconds)
    async with ctx.sessionmaker() as db:
        await db.execute(
            update(MeetingBotSession)
            .where(MeetingBotSession.status == "ingesting", MeetingBotSession.updated_at < cutoff)
            .values(status="ended", lease_token=None, updated_at=utcnow())
        )
        await db.commit()
        ids = list(
            (
                await db.execute(
                    select(MeetingBotSession.id).where(
                        MeetingBotSession.status.in_((*PROVIDER_LIVE, "ended"))
                    )
                )
            ).scalars()
        )
    for bot_id in ids:
        try:
            await check(ctx, bot_id)
        except Exception as error:  # one broken session must not stop the others
            logger.warning("meeting bot %s poll failed: %s", bot_id, type(error).__name__)


async def name_speakers(
    db: AsyncSession, meeting_id: str, document: TranscriptDocument
) -> dict[tuple[str, str], str]:
    """Name the diarized speakers of the bot's track after who Vexa heard (ADR 0021).

    Only speakers with no name yet are named, so a name the user gave is never replaced. The
    caller commits.
    """
    from app.people_api import assign_names

    bot = (
        await db.execute(
            select(MeetingBotSession)
            .where(
                MeetingBotSession.meeting_id == meeting_id,
                MeetingBotSession.status == "completed",
            )
            .order_by(MeetingBotSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if bot is None or not bot.speaker_timeline:
        return {}
    segments = [
        (segment.speaker or "", segment.start, segment.end)
        for segment in document.segments
        if segment.track == "system" and segment.speaker
    ]
    names = {
        ("system", label): name
        for label, name in match_speakers(segments, bot.speaker_timeline).items()
    }
    if names:
        await assign_names(db, meeting_id, names, replace=False)
    return names


# ----- REST API --------------------------------------------------------------------------
def _response(bot: MeetingBotSession) -> BotSessionResponse:
    response = BotSessionResponse.model_validate(bot)
    response.active = bot.status not in BOT_TERMINAL_STATUSES
    return response


# Meetings with a bot being sent in this process: the second request is refused at once.
_starting: set[str] = set()


@router.get("/api/meeting-bot/capabilities", response_model=BotCapabilitiesResponse)
async def capabilities(ctx: Context) -> BotCapabilitiesResponse:
    runtime = ctx.runtime()
    if not runtime.vexa_configured:
        return BotCapabilitiesResponse(configured=False, available=False)
    available = await ctx.client_factory(runtime, ctx.settings).health()
    return BotCapabilitiesResponse(
        configured=True,
        available=available,
        bot_name=runtime.vexa_bot_name,
        platforms=list(PLATFORMS),
    )


@router.post("/api/meetings/{meeting_id}/bot", response_model=BotSessionResponse, status_code=201)
async def start_bot(
    meeting_id: str, body: BotStartRequest, request: Request, db: Session, ctx: Context
) -> BotSessionResponse:
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    if meeting_id in _starting:
        raise HTTPException(status_code=409, detail="BOT_ALREADY_ACTIVE")
    _starting.add(meeting_id)
    try:
        try:
            target = parse_meeting_url(body.meet_url)
            client = ctx.client()
        except BotError as error:
            raise HTTPException(status_code=error.status_code, detail=error.code) from None
        if await live_session(db, meeting_id):
            raise HTTPException(status_code=409, detail="BOT_ALREADY_ACTIVE")
        sessions = request.app.state.audio_sessions
        if ctx.storage.non_empty_tracks(meeting_id) or sessions.has_recorded_audio(meeting_id):
            # Audio already stored is never replaced by another source.
            raise HTTPException(status_code=409, detail="MEETING_ALREADY_RECORDED")
        if (
            meeting.status in ("recording", "processing")
            or meeting_id in imports_in_progress
            or sessions.active(meeting_id) is not None
            or await active_job(db, meeting_id)
        ):
            raise HTTPException(status_code=409, detail="MEETING_BUSY")
        runtime = ctx.runtime()
        await db.rollback()  # no transaction open while Vexa is called
        try:
            created = await client.start_bot(
                target, runtime.vexa_bot_name, body.language, transcribe=runtime.vexa_speaker_names
            )
        except BotError as error:
            raise HTTPException(status_code=error.status_code, detail=error.code) from None
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
        status = str(created.get("status") or "requested")
        bot = MeetingBotSession(
            meeting_id=meeting_id,
            provider="vexa",
            platform=target.platform,
            native_meeting_id=target.native_meeting_id,
            vexa_meeting_id=str(created["id"])[:50] if created.get("id") is not None else None,
            meet_url=target.display_url,
            bot_name=runtime.vexa_bot_name,
            status=status if status in PROVIDER_LIVE else "requested",
            provider_status=status[:30],
            consent_notice="pending",
            speaker_timeline=[],
            max_attempts=20,
            started_at=utcnow(),
            checked_at=utcnow(),
        )
        db.add(bot)
        meeting.status = "recording"
        meeting.started_at = utcnow()
        meeting.ended_at = None
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            with contextlib.suppress(BotError):
                await client.stop_bot(target.platform, target.native_meeting_id)
            raise HTTPException(status_code=409, detail="BOT_ALREADY_ACTIVE") from None
    finally:
        _starting.discard(meeting_id)
    logger.info("meeting %s bot %s sent to %s", meeting_id, bot.id, target.platform)
    return _response(bot)


@router.get("/api/meetings/{meeting_id}/bot", response_model=BotSessionResponse)
async def get_bot(
    meeting_id: str, db: Session, ctx: Context, background: BackgroundTasks
) -> BotSessionResponse:
    bot = await latest_session(db, meeting_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="BOT_NOT_FOUND")
    stale = bot.checked_at is None or utcnow() - _aware(bot.checked_at) > timedelta(
        seconds=ctx.settings.vexa_refresh_seconds
    )
    if bot.status in PROVIDER_LIVE and stale:
        try:
            await refresh(db, ctx, bot)
            await db.commit()
        except BotError as error:
            await db.rollback()
            logger.info("meeting bot %s refresh deferred: %s", bot.id, error.code)
            bot = await latest_session(db, meeting_id)
            assert bot is not None
    if bot.status == "ended":
        background.add_task(check, ctx, bot.id)
    return _response(bot)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@router.delete("/api/meetings/{meeting_id}/bot", response_model=BotSessionResponse)
async def stop_bot(meeting_id: str, db: Session, ctx: Context) -> BotSessionResponse:
    bot = await live_session(db, meeting_id)
    if bot is None or bot.status not in PROVIDER_LIVE:
        raise HTTPException(status_code=404, detail="BOT_NOT_ACTIVE")
    try:
        await ctx.client().stop_bot(bot.platform, bot.native_meeting_id)
    except BotError as error:
        raise HTTPException(status_code=error.status_code, detail=error.code) from None
    bot.status = "stopping"
    await db.commit()
    logger.info("meeting %s bot %s asked to leave", meeting_id, bot.id)
    return _response(bot)


@router.get("/api/meetings/{meeting_id}/chat", response_model=list[ChatMessageResponse])
async def get_chat(meeting_id: str, db: Session) -> list[ChatMessageResponse]:
    if await db.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="MEETING_NOT_FOUND")
    rows = (
        await db.execute(
            select(MeetingChatMessage)
            .where(MeetingChatMessage.meeting_id == meeting_id)
            .order_by(MeetingChatMessage.position)
        )
    ).scalars()
    return [
        ChatMessageResponse(
            id=chat_block_id(row.position),
            sender=row.sender,
            text=row.text,
            sent_at=row.sent_at,
            offset_s=row.offset_s,
        )
        for row in rows
    ]


def chat_block_id(position: int) -> str:
    return f"chat-{position:03d}"


@router.post("/api/integrations/vexa/webhook", status_code=202)
async def webhook(request: Request, ctx: Context, background: BackgroundTasks) -> Response:
    secret = ctx.runtime().vexa_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="WEBHOOK_NOT_CONFIGURED")
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="PAYLOAD_TOO_LARGE")
    if not verify_signature(
        secret,
        body,
        request.headers.get("x-webhook-signature"),
        request.headers.get("x-webhook-timestamp"),
        request.headers.get("authorization"),
        tolerance=ctx.settings.vexa_webhook_tolerance_seconds,
    ):
        raise HTTPException(status_code=401, detail="INVALID_SIGNATURE")
    try:
        envelope = json.loads(body)
        meeting = (envelope.get("data") or {}).get("meeting") or {}
        vexa_id = str(meeting["id"]) if meeting.get("id") is not None else None
        platform = str(meeting.get("platform") or "")
        native = str(meeting.get("native_meeting_id") or "")
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=422, detail="INVALID_PAYLOAD") from None
    async with ctx.sessionmaker() as db:
        query = select(MeetingBotSession.id).where(
            MeetingBotSession.status.not_in(BOT_TERMINAL_STATUSES)
        )
        if vexa_id:
            match = (
                (await db.execute(query.where(MeetingBotSession.vexa_meeting_id == vexa_id)))
                .scalars()
                .first()
            )
        else:
            match = None
        if match is None and platform and native:
            match = (
                (
                    await db.execute(
                        query.where(
                            MeetingBotSession.platform == platform,
                            MeetingBotSession.native_meeting_id == native,
                        )
                    )
                )
                .scalars()
                .first()
            )
    if match is None:
        return JSONResponse({"status": "ignored"}, status_code=202)
    background.add_task(check, ctx, match)
    return JSONResponse({"status": "accepted"}, status_code=202)


def bot_owns(session: MeetingBotSession | None) -> bool:
    return session is not None and session.status in PROVIDER_LIVE
