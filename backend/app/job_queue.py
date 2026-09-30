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
        await self.redis.xadd(self.stream, {"job_id": job_id})

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
        await self.redis.xack(self.stream, self.group, message_id)
