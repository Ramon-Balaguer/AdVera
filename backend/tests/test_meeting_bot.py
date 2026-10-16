"""Meeting bot (ADR 0026): URL validation, webhook signatures, the Vexa client and the
speaker-to-name matching. No network: Vexa is the fake in tests/fake_vexa.py."""

import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.meeting_bot import (
    BotError,
    VexaClient,
    chat_messages,
    match_speakers,
    parse_meeting_url,
    speaker_timeline,
    verify_signature,
)
from tests.fake_vexa import FakeVexa, fixture

START = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)


# ----- meeting URLs ----------------------------------------------------------------------
def test_a_google_meet_url_gives_its_meeting_code():
    target = parse_meeting_url(" https://meet.google.com/abc-defg-hij?authuser=1 ")
    assert (target.platform, target.native_meeting_id) == ("google_meet", "abc-defg-hij")
    assert target.display_url == "https://meet.google.com/abc-defg-hij"
    assert target.passcode is None


def test_a_meet_code_is_case_insensitive():
    assert parse_meeting_url("https://meet.google.com/ABC-DEFG-HIJ").native_meeting_id == (
        "abc-defg-hij"
    )


def test_a_teams_numeric_link_keeps_the_passcode_out_of_the_stored_url():
    target = parse_meeting_url("https://teams.microsoft.com/meet/3812345678901?p=Ab12Cd")
    assert (target.platform, target.native_meeting_id) == ("teams", "3812345678901")
    assert target.passcode == "Ab12Cd"
    assert target.display_url == "https://teams.microsoft.com/meet/3812345678901"
    assert "Ab12Cd" not in target.display_url
    assert target.teams_base_host is None


def test_a_personal_teams_link_names_its_cloud():
    target = parse_meeting_url("https://teams.live.com/meet/9387654321098?p=XyZ9")
    assert target.teams_base_host == "teams.live.com"
    assert target.passcode == "XyZ9"


def test_a_teams_meetup_join_link_gives_its_thread_id():
    url = (
        "https://teams.microsoft.com/l/meetup-join/"
        "19%3ameeting_NjA1ZTI4ZDEtYjQ0Ni00%40thread.v2/0?context=%7b%22Tid%22%3a%22x%22%7d"
    )
    target = parse_meeting_url(url)
    assert target.platform == "teams"
    assert target.native_meeting_id == "19:meeting_NjA1ZTI4ZDEtYjQ0Ni00@thread.v2"
    assert "context" not in target.display_url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "meet.google.com/abc-defg-hij",  # no scheme
        "http://meet.google.com/abc-defg-hij",  # not https
        "https://meet.google.com/abc-defg",  # not a meeting code
        "https://meet.google.com/abc-defg-hij/extra",
        "https://meet.google.com.evil.example/abc-defg-hij",
        "https://user:pass@meet.google.com/abc-defg-hij",
        "https://meet.google.com:8443/abc-defg-hij",
        "https://zoom.us/j/123456789",  # not supported here
        "https://teams.microsoft.com/meet/123",  # too short
        "https://teams.microsoft.com/meet/3812345678901?p=bad%20code",
        "https://teams.evil.example/meet/3812345678901",
        "https://teams.microsoft.com/l/meetup-join/19:other@thread.v2/0",
        "https://meet.google.com/" + "a" * 3000,
    ],
)
def test_anything_else_is_an_invalid_meeting_url(url):
    with pytest.raises(BotError) as error:
        parse_meeting_url(url)
    assert (error.value.code, error.value.status_code) == ("INVALID_MEET_URL", 400)


# ----- webhook signatures ----------------------------------------------------------------
def _sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return "sha256=" + digest.hexdigest()


def test_a_signed_webhook_inside_the_window_is_accepted():
    body = json.dumps(fixture("webhook_meeting_completed.json")).encode()
    signature = _sign("s3cret", "1760608805", body)
    assert verify_signature("s3cret", body, signature, "1760608805", None, now=1760608810)


def test_a_wrong_secret_a_changed_body_or_an_old_timestamp_is_refused():
    body = b'{"event_type":"meeting.completed"}'
    good = _sign("s3cret", "1000", body)
    assert not verify_signature("other", body, good, "1000", None, now=1000)
    assert not verify_signature("s3cret", body + b" ", good, "1000", None, now=1000)
    assert not verify_signature("s3cret", body, good, "1000", None, now=1000 + 301)
    assert not verify_signature("s3cret", body, good, "not-a-number", None, now=1000)
    assert not verify_signature("s3cret", body, None, None, None)
    assert not verify_signature("", body, good, "1000", "Bearer ", now=1000)


def test_the_legacy_bearer_secret_is_accepted():
    assert verify_signature("s3cret", b"{}", None, None, "Bearer s3cret")
    assert not verify_signature("s3cret", b"{}", None, None, "Bearer wrong")


