"""Import → durable job → worker → definitive transcript, against real PostgreSQL and Redis."""

import json
import logging
import shutil
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.asr import AsrSegment
from app.database import create_engine, create_sessionmaker
from app.job_queue import RedisStreamQueue
from app.models import Meeting, TranscriptionJob, utcnow
from app.transcription_jobs import claim, queue_meeting_transcription, reconcile
from app.transcription_worker import CONSUMER_GROUP
from tests.fakes import (
    SYNTHETIC_TEXT,
    FakeDiarizer,
    FakeEngine,
    RecordingQueue,
    failing,
    write_pcm,
    write_sine_wav,
)
from tests.integration.conftest import make_worker

pytestmark = pytest.mark.integration


def create_meeting(api, title="Synthetic meeting") -> dict:
    response = api.post("/api/meetings", json={"title": title})
    assert response.status_code == 201
    return response.json()


def import_wav(api, meeting_id, tmp_path, name="sample.wav"):
    source = write_sine_wav(tmp_path / name)
    with source.open("rb") as handle:
        return api.post(
            f"/api/meetings/{meeting_id}/imports",
            files={"file": (name, handle, "audio/wav")},
        )


def import_other_audio(api, meeting_id, tmp_path):
    """A different recording than `import_wav` (same content would reuse the finished job)."""
    source = write_sine_wav(tmp_path / "other.wav", seconds=2.0)
    with source.open("rb") as handle:
        return api.post(
            f"/api/meetings/{meeting_id}/imports",
            files={"file": ("other.wav", handle, "audio/wav")},
        )


async def queue_two_tracks(sessionmaker, storage, settings, meeting_id) -> str:
    """A recorded microphone plus a system track, queued as capture stop does."""
    write_pcm(storage.track_path(meeting_id, "microphone"))
    write_pcm(storage.track_path(meeting_id, "system"))
    async with sessionmaker() as session:
        meeting = await session.get(Meeting, meeting_id)
        job = await queue_meeting_transcription(session, storage, settings, meeting)
        return job.id


async def expire_lease(sessionmaker, job_id) -> None:
    """Make a job look crashed: running, out of attempts and long without a heartbeat."""
    async with sessionmaker() as session:
        await session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(
                status="running",
                lease_token="crashed",
                attempts=3,
                max_attempts=3,
                updated_at=utcnow() - timedelta(hours=1),
            )
        )
        await session.commit()


async def get_job(sessionmaker, job_id) -> TranscriptionJob:
    async with sessionmaker() as session:
        return await session.get(TranscriptionJob, job_id)


async def get_meeting(sessionmaker, meeting_id) -> Meeting:
    async with sessionmaker() as session:
        return await session.get(Meeting, meeting_id)


async def test_import_queues_job_then_worker_publishes_definitive_transcript(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    assert meeting["attendee_count"] is None
    assert meeting["primary_language"] == []

    response = import_wav(api, meeting["id"], tmp_path)

    assert response.status_code == 202
    body = response.json()
    job_id = body["transcription"]["job_id"]
    assert body["transcription"]["status"] == "queued"
    assert body["meeting"]["status"] == "processing"
    assert body["meeting"]["tracks"] == ["system"]
    assert recording_queue.published == [job_id]
    assert storage.track_path(meeting["id"], "system").stat().st_size == 32_000
    assert not storage.transcript_path(meeting["id"]).exists()

    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    )
    await worker.process(job_id)

    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.stage, job.progress, job.lease_token) == (
        "completed",
        "completed",
        1.0,
        None,
    )
    assert (job.processed_tracks, job.total_tracks) == (1, 1)
    detail = api.get(f"/api/meetings/{meeting['id']}").json()
    assert detail["status"] == "ready"
    assert detail["primary_language"] == ["ca"]
    assert detail["attendee_count"] == 1
    assert detail["duration"] == pytest.approx(1.0)

    transcript = api.get(f"/api/meetings/{meeting['id']}/transcript").json()
    assert transcript["status"] == "definitive"
    assert [s["id"] for s in transcript["segments"]] == ["system-00000", "system-00001"]
    for segment in transcript["segments"]:
        assert {"id", "start", "end", "text", "track", "language", "speaker"} <= segment.keys()
        assert segment["track"] == "system"
    assert transcript["provenance"]["tracks"][0]["provider"] == "fake"
    assert transcript["provenance"]["input_sha256"] == job.input_sha256

    status = api.get(f"/api/meetings/{meeting['id']}/transcription").json()
    assert status["status"] == "completed" and status["job_id"] == job_id


