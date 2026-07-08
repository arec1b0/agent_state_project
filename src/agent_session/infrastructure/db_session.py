import asyncpg
import os
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)
_pool: Optional[asyncpg.Pool] = None

async def init_db_pool() -> None:
    global _pool
    db_url = os.getenv("DB_URL", "postgresql://user:pass@localhost:5432/agent_state")
    _pool = await asyncpg.create_pool(db_url)
    
    # Ensure schema exists on startup
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS event_journal (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                previous_version INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_id ON event_journal(session_id);
        """)
        logger.info("db_schema_initialized")

async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()

def get_db_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized.")
    return _pool