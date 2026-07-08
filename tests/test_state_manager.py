import pytest
from unittest.mock import AsyncMock
from src.agent_session.core.state_manager import StateManager
from src.agent_session.models.state import AgentState
from src.agent_session.models.events import AgentEvent

@pytest.mark.asyncio
async def test_apply_event_success(mock_kv_store: AsyncMock, mock_journal: AsyncMock) -> None:
    manager = StateManager(mock_kv_store, mock_journal)
    
    initial_state = AgentState(session_id="session-1", version=0, context={})
    mock_kv_store.get_state.return_value = initial_state.model_dump_json()
    
    event = AgentEvent(
        event_id="evt-1",
        session_id="session-1",
        event_type="TOOL_CALL",
        payload={"tool_result": "success"},
        idempotency_key="key-1",
        previous_version=0
    )
    
    new_state = await manager.apply_event(event)
    
    assert new_state.version == 1
    assert new_state.context["tool_result"] == "success"
    mock_journal.append_event.assert_called_once_with(event)
    mock_kv_store.set_state.assert_called_once()

@pytest.mark.asyncio
async def test_apply_event_occ_failure(mock_kv_store: AsyncMock, mock_journal: AsyncMock) -> None:
    manager = StateManager(mock_kv_store, mock_journal)
    
    initial_state = AgentState(session_id="session-1", version=2, context={})
    mock_kv_store.get_state.return_value = initial_state.model_dump_json()
    
    event = AgentEvent(
        event_id="evt-2",
        session_id="session-1",
        event_type="USER_PROMPT",
        payload={"text": "hello"},
        idempotency_key="key-2",
        previous_version=1
    )
    
    with pytest.raises(ValueError, match="State version mismatch"):
        await manager.apply_event(event)