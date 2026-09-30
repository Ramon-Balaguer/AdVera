"""External media import into the system track (ADR 0012, meeting-media-import.md).

The uploaded source is kept under the meeting directory, converted to mono PCM16 16 kHz with
ffmpeg and verified before it replaces `system.pcm`. ffmpeg output is never logged: it can
contain file metadata such as titles.
"""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import UploadFile

from app.storage import SAMPLE_WIDTH, MeetingStorage

logger = logging.getLogger("advera.media_import")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
ALLOWED_MIME_PREFIXES = ("audio/", "video/")
# Browsers report some containers generically; the extension allowlist still applies.
GENERIC_MIME_TYPES = {"application/octet-stream", ""}
SOURCE_STEM = "import-source"
CHUNK_SIZE = 1024 * 1024


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
    for previous in directory.glob(f"{SOURCE_STEM}.*"):
        previous.unlink()
    destination = directory / f"{SOURCE_STEM}{extension}"
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


async def convert_to_system_track(
    source: Path, storage: MeetingStorage, meeting_id: str, ffmpeg: str, timeout_seconds: int
) -> None:
    target = storage.track_path(meeting_id, "system")
    temporary = target.with_suffix(".pcm.tmp")
    temporary.unlink(missing_ok=True)
    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            "-f",
            "s16le",
            str(temporary),
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
    # A complete sample stream is non-empty and aligned to 16-bit samples.
    if return_code != 0 or size < SAMPLE_WIDTH or size % SAMPLE_WIDTH:
        logger.warning("media extraction failed (ffmpeg exit %s)", return_code)
        temporary.unlink(missing_ok=True)
        raise MediaImportError("EXTRACTION_FAILED", 422)
    os.replace(temporary, target)