async def test_job_is_committed_before_it_is_published(api, tmp_path):
    seen: list[str] = []

    class AssertingQueue(RecordingQueue):
        async def publish(self, job_id):
            # Runs on the app's event loop, so it uses the app's own sessionmaker.
            job = await get_job(api.app.state.sessionmaker, job_id)
            seen.append(job.status if job else "missing")
            await super().publish(job_id)

    api.app.state.transcription_queue = AssertingQueue()
    meeting = create_meeting(api)
    assert import_wav(api, meeting["id"], tmp_path).status_code == 202
    assert seen == ["queued"]


async def test_redis_stream_message_carries_only_the_job_id(
    api, sessionmaker, storage, settings, redis, stream_name, tmp_path
):
    queue = RedisStreamQueue(redis, stream_name, CONSUMER_GROUP)
    await queue.ensure_group()
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]

    entries = await redis.xrange(stream_name)
    assert [fields for _id, fields in entries] == [{"job_id": job_id}]

    messages = await queue.read("test-consumer", block_ms=1000)
    assert [job for _id, job in messages] == [job_id]
    worker = make_worker(sessionmaker, storage, queue, settings, {"whisperx": FakeEngine()})
    await worker.process(messages[0][1])
    await queue.ack(messages[0][0])
    assert (await get_job(sessionmaker, job_id)).status == "completed"
    await redis.delete(stream_name)


async def test_redis_outage_keeps_job_queued_until_reconciled(api, sessionmaker, tmp_path):
    api.app.state.transcription_queue = RecordingQueue(fail=True)
    meeting = create_meeting(api)
    response = import_wav(api, meeting["id"], tmp_path)
    assert response.status_code == 202
    job_id = response.json()["transcription"]["job_id"]

    async with sessionmaker() as session:
        republish = await reconcile(
            session,
            lease_seconds=600,
            republish_after_seconds=0,
            now=utcnow() + timedelta(seconds=1),
        )
    assert republish == [job_id]
    assert (await get_job(sessionmaker, job_id)).status == "queued"


async def test_empty_result_fails_without_touching_previous_transcript(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    previous = {"sentinel": "previous definitive transcript"}
    storage.meeting_dir(meeting["id"]).mkdir(parents=True)
    storage.transcript_path(meeting["id"]).write_text(json.dumps(previous))
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]

    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine(results=[[]])}
    )
    await worker.process(job_id)

    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.error) == ("failed", "EMPTY_TRANSCRIPT")
    assert (await get_meeting(sessionmaker, meeting["id"])).status == "failed"
    assert json.loads(storage.transcript_path(meeting["id"]).read_text()) == previous
    assert storage.track_path(meeting["id"], "system").exists()


async def test_provider_failures_retry_then_fail_with_sanitized_code(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, caplog
):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    recording_queue.published.clear()
    engine = FakeEngine(results=[failing("PROVIDER_EXPLODED")])
    worker = make_worker(sessionmaker, storage, recording_queue, settings, {"whisperx": engine})

    await worker.process(job_id)
    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.stage, job.attempts, job.error) == (
        "queued",
        "retrying",
        1,
        "ASR_FAILED",
    )
    assert recording_queue.published == [job_id]

    await worker.process(job_id)
    await worker.process(job_id)
    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.attempts, job.error) == ("failed", 3, "ASR_FAILED")
    assert (await get_meeting(sessionmaker, meeting["id"])).status == "failed"
    await worker.process(job_id)  # a duplicate message for a failed job is a no-op
    assert len(engine.calls) == 3


