import pytest
import json
from unittest.mock import AsyncMock
from src.agent_session.core.rollback_engine import RollbackEngine

@pytest.mark.asyncio
async def test_rollback_to_version(mock_journal: AsyncMock, mock_kv_store: AsyncMock, mock_telemetry: AsyncMock) -> None:
    engine = RollbackEngine(mock_journal, mock_kv_store, mock_telemetry)
    
    mock_journal.get_events_for_session.return_value = [
        {"payload": json.dumps({"step": 1})},
        {"payload": json.dumps({"step": 2})},
        {"payload": json.dumps({"step": 3})}
    ]
    
    state = await engine.rollback_to_version("session-1", 2)
    
    assert state.version == 2
    assert state.context["step"] == 2
    mock_kv_store.set_state.assert_called_once()