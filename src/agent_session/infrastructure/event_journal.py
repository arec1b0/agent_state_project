import asyncpg
import json
from typing import List
from ..models.events import AgentEvent

class EventJournal:
    """
    Append-only event log in PostgreSQL (table `event_journal`, auto-created
    on startup). The journal is the source of truth for a session's history
    and the input for deterministic rollback.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def append_event(self, event: AgentEvent) -> None:
        query = """
            INSERT INTO event_journal (
                event_id, session_id, event_type, payload, 
                timestamp, idempotency_key, previous_version
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                event.event_id,
                event.session_id,
                event.event_type,
                json.dumps(event.payload),
                event.timestamp.replace(tzinfo=None),
                event.idempotency_key,
                event.previous_version
            )

    async def get_events_for_session(self, session_id: str) -> List[asyncpg.Record]:
        query = """
            SELECT * FROM event_journal 
            WHERE session_id = $1 
            ORDER BY timestamp ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, session_id)