async def test_definitive_failure_uses_explicit_fallback(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    settings.asr_definitive_provider = "primary"
    settings.asr_fallback_provider = "secondary"
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    engines = {
        "primary": FakeEngine(name="primary", results=[failing("PRIMARY_DOWN")]),
        "secondary": FakeEngine(name="secondary"),
    }
    await make_worker(sessionmaker, storage, recording_queue, settings, engines).process(job_id)

    assert (await get_job(sessionmaker, job_id)).status == "completed"
    provenance = storage.read_transcript(meeting["id"])["provenance"]["tracks"][0]
    assert (provenance["provider"], provenance["fallback_reason"]) == ("secondary", "PRIMARY_DOWN")


async def test_progress_is_persisted_per_track(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = await queue_two_tracks(sessionmaker, storage, settings, meeting["id"])
    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    )
    writes = []
    original = worker._write

    async def spy(job, token, **values):
        writes.append(values)
        await original(job, token, **values)

    worker._write = spy
    await worker.process(job_id)

    progress = [w["progress"] for w in writes if "progress" in w]
    assert progress == [0.5, 1.0]
    assert [w["track"] for w in writes if w.get("stage") == "transcribing"] == [
        "microphone",
        "system",
    ]
    job = await get_job(sessionmaker, job_id)
    assert (job.processed_tracks, job.total_tracks, job.progress) == (2, 2, 1.0)
    tracks = {s["track"] for s in storage.read_transcript(meeting["id"])["segments"]}
    assert tracks == {"microphone", "system"}


async def test_stale_lease_is_recovered_and_lost_lease_stops_writes(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]

    async with sessionmaker() as session:
        assert await claim(session, job_id, "crashed-worker")
        await session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(updated_at=utcnow() - timedelta(hours=1))
        )
        await session.commit()
    async with sessionmaker() as session:
        republish = await reconcile(session, lease_seconds=600, republish_after_seconds=600)
    assert republish == [job_id]
    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.stage, job.lease_token) == ("queued", "requeued", None)

    def steal_lease(_path):
        import asyncio

        async def steal():
            engine = create_engine(settings.database_url)  # this runs on another thread's loop
            async with create_sessionmaker(engine)() as session:
                await session.execute(
                    update(TranscriptionJob)
                    .where(TranscriptionJob.id == job_id)
                    .values(lease_token="another-worker")
                )
                await session.commit()
            await engine.dispose()

        asyncio.run(steal())

    engine = FakeEngine(on_call=steal_lease)
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": engine}
    ).process(job_id)
    assert not storage.transcript_path(meeting["id"]).exists()
    assert (await get_job(sessionmaker, job_id)).lease_token == "another-worker"


async def test_changed_input_fails_the_job(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    write_pcm(storage.track_path(meeting["id"], "system"), seconds=2)
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(job_id)
    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.error) == ("failed", "INPUT_CHANGED")


async def test_worker_logs_never_contain_transcript_text(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, caplog
):
    caplog.set_level(logging.DEBUG)
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(job_id)
    assert (await get_job(sessionmaker, job_id)).status == "completed"
    assert SYNTHETIC_TEXT not in caplog.text


def test_import_rejects_unsupported_media_and_busy_meetings(api, recording_queue, tmp_path):
    meeting = create_meeting(api)
    response = api.post(
        f"/api/meetings/{meeting['id']}/imports",
        files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert (response.status_code, response.json()["detail"]) == (415, "UNSUPPORTED_MEDIA")

    assert import_wav(api, meeting["id"], tmp_path).status_code == 202
    response = import_wav(api, meeting["id"], tmp_path, name="again.wav")
    assert (response.status_code, response.json()["detail"]) == (409, "MEETING_BUSY")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_video_import_extracts_system_track(api, recording_queue, storage, tmp_path):
    import subprocess

    video = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=1",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(video),
        ],
        check=True,
    )
    meeting = create_meeting(api)
    with video.open("rb") as handle:
        response = api.post(
            f"/api/meetings/{meeting['id']}/imports",
            files={"file": ("clip.mp4", handle, "video/mp4")},
        )
    assert response.status_code == 202
    size = storage.track_path(meeting["id"], "system").stat().st_size
    assert size > 0 and size % 2 == 0
    # Only the extracted audio is kept (ADR 0016).
    assert sorted(p.name for p in storage.meeting_dir(meeting["id"]).iterdir()) == ["system.pcm"]


def test_audio_is_served_as_wav_with_ranges(api, recording_queue, tmp_path):
    meeting = create_meeting(api)
    import_wav(api, meeting["id"], tmp_path)
    full = api.get(f"/api/meetings/{meeting['id']}/audio/system")
    assert full.status_code == 200 and full.headers["content-type"] == "audio/wav"
    assert full.content[:4] == b"RIFF" and len(full.content) == 44 + 32_000

    partial = api.get(
        f"/api/meetings/{meeting['id']}/audio/system", headers={"Range": "bytes=0-99"}
    )
    assert partial.status_code == 206
    assert partial.headers["content-range"] == f"bytes 0-99/{44 + 32_000}"
    assert len(partial.content) == 100
    assert api.get(f"/api/meetings/{meeting['id']}/audio/microphone").status_code == 404


