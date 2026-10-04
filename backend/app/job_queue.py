"""JobQueue over Redis Streams (ADR 0008, docs/redis.md).

Redis is transport only: a message carries nothing but `{"job_id": ...}`. PostgreSQL holds
job state, attempts, leases and errors, so a lost message is recovered by reconciliation.
"""

from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import ResponseError

TRANSCRIPTION_CONSUMER_GROUP = "transcription-workers"
READ_BLOCK_MS = 5000
# Must exceed the XREADGROUP block, or an empty blocking read ends in a socket timeout.
SOCKET_TIMEOUT_SECONDS = 30
# A safety net only: PostgreSQL holds the truth and reconciliation republishes lost jobs.
STREAM_MAXLEN = 10_000
CLAIM_PAGE = 100
CLAIM_MAX_PAGES = 10


def create_redis(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=5,
    )


class JobQueue(Protocol):
    async def publish(self, job_id: str) -> None: ...


class RedisStreamQueue:
    def __init__(self, redis: Redis, stream: str, group: str) -> None:
        self.redis = redis
        self.stream = stream
        self.group = group

    async def publish(self, job_id: str) -> None:
        await self.redis.xadd(
            self.stream, {"job_id": job_id}, maxlen=STREAM_MAXLEN, approximate=True
        )

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def read(
        self, consumer: str, *, pending: bool = False, count: int = 1, block_ms: int = READ_BLOCK_MS
    ) -> list[tuple[str, str]]:
        """Read new messages, or this consumer's unacknowledged ones when `pending`."""
        response = await self.redis.xreadgroup(
            self.group,
            consumer,
            {self.stream: "0" if pending else ">"},
            count=count,
            block=None if pending else block_ms,
        )
        messages: list[tuple[str, str]] = []
        for _stream, entries in response or []:
            for message_id, fields in entries:
                job_id = fields.get("job_id") if fields else None
                messages.append((message_id, job_id or ""))
        return messages

    async def ack(self, message_id: str) -> None:
        """Acknowledge and delete: the stream keeps what is pending, not the history."""
        await self.redis.xack(self.stream, self.group, message_id)
        await self.redis.xdel(self.stream, message_id)

    async def claim_stale(self, consumer: str, min_idle_ms: int) -> list[tuple[str, str]]:
        """Take over messages that another consumer read and never acknowledged.

        A container that dies leaves its pending messages under a hostname nobody reuses. The
        job itself is safe either way (its lease decides who may run it); this empties the list.
        """
        messages: list[tuple[str, str]] = []
        start = "0-0"
        for _ in range(CLAIM_MAX_PAGES):
            next_id, entries, *_deleted = await self.redis.xautoclaim(
                self.stream, self.group, consumer, min_idle_ms, start_id=start, count=CLAIM_PAGE
            )
            for message_id, fields in entries:
                messages.append((message_id, (fields or {}).get("job_id") or ""))
            if next_id in ("0-0", b"0-0"):
                break
            start = next_id
        return messages
