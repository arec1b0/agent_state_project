import pytest
from unittest.mock import AsyncMock
from src.agent_session.infrastructure.kv_store import KVStore
from src.agent_session.infrastructure.event_journal import EventJournal

@pytest.fixture
def mock_kv_store() -> AsyncMock:
    return AsyncMock(spec=KVStore)

@pytest.fixture
def mock_journal() -> AsyncMock:
    return AsyncMock(spec=EventJournal)