async def test_delete_removes_rows_and_storage(
    api, recording_queue, sessionmaker, storage, tmp_path
):
    meeting = create_meeting(api)
    import_wav(api, meeting["id"], tmp_path)
    assert storage.meeting_dir(meeting["id"]).exists()

    assert api.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    assert api.get(f"/api/meetings/{meeting['id']}").status_code == 404
    assert not storage.meeting_dir(meeting["id"]).exists()
    async with sessionmaker() as session:
        jobs = (await session.execute(select(TranscriptionJob))).scalars().all()
    assert jobs == []


def test_meeting_crud_validation(api):
    assert api.post("/api/meetings", json={"title": "   "}).status_code == 422
    meeting = create_meeting(api, "Original")
    renamed = api.patch(f"/api/meetings/{meeting['id']}", json={"title": "Renamed"}).json()
    assert renamed["title"] == "Renamed"
    assert [m["id"] for m in api.get("/api/meetings").json()] == [meeting["id"]]
    assert api.get("/api/meetings/00000000-0000-0000-0000-000000000000").status_code == 404
    assert api.get(f"/api/meetings/{meeting['id']}/transcription").status_code == 404
    assert api.get(f"/api/meetings/{meeting['id']}/transcript").status_code == 404


async def test_empty_blocking_read_returns_no_messages_without_timeout(redis, stream_name):
    """Regression: the default block must not trip the client's socket read timeout."""
    queue = RedisStreamQueue(redis, stream_name, CONSUMER_GROUP)
    await queue.ensure_group()
    assert await queue.read("idle-consumer") == []
    await redis.delete(stream_name)


def test_failed_extraction_keeps_no_uploaded_file(api, recording_queue, storage):
    meeting = create_meeting(api)
    response = api.post(
        f"/api/meetings/{meeting['id']}/imports",
        files={"file": ("broken.mp4", b"not really a video", "video/mp4")},
    )
    assert (response.status_code, response.json()["detail"]) == (422, "EXTRACTION_FAILED")
    directory = storage.meeting_dir(meeting["id"])
    assert not directory.exists() or list(directory.iterdir()) == []
    assert api.get(f"/api/meetings/{meeting['id']}").json()["status"] == "scheduled"


def unlabelled_engine() -> FakeEngine:
    return FakeEngine(
        results=[
            [
                AsrSegment(0.0, 0.5, "segment a", language="ca"),
                AsrSegment(0.5, 1.0, "segment b", language="ca"),
            ]
        ]
    )


async def test_diarization_labels_stay_unique_across_tracks(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = await queue_two_tracks(sessionmaker, storage, settings, meeting["id"])
    diarizer = FakeDiarizer([[0, 0], [0, 1]])  # microphone: one voice; system: two voices
    await make_worker(
        sessionmaker,
        storage,
        recording_queue,
        settings,
        {"whisperx": unlabelled_engine()},
        diarizer,
    ).process(job_id)

    transcript = storage.read_transcript(meeting["id"])
    by_track = {}
    for segment in transcript["segments"]:
        by_track.setdefault(segment["track"], []).append(segment["speaker"])
    assert by_track == {
        "microphone": ["SPEAKER_00", "SPEAKER_00"],
        "system": ["SPEAKER_01", "SPEAKER_02"],
    }
    provenance = {p["track"]: p["diarization"] for p in transcript["provenance"]["tracks"]}
    assert provenance["system"]["status"] == "completed" and provenance["system"]["speakers"] == 2
    assert api.get(f"/api/meetings/{meeting['id']}").json()["attendee_count"] == 3


async def test_provider_speaker_labels_are_authoritative(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    diarizer = FakeDiarizer([[1, 1]])
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}, diarizer
    ).process(job_id)
    transcript = storage.read_transcript(meeting["id"])
    assert {s["speaker"] for s in transcript["segments"]} == {"SPEAKER_00"}
    assert transcript["provenance"]["tracks"][0]["diarization"]["status"] == "provider"