# ----- speakers and chat -----------------------------------------------------------------
def test_the_timeline_keeps_named_final_speech_only():
    transcript = fixture("transcript_completed.json")
    timeline = speaker_timeline(transcript["segments"], START, "AdVera Notekeeper")
    assert timeline == [[0.0, 1.0, "Ramón Prueba"], [2.0, 3.5, "Marta Prueba"]]


def test_without_wall_clock_times_the_relative_times_are_used():
    segments = [{"speaker": "Ana", "start": 5, "end": 7}, {"speaker": "", "start": 1, "end": 2}]
    assert speaker_timeline(segments, None, "Bot") == [[5.0, 7.0, "Ana"]]


def test_each_label_gets_the_name_it_overlaps_most():
    segments = [
        ("SPEAKER_00", 0.0, 1.0),
        ("SPEAKER_00", 1.0, 1.4),
        ("SPEAKER_01", 2.1, 3.4),
        ("SPEAKER_02", 10.0, 11.0),  # nobody named spoke then: stays unnamed
    ]
    timeline = [[0.0, 1.2, "Ramón Prueba"], [1.2, 1.4, "Marta Prueba"], [2.0, 3.5, "Marta Prueba"]]
    assert match_speakers(segments, timeline) == {
        "SPEAKER_00": "Ramón Prueba",
        "SPEAKER_01": "Marta Prueba",
    }


def test_two_labels_may_be_one_person():
    timeline = [[0.0, 10.0, "Ramón Prueba"]]
    names = match_speakers([("SPEAKER_00", 0, 4), ("SPEAKER_03", 5, 9)], timeline)
    assert names == {"SPEAKER_00": "Ramón Prueba", "SPEAKER_03": "Ramón Prueba"}


def test_chat_is_merged_without_repeats_or_the_bot_and_placed_in_the_call():
    transcript = fixture("transcript_completed.json")
    meeting = fixture("meeting_completed.json")
    messages = chat_messages(
        [
            [s for s in transcript["segments"] if s.get("source") == "chat"],
            [{"sender": "AdVera Notekeeper", "text": "Esta reunión se graba"}],
            meeting["data"]["chat_messages"],
            meeting["data"]["chat_messages"],  # the same message from two places
        ],
        START,
        "AdVera Notekeeper",
    )
    assert [(m["sender"], m["text"], m["offset_s"]) for m in messages] == [
        ("Marta Prueba", "Os paso el enlace del presupuesto", 1.5),
        ("Ramón Prueba", "Gràcies!", 3.8),
    ]


# ----- the Vexa client -------------------------------------------------------------------
async def test_a_bot_is_sent_recording_without_vexa_transcription_by_default():
    vexa = FakeVexa()
    target = parse_meeting_url("https://meet.google.com/abc-defg-hij")
    created = await vexa.client().start_bot(target, "AdVera Notekeeper")
    assert created["id"] == 11367
    assert vexa.bodies[-1] == {
        "platform": "google_meet",
        "native_meeting_id": "abc-defg-hij",
        "bot_name": "AdVera Notekeeper",
        "recording_enabled": True,
        "transcribe_enabled": False,
    }


async def test_the_bot_leaves_a_call_where_nobody_speaks_after_the_configured_wait():
    vexa = FakeVexa()
    target = parse_meeting_url("https://meet.google.com/abc-defg-hij")
    await vexa.client().start_bot(target, "AdVera Notekeeper", leave_alone_seconds=120)
    assert vexa.bodies[-1]["automatic_leave"] == {"max_time_left_alone": 120_000}


async def test_a_teams_bot_carries_its_passcode_and_cloud():
    vexa = FakeVexa()
    target = parse_meeting_url("https://teams.live.com/meet/9387654321098?p=XyZ9")
    await vexa.client().start_bot(target, "AdVera Notekeeper", "ca", transcribe=True)
    body = vexa.bodies[-1]
    assert body["platform"] == "teams"
    assert body["passcode"] == "XyZ9"
    assert body["teams_base_host"] == "teams.live.com"
    assert body["language"] == "ca"
    assert body["transcribe_enabled"] is True


@pytest.mark.parametrize(
    ("status", "code"),
    [(409, "BOT_ALREADY_ACTIVE"), (422, "INVALID_MEET_URL"), (403, "BOT_PROVIDER_UNAVAILABLE")],
)
async def test_vexa_refusals_become_stable_codes(status, code):
    vexa = FakeVexa()
    vexa.fail_start = status
    with pytest.raises(BotError) as error:
        target = parse_meeting_url("https://meet.google.com/abc-defg-hij")
        await vexa.client().start_bot(target, "B")
    assert error.value.code == code


