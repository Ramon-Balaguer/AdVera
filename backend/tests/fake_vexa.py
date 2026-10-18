"""A stateful stand-in for a self-hosted Vexa (ADR 0026), served through httpx.MockTransport.

It answers the endpoints AdVera calls with the shapes in tests/fixtures/vexa, records every
request, and lets a test move the bot through its lifecycle (`set_status`). The recording it
serves is a synthetic WAV, so the real ffmpeg conversion runs on it.
"""

import copy
import json
from pathlib import Path
from typing import Any

import httpx

from app.meeting_bot import VexaClient

FIXTURES = Path(__file__).parent / "fixtures" / "vexa"
API_KEY = "test-vexa-key"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeVexa:
    def __init__(self, recording: bytes = b"", *, chat_route: bool = False) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, Any]] = []
        self.status = "requested"
        self.platform = "google_meet"
        self.native = "abc-defg-hij"
        self.recording = recording
        self.recording_status = "completed"
        self.chat_route = chat_route  # Vexa 0.12 has no chat write route: 404 by default
        self.healthy = True
        self.fail_start: int | None = None
        self.transcript = fixture("transcript_completed.json")

    # -- test controls -------------------------------------------------------------------
    def set_status(self, status: str) -> None:
        self.status = status

    def client(self) -> VexaClient:
        return VexaClient("http://vexa:8056", API_KEY, transport=httpx.MockTransport(self.handle))

    def factory(self, _runtime=None, _settings=None) -> VexaClient:
        return self.client()

    def paths(self, method: str | None = None) -> list[str]:
        return [request.url.path for request in self.requests if method in (None, request.method)]

    # -- the fake API --------------------------------------------------------------------
    def _meeting(self) -> dict[str, Any]:
        name = "meeting_completed.json" if self.status == "completed" else "meeting_active.json"
        meeting = fixture(name)
        meeting.update(status=self.status, platform=self.platform, native_meeting_id=self.native)
        return meeting

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("x-api-key") != API_KEY:
            return httpx.Response(401, json={"detail": "invalid api key"})
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        if body:
            self.bodies.append(body)
        if path == "/health":
            return httpx.Response(200 if self.healthy else 503, json={"status": "ok"})
        if method == "POST" and path == "/bots":
            if self.fail_start:
                return httpx.Response(self.fail_start, json={"detail": "refused"})
            self.platform = body["platform"]
            self.native = body["native_meeting_id"]
            created = fixture("bot_created.json")
            created.update(platform=self.platform, native_meeting_id=self.native)
            return httpx.Response(201, json=created)
        if method == "DELETE" and path.startswith("/bots/"):
            self.status = "stopping"
            return httpx.Response(202, json={"status": "stopping", "meeting_id": 11367})
        if path.startswith("/bots/") and path.endswith("/chat"):
            if method == "POST":
                return httpx.Response(202 if self.chat_route else 404, json={})
            return httpx.Response(200, json={"messages": []})
        if method == "GET" and path == "/meetings/11367":
            return httpx.Response(200, json=self._meeting())
        if method == "GET" and path.startswith("/transcripts/"):
            transcript = copy.deepcopy(self.transcript)
            transcript.update(status=self.status, platform=self.platform)
            transcript["native_meeting_id"] = self.native
            for recording in transcript.get("recordings") or []:
                recording["status"] = self.recording_status
            return httpx.Response(200, json=transcript)
        if method == "GET" and path == "/recordings":
            return httpx.Response(200, json={"recordings": self.transcript["recordings"]})
        if method == "GET" and path == "/recordings/481159273044/master":
            return httpx.Response(200, json=fixture("recording_master.json"))
        if method == "GET" and path == "/recordings/481159273044/media/730928415562/raw":
            return httpx.Response(
                200, content=self.recording, headers={"content-type": "audio/wav"}
            )
        return httpx.Response(404, json={"detail": "not found"})
