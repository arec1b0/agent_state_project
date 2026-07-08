import logging
from fastapi import HTTPException
from ..infrastructure.kv_store import KVStore

logger = logging.getLogger(__name__)

class ExactlyOnceGuard:
    def __init__(self, kv_store: KVStore) -> None:
        self.kv = kv_store

    async def check_and_lock(self, idempotency_key: str) -> None:
        """
        Validates idempotency. Raises 409 if the action was already processed.
        In a distributed system, this prevents the same LLM tool call from executing twice.
        """
        acquired = await self.kv.lock_idempotency_key(idempotency_key)
        if not acquired:
            logger.warning(f"Idempotency lock rejected for key: {idempotency_key}")
            raise HTTPException(
                status_code=409, 
                detail=f"Duplicate request detected for idempotency key: {idempotency_key}"
            )