async def test_an_unreachable_vexa_is_a_retryable_provider_error():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    client = VexaClient("http://vexa:8056", "k", transport=httpx.MockTransport(refuse))
    with pytest.raises(BotError) as error:
        await client.meeting("1")
    assert error.value.code == "BOT_PROVIDER_UNAVAILABLE"
    assert error.value.retryable
    assert await client.health() is False
    assert await client.send_chat("google_meet", "abc-defg-hij", "hola") is False


async def test_writing_in_the_chat_reports_whether_vexa_can():
    assert await FakeVexa().client().send_chat("google_meet", "abc-defg-hij", "x") is False
    assert await FakeVexa(chat_route=True).client().send_chat("google_meet", "a", "x") is True


async def test_the_audio_route_comes_from_master_never_from_the_recording_id():
    vexa = FakeVexa()
    recording = fixture("transcript_completed.json")["recordings"][0]
    path = await vexa.client().audio_path(recording)
    assert path == "/recordings/481159273044/media/730928415562/raw?type=audio"


async def test_without_master_the_media_file_id_is_used():
    recording = {"id": 5, "media_files": [{"id": 9, "type": "audio"}]}
    client = VexaClient(
        "http://vexa", "k", transport=httpx.MockTransport(lambda r: httpx.Response(404))
    )
    assert await client.audio_path(recording) == "/recordings/5/media/9/raw?type=audio"
    assert await client.audio_path({"id": 5, "media_files": []}) is None


async def test_a_download_is_bounded(tmp_path):
    vexa = FakeVexa(recording=b"x" * 100)
    client = vexa.client()
    path = "/recordings/481159273044/media/730928415562/raw"
    assert await client.download(path, tmp_path / "a", max_bytes=1000) == 100
    with pytest.raises(BotError) as error:
        await client.download(path, tmp_path / "b", max_bytes=10)
    assert error.value.code == "RECORDING_TOO_LARGE"
    vexa.recording = b""
    with pytest.raises(BotError) as error:
        await client.download(path, tmp_path / "c", max_bytes=10)
    assert error.value.code == "RECORDING_EMPTY"


async def test_paths_quote_teams_thread_ids():
    vexa = FakeVexa()
    await vexa.client().stop_bot("teams", "19:meeting_abc@thread.v2")
    assert (
        vexa.requests[-1]
        .url.raw_path.decode()
        .startswith("/bots/teams/19%3Ameeting_abc%40thread.v2")
    )


async def test_the_api_key_is_sent_and_redirects_are_not_followed():
    seen = []

    def redirect(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "http://elsewhere/"})

    client = VexaClient("http://vexa", "k3y", transport=httpx.MockTransport(redirect))
    with pytest.raises(BotError):
        await client.meeting("1")
    assert len(seen) == 1
    assert seen[0].headers["x-api-key"] == "k3y"


# ----- API without a configured Vexa -----------------------------------------------------
def test_capabilities_say_no_bot_until_vexa_is_configured(client):
    assert client.get("/api/meeting-bot/capabilities").json() == {
        "configured": False,
        "available": False,
        "bot_name": None,
        "platforms": [],
    }


def test_the_webhook_is_refused_until_a_secret_is_set(client):
    response = client.post("/api/integrations/vexa/webhook", content=b"{}")
    assert (response.status_code, response.json()["detail"]) == (503, "WEBHOOK_NOT_CONFIGURED")


def test_settings_keep_the_vexa_key_and_secret_write_only(client, monkeypatch):
    async def safe(_url):
        return None

    monkeypatch.setattr("app.settings_api.assert_safe_destination", safe)
    response = client.put(
        "/api/settings",
        json={
            "vexa_base_url": "http://vexa:8056/",
            "vexa_api_key": "k",
            "vexa_webhook_secret": "s",
            "vexa_bot_name": "  AdVera   Notekeeper ",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vexa_base_url"] == "http://vexa:8056"
    assert body["vexa_bot_name"] == "AdVera Notekeeper"
    assert body["vexa_configured"] and body["vexa_api_key_set"]
    assert body["vexa_webhook_secret_set"]
    assert body["vexa_speaker_names"] is False
    assert body["vexa_leave_alone_seconds"] == 120
    assert "k" not in (body.get("vexa_api_key"), body.get("vexa_webhook_secret"))
    assert "vexa_api_key" not in body and "vexa_webhook_secret" not in body


def test_the_silence_wait_is_bounded(client):
    for seconds in (10, 7200):
        response = client.put("/api/settings", json={"vexa_leave_alone_seconds": seconds})
        assert (response.status_code, response.json()["detail"]) == (422, "INVALID_SETTINGS")
    response = client.put("/api/settings", json={"vexa_leave_alone_seconds": 300})
    assert response.json()["vexa_leave_alone_seconds"] == 300


def test_an_invalid_vexa_url_never_overwrites_the_settings(client):
    response = client.put("/api/settings", json={"vexa_base_url": "ftp://vexa"})
    assert (response.status_code, response.json()["detail"]) == (422, "INVALID_SETTINGS")
