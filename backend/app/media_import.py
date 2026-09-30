"""External media import into the system track (ADR 0012, ADR 0016).

The upload is written to a temporary file in the meeting directory, converted to mono PCM16
16 kHz with ffmpeg and verified before it replaces `system.pcm`. Only the extracted audio is
kept: the uploaded file (audio or video) is deleted whether conversion succeeds or fails
(ADR 0016). ffmpeg output is never logged: it can contain file metadata such as titles.
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.storage import SAMPLE_RATE, SAMPLE_WIDTH, MeetingStorage

logger = logging.getLogger("advera.media_import")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
ALLOWED_MIME_PREFIXES = ("audio/", "video/")
# Browsers report some containers generically; the extension allowlist still applies.
GENERIC_MIME_TYPES = {"application/octet-stream", ""}
UPLOAD_PREFIX = ".import-upload-"
CHUNK_SIZE = 1024 * 1024
# Meetings with an import running in this process. Both the import endpoint and the recording
# start consult it, so neither can replace the other's audio (QA/Security review).
imports_in_progress: set[str] = set()


class MediaImportError(Exception):
    """An import failure with a stable code and HTTP status."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def validate_media(filename: str | None, content_type: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise MediaImportError("UNSUPPORTED_MEDIA", 415)
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in GENERIC_MIME_TYPES and not mime.startswith(ALLOWED_MIME_PREFIXES):
        raise MediaImportError("UNSUPPORTED_MEDIA", 415)
    return extension


async def store_upload(
    upload: UploadFile, storage: MeetingStorage, meeting_id: str, extension: str, max_bytes: int
) -> Path:
    directory = storage.meeting_dir(meeting_id)
    directory.mkdir(parents=True, exist_ok=True)
    for previous in directory.glob(f"{UPLOAD_PREFIX}*"):
        previous.unlink()  # leftovers of an interrupted import
    destination = directory / f"{UPLOAD_PREFIX}{uuid.uuid4().hex}{extension}"
    written = 0
    try:
        with destination.open("wb") as target:
            while chunk := await upload.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise MediaImportError("UPLOAD_TOO_LARGE", 413)
                target.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if written == 0:
        destination.unlink(missing_ok=True)
        raise MediaImportError("EMPTY_UPLOAD", 400)
    return destination


def ffmpeg_arguments(ffmpeg: str, source: Path, output: Path, max_seconds: int) -> list[str]:
    """ffmpeg command line: only local files (no network protocols), audio only, bounded.

    Output is cut one second past the limit so an over-long input is detected rather than
    silently truncated to a plausible-looking transcript.
    """
    limit = max_seconds + 1
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        "-t",
        str(limit),
        "-fs",
        str(limit * SAMPLE_RATE * SAMPLE_WIDTH),
        "-f",
        "s16le",
        str(output),
    ]


async def convert_to_system_track(
    source: Path,
    storage: MeetingStorage,
    meeting_id: str,
    ffmpeg: str,
    timeout_seconds: int,
    max_seconds: int = 8 * 3600,
) -> None:
    target = storage.track_path(meeting_id, "system")
    temporary = target.with_suffix(".pcm.tmp")
    temporary.unlink(missing_ok=True)
    try:
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_arguments(ffmpeg, source, temporary, max_seconds),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise MediaImportError("FFMPEG_UNAVAILABLE", 500) from error
    try:
        return_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.wait()
        temporary.unlink(missing_ok=True)
        raise MediaImportError("EXTRACTION_TIMEOUT", 422) from None

    size = temporary.stat().st_size if temporary.exists() else 0
    if return_code == 0 and size > max_seconds * SAMPLE_RATE * SAMPLE_WIDTH:
        temporary.unlink(missing_ok=True)
        raise MediaImportError("MEDIA_TOO_LONG", 413)
    # A complete sample stream is non-empty and aligned to 16-bit samples.
    if return_code != 0 or size < SAMPLE_WIDTH or size % SAMPLE_WIDTH:
        logger.warning("media extraction failed (ffmpeg exit %s)", return_code)
        temporary.unlink(missing_ok=True)
        raise MediaImportError("EXTRACTION_FAILED", 422)
    os.replace(temporary, target)
