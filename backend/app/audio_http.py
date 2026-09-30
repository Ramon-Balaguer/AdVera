"""Serve stored PCM tracks as WAV synthesized on the fly (spec §5), with byte ranges so the
browser can seek for click-to-seek playback."""

import re
import struct
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.storage import SAMPLE_RATE, SAMPLE_WIDTH

HEADER_SIZE = 44
CHUNK_SIZE = 256 * 1024
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def wav_header(data_size: int) -> bytes:
    byte_rate = SAMPLE_RATE * SAMPLE_WIDTH
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, byte_rate, SAMPLE_WIDTH, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )


def _parse_range(header: str | None, total: int) -> tuple[int, int] | None:
    if not header:
        return None
    match = RANGE.match(header.strip())
    if not match or match.groups() == ("", ""):
        raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{total}"})
    first, last = match.groups()
    if first == "":
        start, end = max(0, total - int(last)), total - 1
    else:
        start = int(first)
        end = min(int(last), total - 1) if last else total - 1
    if start >= total or start > end:
        raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{total}"})
    return start, end


def _iter_bytes(header: bytes, pcm_path: Path, start: int, end: int) -> Iterator[bytes]:
    position = start
    if position < HEADER_SIZE:
        piece = header[position : min(end + 1, HEADER_SIZE)]
        position += len(piece)
        yield piece
    if position > end:
        return
    with pcm_path.open("rb") as source:
        source.seek(position - HEADER_SIZE)
        remaining = end - position + 1
        while remaining > 0:
            chunk = source.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def wav_response(pcm_path: Path, range_header: str | None) -> StreamingResponse:
    data_size = pcm_path.stat().st_size
    total = HEADER_SIZE + data_size
    header = wav_header(data_size)
    byte_range = _parse_range(range_header, total)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    if byte_range is None:
        start, end, status = 0, total - 1, 200
    else:
        start, end = byte_range
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        _iter_bytes(header, pcm_path, start, end),
        status_code=status,
        media_type="audio/wav",
        headers=headers,
    )