async def test_unavailable_diarization_still_publishes_transcript(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker,
        storage,
        recording_queue,
        settings,
        {"whisperx": unlabelled_engine()},
        FakeDiarizer(status="unavailable"),
    ).process(job_id)
    assert (await get_job(sessionmaker, job_id)).status == "completed"
    transcript = storage.read_transcript(meeting["id"])
    assert all(s["speaker"] is None for s in transcript["segments"])
    assert transcript["provenance"]["tracks"][0]["diarization"]["status"] == "unavailable"
    assert api.get(f"/api/meetings/{meeting['id']}").json()["attendee_count"] == 0


async def test_a_crashing_diarizer_never_fails_the_transcript(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    class Crashing:
        name = "crashing"

        def diarize(self, pcm_path, spans):
            raise ValueError("clustering blew up")

    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker,
        storage,
        recording_queue,
        settings,
        {"whisperx": unlabelled_engine()},
        Crashing(),
    ).process(job_id)
    assert (await get_job(sessionmaker, job_id)).status == "completed"
    assert (await get_meeting(sessionmaker, meeting["id"])).status == "ready"
    transcript = storage.read_transcript(meeting["id"])
    assert all(s["speaker"] is None for s in transcript["segments"])
    assert transcript["provenance"]["tracks"][0]["diarization"]["status"] == "unavailable"


async def test_progress_advances_within_a_single_track(
    api, recording_queue, sessionmaker, storage, settings, tmp_path, monkeypatch
):
    import time

    from app import transcription_worker

    monkeypatch.setattr(transcription_worker, "PROGRESS_POLL_SECONDS", 0.05)

    class SlowEngine(FakeEngine):
        def transcribe(self, pcm_path, on_progress=None):
            for fraction in (0.25, 0.5, 0.75, 1.0):
                on_progress(fraction)
                time.sleep(0.2)
            return super().transcribe(pcm_path)

    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    worker = make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": SlowEngine()}
    )
    writes = []
    original = worker._write

    async def spy(job, token, **values):
        writes.append(values)
        await original(job, token, **values)

    worker._write = spy
    await worker.process(job_id)

    progress = [w["progress"] for w in writes if "progress" in w]
    within = [value for value in progress if 0 < value < 1]
    assert len(within) >= 3  # partial progress inside the only track
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert max(within) <= 0.9  # ASR share; diarization and finalizing complete the track
    assert (await get_job(sessionmaker, job_id)).progress == 1.0


def test_import_is_refused_beside_a_recorded_microphone(api, recording_queue, storage):
    meeting = create_meeting(api)
    path = storage.track_path(meeting["id"], "microphone")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x01\x00" * 1600)
    source = write_sine_wav(storage.root.parent / "extra.wav")
    with source.open("rb") as handle:
        response = api.post(
            f"/api/meetings/{meeting['id']}/imports", files={"file": ("a.wav", handle, "audio/wav")}
        )
    assert (response.status_code, response.json()["detail"]) == (409, "MEETING_ALREADY_RECORDED")
    assert not storage.track_path(meeting["id"], "system").exists()
    assert recording_queue.published == []


def test_concurrent_imports_of_one_meeting_cannot_both_pass(api, recording_queue, tmp_path):
    from app.media_import import imports_in_progress

    meeting = create_meeting(api)
    imports_in_progress.add(meeting["id"])  # the first import is still converting
    try:
        response = import_wav(api, meeting["id"], tmp_path)
    finally:
        imports_in_progress.discard(meeting["id"])
    assert (response.status_code, response.json()["detail"]) == (409, "IMPORT_IN_PROGRESS")
    assert import_wav(api, meeting["id"], tmp_path).status_code == 202  # released afterwards


