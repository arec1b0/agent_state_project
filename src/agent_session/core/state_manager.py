import logging
import time
from ..models.state import AgentState
from ..models.events import AgentEvent
from ..infrastructure.kv_store import KVStore
from ..infrastructure.event_journal import EventJournal
from .telemetry import AgentTelemetry

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, kv_store: KVStore, journal: EventJournal, telemetry: AgentTelemetry) -> None:
        self.kv = kv_store
        self.journal = journal
        self.telemetry = telemetry

    async def get_current_state(self, session_id: str) -> AgentState:
        try:
            state_json = await self.kv.get_state(session_id)
            if state_json:
                return AgentState.model_validate_json(state_json)
        except Exception as e:
            logger.error(f"Failed to parse state for {session_id} from KV store: {e}")
            
        return AgentState(session_id=session_id)

    async def apply_event(self, event: AgentEvent) -> AgentState:
        start_time = time.perf_counter()
        current_state = await self.get_current_state(event.session_id)
        
        if current_state.version != event.previous_version:
            logger.error(f"OCC Failure: {current_state.version} != {event.previous_version}")
            raise ValueError(
                f"State version mismatch. Expected {current_state.version}, "
                f"got {event.previous_version}."
            )
        
        current_state.context.update(event.payload)
        current_state.version += 1
        
        try:
            await self.journal.append_event(event)
            await self.kv.set_state(event.session_id, current_state.model_dump_json())
        except Exception as e:
            logger.critical(f"Failed to persist state transition for session {event.session_id}: {e}")
            raise RuntimeError("State persistence failed. System requires intervention.") from e
            
        latency_ms = (time.perf_counter() - start_time) * 1000
        await self.telemetry.log_transition(event, latency_ms)
            
        return current_state