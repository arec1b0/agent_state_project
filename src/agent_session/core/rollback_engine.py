import json
import logging
from ..models.state import AgentState
from ..infrastructure.event_journal import EventJournal
from ..infrastructure.kv_store import KVStore
from .telemetry import AgentTelemetry

logger = logging.getLogger(__name__)

class RollbackEngine:
    """
    Rebuilds session state at a historical version by replaying the event
    journal from the beginning, then overwrites the Redis snapshot with the
    result. The journal itself is never mutated.
    """

    def __init__(self, journal: EventJournal, kv_store: KVStore, telemetry: AgentTelemetry) -> None:
        self.journal = journal
        self.kv = kv_store
        self.telemetry = telemetry

    async def rollback_to_version(self, session_id: str, target_version: int) -> AgentState:
        """
        Replay the session's events in timestamp order until target_version is
        reached and persist the rebuilt state as the new snapshot.

        Raises:
            RuntimeError: an event payload in the journal is corrupted, making
                deterministic replay impossible.
        """
        records = await self.journal.get_events_for_session(session_id)
        state = AgentState(session_id=session_id)
        
        for record in records:
            if state.version >= target_version:
                break
            
            try:
                payload = json.loads(record['payload'])
                state.context.update(payload)
                state.version += 1
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Corrupted event payload in journal for session {session_id}: {e}")
                raise RuntimeError(f"Cannot complete rollback due to corrupted history: {e}")
                
        await self.kv.set_state(session_id, state.model_dump_json())
        await self.telemetry.log_rollback(session_id, target_version)
        
        logger.info(f"Session {session_id} successfully rolled back to version {state.version}")
        
        return state