def test_oversized_or_unsized_uploads_are_refused_before_the_body_is_read(api, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MEDIA_IMPORT_MAX_BYTES", "1000")
    get_settings.cache_clear()
    meeting = create_meeting(api)
    url = f"/api/meetings/{meeting['id']}/imports"
    too_big = api.post(url, content=b"x", headers={"Content-Length": str(10 * 1024 * 1024)})
    assert (too_big.status_code, too_big.json()["detail"]) == (413, "FILE_TOO_LARGE")

    def chunks():
        yield b"--b\r\n"
        yield b"--b--\r\n"

    unsized = api.post(
        url, content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=b"}
    )
    assert (unsized.status_code, unsized.json()["detail"]) == (411, "LENGTH_REQUIRED")


async def test_model_load_failure_takes_the_fallback_provider(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    """A real provider whose model cannot be loaded (download, memory) must not skip ADR 0003."""
    from app.asr_fasterwhisper import FasterWhisperProvider

    def broken_loader():
        raise RuntimeError("model download failed")

    settings.asr_definitive_provider = "primary"
    settings.asr_fallback_provider = "secondary"
    meeting = create_meeting(api)
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    engines = {
        "primary": FasterWhisperProvider("large-v3", "cpu", "int8", model_loader=broken_loader),
        "secondary": FakeEngine(name="secondary"),
    }
    await make_worker(sessionmaker, storage, recording_queue, settings, engines).process(job_id)

    job = await get_job(sessionmaker, job_id)
    assert job.status == "completed"
    provenance = storage.read_transcript(meeting["id"])["provenance"]["tracks"][0]
    assert (provenance["provider"], provenance["fallback_reason"]) == (
        "secondary",
        "MODEL_LOAD_FAILED",
    )


def test_ffmpeg_reads_only_local_files_and_is_bounded():
    from pathlib import Path

    from app.media_import import ffmpeg_arguments

    args = ffmpeg_arguments("ffmpeg", Path("in.mp4"), Path("out.pcm"), 3600)
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
    assert args.index("-protocol_whitelist") < args.index("-i")  # an input option
    assert args[args.index("-t") + 1] == "3601"
    assert args[args.index("-fs") + 1] == str(3601 * 16_000 * 2)
    assert "-vn" in args and args[-1] == "out.pcm"


def test_media_longer_than_the_limit_is_refused_not_truncated(
    api, recording_queue, storage, tmp_path, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setenv("MEDIA_IMPORT_MAX_SECONDS", "1")
    get_settings.cache_clear()
    meeting = create_meeting(api, "Reunió massa llarga")
    source = write_sine_wav(tmp_path / "long.wav", seconds=3)
    with source.open("rb") as handle:
        response = api.post(
            f"/api/meetings/{meeting['id']}/imports",
            files={"file": ("long.wav", handle, "audio/wav")},
        )
    assert (response.status_code, response.json()["detail"]) == (413, "MEDIA_TOO_LONG")
    assert not storage.track_path(meeting["id"], "system").exists()
    assert recording_queue.published == []


async def test_reconciler_does_not_overwrite_a_lease_that_beat_in_the_meantime(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api, "Reunió amb latència")
    job_id = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    async with sessionmaker() as session:
        assert await claim(session, job_id, "live-worker")
        await session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(updated_at=utcnow() - timedelta(hours=1))
        )
        await session.commit()

    async with sessionmaker() as session:
        real_execute = session.execute
        beaten = []

        async def racing(statement, *args, **kwargs):
            # The worker's heartbeat lands after reconcile read the stale job, before its UPDATE.
            if getattr(statement, "is_update", False) and not beaten:
                beaten.append(True)
                async with sessionmaker() as other:
                    await other.execute(
                        update(TranscriptionJob)
                        .where(TranscriptionJob.id == job_id)
                        .values(updated_at=utcnow())
                    )
                    await other.commit()
            return await real_execute(statement, *args, **kwargs)

        session.execute = racing
        republish = await reconcile(session, lease_seconds=600, republish_after_seconds=600)

    assert beaten and republish == []
    job = await get_job(sessionmaker, job_id)
    assert (job.status, job.lease_token) == ("running", "live-worker")  # still the worker's


async def test_failed_reimport_of_other_audio_does_not_leave_a_stale_transcript_ready(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api, "Reunió amb dos àudios")
    first = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(first)

    second = import_other_audio(api, meeting["id"], tmp_path).json()["transcription"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine(results=[[]])}
    ).process(second["job_id"])

    assert (await get_job(sessionmaker, second["job_id"])).status == "failed"
    # The old transcript describes audio that is no longer there: the meeting is failed.
    assert (await get_meeting(sessionmaker, meeting["id"])).status == "failed"


async def test_expired_lease_of_a_reimport_does_not_leave_a_stale_transcript_ready(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    meeting = create_meeting(api, "Reunió amb transcripció prèvia")
    first = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(first)
    second = import_other_audio(api, meeting["id"], tmp_path).json()["transcription"]
    await expire_lease(sessionmaker, second["job_id"])

    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).reconcile()

    job = await get_job(sessionmaker, second["job_id"])
    assert (job.status, job.error) == ("failed", "LEASE_EXPIRED")
    assert (await get_meeting(sessionmaker, meeting["id"])).status == "failed"


async def test_failed_job_for_the_same_audio_keeps_the_meeting_ready(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    """The transcript still matches the audio, so a failed extra job must not hide it."""
    meeting = create_meeting(api, "Misma pista, otro job")
    first = import_wav(api, meeting["id"], tmp_path).json()["transcription"]["job_id"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(first)
    good = json.loads(storage.transcript_path(meeting["id"]).read_text())

    # Same audio, different model: a new job (its idempotency key differs).
    other_settings = settings.model_copy(update={"asr_definitive_model": "another-model"})
    async with sessionmaker() as session:
        row = await session.get(Meeting, meeting["id"])
        job = await queue_meeting_transcription(session, storage, other_settings, row)
    assert job.id != first
    await make_worker(
        sessionmaker,
        storage,
        recording_queue,
        other_settings,
        {"whisperx": FakeEngine(results=[[]])},
    ).process(job.id)

    assert (await get_job(sessionmaker, job.id)).status == "failed"
    assert (await get_meeting(sessionmaker, meeting["id"])).status == "ready"
    assert json.loads(storage.transcript_path(meeting["id"]).read_text()) == good


async def test_import_never_replaces_a_system_only_recording_but_may_follow_an_empty_attempt(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    # A capture that stored nothing (stop without audio) leaves a manifest but no audio: an
    # import is fine.
    empty = create_meeting(api, "Intent sense àudio")
    with api.websocket_connect(f"/ws/meetings/{empty['id']}/audio") as ws:
        ws.send_json({"type": "start"})
        ws.receive_json()
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "audio.stopped"
        assert ws.receive_json()["code"] == "NO_AUDIO"
    assert import_wav(api, empty["id"], tmp_path).status_code == 202

    # A finished capture that stored a system-only track (the desktop agent) is a recording.
    recorded = create_meeting(api, "Gravació del sistema")
    with api.websocket_connect(f"/ws/meetings/{recorded['id']}/audio") as ws:
        ws.send_json({"type": "start"})
        ws.receive_json()
        # What the desktop agent's track channel does: append PCM to the session's system track.
        sessions = api.app.state.audio_sessions
        sessions.append(sessions.active(recorded["id"]), "system", b"\x01\x00" * 4096)
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "audio.stopped"
        job_id = ws.receive_json()["job_id"]
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(job_id)
    before = storage.track_path(recorded["id"], "system").read_bytes()

    response = import_other_audio(api, recorded["id"], tmp_path)
    assert (response.status_code, response.json()["detail"]) == (409, "MEETING_ALREADY_RECORDED")
    assert storage.track_path(recorded["id"], "system").read_bytes() == before


async def test_reimport_after_an_empty_capture_attempt_is_still_allowed(
    api, recording_queue, sessionmaker, storage, settings, tmp_path
):
    """A stop with no audio leaves a manifest; that must not make later imports 'recorded'."""
    meeting = create_meeting(api, "Intent buit i dues importacions")
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        ws.send_json({"type": "start"})
        ws.receive_json()
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "audio.stopped"
        assert ws.receive_json()["code"] == "NO_AUDIO"
    first = import_wav(api, meeting["id"], tmp_path)
    assert first.status_code == 202
    await make_worker(
        sessionmaker, storage, recording_queue, settings, {"whisperx": FakeEngine()}
    ).process(first.json()["transcription"]["job_id"])

    again = import_other_audio(api, meeting["id"], tmp_path)  # the A1 re-import flow
    assert again.status_code == 202, again.text


def test_import_waits_for_a_recording_session_even_before_its_first_frame(
    api, recording_queue, tmp_path
):
    meeting = create_meeting(api, "Sessió oberta sense àudio")
    with api.websocket_connect(f"/ws/meetings/{meeting['id']}/audio") as ws:
        ws.send_json({"type": "start"})
        ws.receive_json()
        response = import_wav(api, meeting["id"], tmp_path)
        assert (response.status_code, response.json()["detail"]) == (409, "MEETING_BUSY")
