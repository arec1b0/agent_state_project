import redis.asyncio as redis
import os
from typing import Optional

class KVStore:
    """
    Redis access layer: session state snapshots (key `state:{session_id}`)
    and idempotency locks (the raw idempotency key, SET NX with a TTL).
    Configured via the REDIS_URL environment variable.
    """

    def __init__(self) -> None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client = redis.from_url(redis_url, decode_responses=True)

    async def lock_idempotency_key(self, key: str, ttl_seconds: int = 86400) -> bool:
        """Returns True if the lock was acquired, False if the key already exists."""
        result = await self.client.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(result)

    async def get_state(self, session_id: str) -> Optional[str]:
        return await self.client.get(f"state:{session_id}")

    async def set_state(self, session_id: str, state_json: str) -> None:
        await self.client.set(f"state:{session_id}", state_json)

    async def close(self) -> None:
        await self.client.aclose()